"""End to end: read a webtoon chapter to its end in the continuous reader ->
the next chapter of the series shows up in Continue Reading, and opens.

Runs the real Flask app in-process on a temporary database with real CBZ files,
so nothing touches the library database.
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

SERIES = "E2E Saga"


def _cbz(path, shade):
    with zipfile.ZipFile(path, "w") as z:
        for i in range(3):                       # tall strips -> continuous reader
            buf = io.BytesIO()
            Image.new("RGB", (400, 2400), (shade, 60 + 40 * i, 120)).save(buf, "PNG")
            z.writestr(f"p_{i}.png", buf.getvalue())


@pytest.fixture()
def live(tmp_path):
    db_path = str(tmp_path / "e2e.db")
    with patch.object(config, "DB_PATH", db_path):
        database.init_db()
        conn = database.get_db()
        for n in (1, 2, 3):
            p = tmp_path / f"ch{n}.cbz"
            _cbz(p, 40 * n)
            conn.execute("INSERT INTO books (id, path, filename, title, format, series, series_index, "
                         "collection_path, file_size, category) VALUES (?, ?, ?, ?, 'cbz', ?, ?, ?, ?, 'Comics')",
                         (700 + n, str(p), p.name, f"Chapitre {n}", SERIES, float(n), SERIES, p.stat().st_size))
        conn.commit()
        conn.close()
        srv = make_server("127.0.0.1", 0, bookhaven.app, threaded=True)
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        try:
            yield f"http://127.0.0.1:{srv.server_port}"
        finally:
            srv.shutdown()


@pytest.mark.parametrize("viewport", [{"width": 1280, "height": 800}, {"width": 390, "height": 844}])
def test_finish_chapter_then_next_one_is_in_continue_reading(live, pw_browser, viewport):
    ctx = pw_browser.new_context(viewport=viewport)
    page = ctx.new_page()
    try:
        page.goto(live)
        page.wait_for_selector(".topbar", timeout=10000)
        page.evaluate("() => openBook(701)")
        page.wait_for_function("() => document.getElementById('comic-container').classList.contains('continuous')"
                               " && [...document.querySelectorAll('#comic-scroll img')].every(i => i.complete && i.naturalHeight)",
                               timeout=15000)
        # read to the end, then leave the reader
        page.evaluate("() => { const c = document.getElementById('comic-container'); c.dispatchEvent(new WheelEvent('wheel', {deltaY: 100})); c.scrollTop = c.scrollHeight; }")
        page.wait_for_timeout(400)
        page.evaluate("() => closeReader()")
        page.wait_for_function("() => document.querySelector('#continue-row .continue-card')", timeout=10000)

        prog = page.evaluate("() => fetch('/api/books/701/progress').then(r => r.json())")
        assert prog["progress"] == 100, prog

        rows = page.evaluate("() => fetch('/api/continue-reading').then(r => r.json())")
        assert [(r["id"], r.get("up_next")) for r in rows] == [(702, 1)]

        card = page.locator("#continue-row .continue-card")
        assert card.count() == 1
        assert "Chapitre 2" in card.inner_text() and "À suivre" in card.inner_text()

        card.click()
        page.wait_for_function("() => document.getElementById('reader-title').textContent === 'Chapitre 2'",
                               timeout=10000)
    finally:
        ctx.close()


def test_moving_on_from_the_end_marks_the_chapter_finished(live, pw_browser):
    """'Suivant' at the bottom of a chapter records it as finished before opening the next."""
    ctx = pw_browser.new_context(viewport={"width": 1280, "height": 800})
    page = ctx.new_page()
    try:
        page.goto(live)
        page.wait_for_selector(".topbar", timeout=10000)
        page.evaluate("() => openBook(702)")
        page.wait_for_function("() => document.querySelector('#comic-scroll .next-chapter-btn')"
                               " && [...document.querySelectorAll('#comic-scroll img')].every(i => i.complete && i.naturalHeight)",
                               timeout=15000)
        page.evaluate("() => { const c = document.getElementById('comic-container'); c.dispatchEvent(new WheelEvent('wheel', {deltaY: 100})); c.scrollTop = c.scrollHeight; }")
        page.click("#comic-scroll .next-chapter-btn")          # immediately, no wait for the scroll debounce
        page.wait_for_function("() => document.getElementById('reader-title').textContent === 'Chapitre 3'",
                               timeout=10000)
        prog = page.evaluate("() => fetch('/api/books/702/progress').then(r => r.json())")
        assert prog["progress"] == 100, prog
    finally:
        ctx.close()
