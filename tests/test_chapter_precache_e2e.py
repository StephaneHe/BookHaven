"""R98 end to end: read a webtoon chapter -> the next chapter is pre-cached, and
opening it is served from the browser cache with NO page request to the server.

Real Flask app in-process on a temporary database with real CBZ files and no
Playwright routing (routing would disable the browser HTTP cache). Requests are
counted by a WSGI middleware.
"""
import io
import os
import re
import threading
import time
import zipfile
from unittest.mock import patch

import pytest
from PIL import Image
from werkzeug.serving import make_server

os.environ.setdefault("BOOKHAVEN_SECRET_KEY", "test-secret-key-32chars-minimum!")
os.environ.setdefault("BOOKHAVEN_TEST_MODE", "1")
os.environ.setdefault("BOOKHAVEN_ENV", "development")

import bookhaven  # noqa: E402
import config     # noqa: E402
import database   # noqa: E402

PAGE_HITS = []        # (book_id, page) served by the app


def _cbz(path, shade, n=4):
    with zipfile.ZipFile(path, "w") as z:
        for i in range(n):
            buf = io.BytesIO()
            Image.new("RGB", (400, 2400), (shade, 40 * i, 120)).save(buf, "PNG")
            z.writestr(f"p_{i}.png", buf.getvalue())


@pytest.fixture()
def live(tmp_path):
    db_path = str(tmp_path / "e2e.db")
    PAGE_HITS.clear()
    inner = bookhaven.app.wsgi_app

    def counting(environ, start_response):
        m = re.match(r"/api/books/(\d+)/comic-page/(\d+)$", environ.get("PATH_INFO", ""))
        if m:
            PAGE_HITS.append((int(m.group(1)), int(m.group(2))))
        return inner(environ, start_response)

    with patch.object(config, "DB_PATH", db_path), patch.object(bookhaven.app, "wsgi_app", counting):
        database.init_db()
        conn = database.get_db()
        for n in range(1, 6):
            p = tmp_path / f"ch{n}.cbz"
            _cbz(p, 40 * n)
            conn.execute("INSERT INTO books (id, path, filename, title, format, series, series_index, "
                         "collection_path, file_size, modified_at, category, reading_mode) "
                         "VALUES (?, ?, ?, ?, 'cbz', 'E2E Webtoon', ?, 'E2E Webtoon', ?, '2026-10-04 10:00:00', "
                         "'Comics', 'webtoon')",
                         (800 + n, str(p), p.name, f"Chapitre {n}", float(n), p.stat().st_size))
        conn.commit()
        conn.close()
        srv = make_server("127.0.0.1", 0, bookhaven.app, threaded=True)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            yield f"http://127.0.0.1:{srv.server_port}"
        finally:
            srv.shutdown()


def test_R98_next_chapter_served_from_cache_without_server_requests(live, pw_browser):
    ctx = pw_browser.new_context(viewport={"width": 1280, "height": 800})
    page = ctx.new_page()
    try:
        page.goto(live)
        page.wait_for_selector(".topbar", timeout=10000)
        page.evaluate("() => openBook(801)")
        page.wait_for_function("() => comicPrecacheStatus().finished", timeout=30000)
        assert page.evaluate("() => comicPrecacheStatus().books") == [802, 803, 804]
        assert {p for b, p in PAGE_HITS if b == 802} == {0, 1, 2, 3}
        assert not [h for h in PAGE_HITS if h[0] == 805]            # beyond k = 3

        before = len(PAGE_HITS)
        t0 = time.time()
        page.evaluate("() => comicChapterStep(1)")
        page.wait_for_function(
            "() => { const i = document.querySelector('#comic-scroll img');"
            " return i && i.src.includes('/books/802/') && i.complete && i.naturalHeight > 0; }",
            timeout=15000)
        first_strip_s = time.time() - t0
        page.wait_for_function("() => [...document.querySelectorAll('#comic-scroll img')]"
                               ".every(i => i.complete && i.naturalHeight)", timeout=15000)
        served_802 = [h for h in PAGE_HITS[before:] if h[0] == 802]
        assert served_802 == [], f"next chapter re-requested from the server: {served_802}"
        assert first_strip_s < 2.0
    finally:
        ctx.close()
