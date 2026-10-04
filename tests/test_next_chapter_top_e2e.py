"""R99 end to end: in the continuous (webtoon) reader, moving to the next or
previous chapter -- end-of-chapter "Suivant", bottom › / ‹ buttons, arrow keys --
always opens it at the TOP, including when it is already pre-cached and when it
has a stored progress (partial or finished); that stored progress is left intact
until the reader scrolls. Opening a book deliberately still resumes exactly.

Real Flask app in-process on a temporary database with real CBZ files and no
Playwright routing (so the 2.10.0 pre-cache and the browser HTTP cache are live).
"""
import io
import os
import threading
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

IDS = [901, 902, 903, 904]


def _cbz(path, shade, n=4):
    with zipfile.ZipFile(path, "w") as z:
        for i in range(n):
            buf = io.BytesIO()
            Image.new("RGB", (400, 2400), (shade, 30 * i, 140)).save(buf, "PNG")
            z.writestr(f"p_{i}.png", buf.getvalue())


@pytest.fixture()
def live(tmp_path):
    db_path = str(tmp_path / "e2e.db")
    with patch.object(config, "DB_PATH", db_path):
        database.init_db()
        conn = database.get_db()
        for n, bid in enumerate(IDS, start=1):
            p = tmp_path / f"ch{n}.cbz"
            _cbz(p, 50 * n)
            conn.execute("INSERT INTO books (id, path, filename, title, format, series, series_index, "
                         "collection_path, file_size, modified_at, category, reading_mode) VALUES "
                         "(?, ?, ?, ?, 'cbz', 'Top Saga', ?, 'Top Saga', ?, '2026-10-04 10:00:00', 'Comics', 'webtoon')",
                         (bid, str(p), p.name, f"Chapitre {n}", float(n), p.stat().st_size))
        conn.commit()
        conn.close()
        srv = make_server("127.0.0.1", 0, bookhaven.app, threaded=True)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            yield f"http://127.0.0.1:{srv.server_port}"
        finally:
            srv.shutdown()


@pytest.fixture(params=[{"width": 1280, "height": 800}, {"width": 390, "height": 844}], ids=["desktop", "phone"])
def page(request, live, pw_browser):
    ctx = pw_browser.new_context(viewport=request.param)
    pg = ctx.new_page()
    pg.goto(live)
    pg.wait_for_selector(".topbar", timeout=10000)
    yield pg
    ctx.close()


def _put(page, bid, loc, pct):
    page.evaluate(f"""() => fetch('/api/books/{bid}/progress', {{method: 'PUT',
        headers: {{'Content-Type': 'application/json'}},
        body: JSON.stringify({{current_location: '{loc}', progress: {pct}}})}})""")


def _progress(page, bid):
    return page.evaluate(f"() => fetch('/api/books/{bid}/progress').then(r => r.json())")


def _loaded(page, bid):
    page.wait_for_function(
        f"() => document.getElementById('reader-title').textContent === 'Chapitre {IDS.index(bid) + 1}'"
        f" && [...document.querySelectorAll('#comic-scroll img')].length"
        f" && [...document.querySelectorAll('#comic-scroll img')].every(i => i.src.includes('/books/{bid}/') && i.complete && i.naturalHeight)",
        timeout=15000)


def _read_to_bottom(page, vp_w, vp_h):
    page.mouse.move(vp_w // 2, vp_h // 2)
    for _ in range(12):
        page.mouse.wheel(0, 4000)
    page.wait_for_timeout(400)
    assert page.evaluate("() => document.getElementById('comic-container').scrollTop") > 2000


def _assert_at_top(page, label):
    for wait in (0, 300, 1200):                          # and it stays there
        page.wait_for_timeout(wait)
        st = page.evaluate("() => ({ top: document.getElementById('comic-container').scrollTop,"
                           " pos: (p => p && p.idx + p.frac)(comicReadPosition()) })")
        assert st["top"] == 0 and st["pos"] == 0, f"{label}: not at the top after {wait} ms: {st}"


def test_R99_next_chapter_opens_at_top_even_precached_and_with_progress(page):
    vp = page.viewport_size
    # chapter 2 was finished, chapter 3 left half-way
    _put(page, 902, "3.5000", 100)
    _put(page, 903, "2.2500", 60)
    page.evaluate("() => openBook(901)")
    _loaded(page, 901)
    page.wait_for_function("() => comicPrecacheStatus().finished", timeout=30000)
    assert 902 in page.evaluate("() => comicPrecacheStatus().books")       # N+1 already pre-cached

    # end-of-chapter button -> chapter 2 (finished, pre-cached) at the top
    _read_to_bottom(page, vp["width"], vp["height"])
    page.click("#comic-scroll .next-chapter-btn")
    _loaded(page, 902)
    _assert_at_top(page, "Suivant -> finished chapter")
    assert _progress(page, 902)["progress"] == 100                         # not overwritten

    # bottom › button -> chapter 3 (partial progress) at the top
    _read_to_bottom(page, vp["width"], vp["height"])
    page.click("#comic-cont-next")
    _loaded(page, 903)
    _assert_at_top(page, "› -> partially read chapter")
    p3 = _progress(page, 903)
    assert (p3["current_location"], p3["progress"]) == ("2.2500", 60)      # kept until the reader scrolls

    # arrow key → -> chapter 4 (never opened) at the top
    _read_to_bottom(page, vp["width"], vp["height"])
    page.keyboard.press("ArrowRight")
    _loaded(page, 904)
    _assert_at_top(page, "→ -> new chapter")

    # previous: ← and ‹ also land at the top
    _read_to_bottom(page, vp["width"], vp["height"])
    page.keyboard.press("ArrowLeft")
    _loaded(page, 903)
    _assert_at_top(page, "← -> previous chapter")
    _read_to_bottom(page, vp["width"], vp["height"])
    page.click("#comic-cont-prev")
    _loaded(page, 902)
    _assert_at_top(page, "‹ -> previous chapter")


def test_R99_deliberate_open_still_resumes_exactly(page):
    """Opening a book from Continue Reading / detail resumes at its stored position."""
    _put(page, 903, "2.2500", 60)
    page.evaluate("() => openBook(903)")
    _loaded(page, 903)
    page.wait_for_timeout(400)
    pos = page.evaluate("() => (p => p.idx + p.frac)(comicReadPosition())")
    assert abs(pos - 2.25) < 0.01


def test_R99_reading_after_navigation_saves_the_new_position(page):
    """The stored position of a revisited chapter is replaced only once the reader scrolls."""
    vp = page.viewport_size
    _put(page, 902, "3.5000", 100)
    page.evaluate("() => openBook(901)")
    _loaded(page, 901)
    _read_to_bottom(page, vp["width"], vp["height"])
    page.click("#comic-scroll .next-chapter-btn")
    _loaded(page, 902)
    page.mouse.move(vp["width"] // 2, vp["height"] // 2)
    page.mouse.wheel(0, 1500)
    page.wait_for_timeout(400)
    page.evaluate("() => closeReader()")
    page.wait_for_timeout(400)
    p2 = _progress(page, 902)
    assert 0 < float(p2["current_location"]) < 3.5 and p2["progress"] < 100
