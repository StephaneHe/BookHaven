"""R100 load test: the library must always list, even while webtoon images are
being read and pre-cached from a slow library disk.

Incident 2026-10-04 21:11: image requests (reader + 2.10.0 pre-cache + app) on
the USB library disk occupied every waitress thread; the library listing, which
never touches that disk, queued behind them and the server looked dead.

Setup: the REAL production server (waitress with bookhaven.waitress_options())
in-process on a temporary database; every archive open is slowed down to
simulate a struggling USB disk; a real browser reads a webtoon chapter with the
pre-cache active while 40 concurrent clients hammer comic pages. Meanwhile the
library listing (web home + Android API) must answer in < 2 s, every time.
"""
import io
import os
import threading
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from urllib.request import urlopen

import pytest
from PIL import Image

os.environ.setdefault("BOOKHAVEN_SECRET_KEY", "test-secret-key-32chars-minimum!")
os.environ.setdefault("BOOKHAVEN_TEST_MODE", "1")
os.environ.setdefault("BOOKHAVEN_ENV", "development")

import bookhaven  # noqa: E402
import config     # noqa: E402
import database   # noqa: E402

SLOW_DISK_S = 2.0          # each archive open on the "USB disk"
LIST_LIMIT_S = 2.0         # requirement: the library answers in < 2 s
SERIES = [961, 962, 963, 964]


def _cbz(path, shade, n=10):
    with zipfile.ZipFile(path, "w") as z:
        for i in range(n):
            buf = io.BytesIO()
            Image.new("RGB", (200, 1200), (shade, 20 * i, 90)).save(buf, "PNG")
            z.writestr(f"p_{i}.png", buf.getvalue())


@pytest.fixture()
def server(tmp_path):
    import waitress
    db_path = str(tmp_path / "load.db")
    real_open = bookhaven._open_comic_archive

    def slow_open(path, fmt):
        time.sleep(SLOW_DISK_S)                 # struggling USB library disk
        return real_open(path, fmt)

    with patch.object(config, "DB_PATH", db_path), \
         patch.object(bookhaven, "_open_comic_archive", slow_open):
        database.init_db()
        conn = database.get_db()
        for n, bid in enumerate(SERIES, start=1):
            p = tmp_path / f"ch{n}.cbz"
            _cbz(p, 40 * n)
            conn.execute("INSERT INTO books (id, path, filename, title, format, series, series_index, "
                         "collection_path, file_size, modified_at, category, reading_mode) VALUES "
                         "(?, ?, ?, ?, 'cbz', 'Load Webtoon', ?, 'Load Webtoon', ?, '2026-10-04 10:00:00', 'Comics', 'webtoon')",
                         (bid, str(p), p.name, f"Chapitre {n}", float(n), p.stat().st_size))
        for i in range(200):                    # a library to list
            conn.execute("INSERT INTO books (path, filename, title, author, format, category, file_size) "
                         "VALUES (?, ?, ?, 'Auteur', 'epub', 'Books', 1000)",
                         (f"/lib/b{i}.epub", f"b{i}.epub", f"Livre {i:03d}"))
        conn.commit()
        conn.close()
        bookhaven._page_list_cache.clear()
        srv = waitress.create_server(bookhaven.app, host="127.0.0.1", port=0, **bookhaven.waitress_options())
        threading.Thread(target=srv.run, daemon=True).start()
        try:
            yield f"http://127.0.0.1:{srv.effective_port}"
        finally:
            srv.close()


def _get(url, timeout=15):
    t0 = time.time()
    with urlopen(url, timeout=timeout) as r:
        r.read()
        return r.status, time.time() - t0


def test_R100_library_lists_under_load_with_precache_and_slow_disk(server, pw_browser):
    # 1. a real reader: webtoon chapter 1, pre-cache of chapters 2-4 active
    ctx = pw_browser.new_context(viewport={"width": 1280, "height": 800})
    page = ctx.new_page()
    page.goto(server)
    page.wait_for_selector(".topbar", timeout=15000)
    page.evaluate("() => openBook(961)")

    # 2. 40 concurrent clients hammering comic pages (other tabs, the app...)
    stop = threading.Event()
    statuses = []

    def hammer(k):
        while not stop.is_set():
            bid = SERIES[k % len(SERIES)]
            try:
                statuses.append(_get(f"{server}/api/books/{bid}/comic-page/{k % 10}?h={k}", timeout=30)[0])
            except Exception as e:                       # 503 surfaces as HTTPError
                statuses.append(getattr(e, "code", "err"))
                time.sleep(0.05)

    pool = ThreadPoolExecutor(max_workers=40)
    for k in range(40):
        pool.submit(hammer, k)

    # 3. meanwhile the library must keep listing fast (web home + Android API)
    worst = {}
    try:
        t_end = time.time() + 12
        while time.time() < t_end:
            for name, path in (("home", "/"), ("grouped", "/api/books/grouped?page=1&per_page=50"),
                               ("android list", "/api/books?per_page=50"), ("continue", "/api/continue-reading")):
                status, dt = _get(server + path)
                assert status == 200, (name, status)
                worst[name] = max(worst.get(name, 0), dt)
                assert dt < LIST_LIMIT_S, f"{name} took {dt:.2f}s under load (limit {LIST_LIMIT_S}s)"
            time.sleep(0.3)
    finally:
        stop.set()
        pool.shutdown(wait=True)

    # load really happened: archive slots saturated, overflow shed quickly as 503
    assert len(statuses) >= 40
    assert 503 in statuses
    # once the flood is over, the reader still gets every strip (retries on 503)
    page.wait_for_function("() => [...document.querySelectorAll('#comic-scroll img')].length"
                           " && [...document.querySelectorAll('#comic-scroll img')].every(i => i.complete && i.naturalHeight > 0)",
                           timeout=60000)
    ctx.close()
    print("worst latencies under load:", {k: round(v, 2) for k, v in worst.items()})


def test_R100_busy_archive_returns_503_quickly(server, monkeypatch):
    """With every archive slot taken, an image request is shed with 503 +
    Retry-After after ARCHIVE_IO_WAIT instead of pinning a thread forever."""
    monkeypatch.setattr(bookhaven, "ARCHIVE_IO_WAIT", 0.5)
    held = 0
    while bookhaven._archive_io.acquire(blocking=False):
        held += 1
    try:
        t0 = time.time()
        try:
            urlopen(f"{server}/api/books/961/comic-page/0", timeout=10)
            code, headers = 200, {}
        except Exception as e:
            code, headers = e.code, e.headers
        assert code == 503 and headers.get("Retry-After") and time.time() - t0 < 3
        status, dt = _get(server + "/api/books/grouped?page=1&per_page=50")
        assert status == 200 and dt < LIST_LIMIT_S
    finally:
        for _ in range(held):
            bookhaven._archive_io.release()


def test_R100_stall_monitor_dumps_threads(tmp_path, monkeypatch):
    """A request running longer than STALL_SECONDS produces a dump with the
    in-flight requests and every thread's stack (evidence for next time)."""
    monkeypatch.setattr(bookhaven, "STALL_SECONDS", 0.1)
    monkeypatch.setattr(bookhaven.os.path, "dirname", lambda p: str(tmp_path) if p.endswith("bookhaven.py") else os.path.split(p)[0])
    tid = threading.get_ident()
    with bookhaven._inflight_lock:
        bookhaven._inflight[tid] = ("GET /api/books/1/comic-page/3", time.time() - 30)
    try:
        bookhaven._dump_stall(time.time())
    finally:
        with bookhaven._inflight_lock:
            bookhaven._inflight.pop(tid, None)
    dumps = list((tmp_path / "logs").glob("stall-*.log"))
    assert dumps, "no stall dump written"
    text = dumps[0].read_text(encoding="utf-8")
    assert "GET /api/books/1/comic-page/3" in text and "--- thread" in text
