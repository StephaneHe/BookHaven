"""Opening a book after scrolling the library: the reader's top bar (back button,
controls) is fully on screen, and closing the reader returns to the same place
in the library. Found 2026-10-04: the page kept ~39 px of library scroll, so
the bar started off screen (and made test_R41_chapter_picker intermittent).

Fake book through Playwright routes (id 930001); nothing reaches the database.
"""
import io
import json
import re

import pytest
from PIL import Image


def _png():
    buf = io.BytesIO()
    Image.new("RGB", (400, 2400), (80, 60, 120)).save(buf, "PNG")
    return buf.getvalue()


PNG = _png()


def _handler(route):
    req = route.request
    if req.method != "GET":
        return route.fulfill(status=200, content_type="application/json", body="{}")
    rest = re.search(r"/api/books/930001(/[^?]*)?", req.url).group(1) or ""
    if rest == "":
        return route.fulfill(status=200, content_type="application/json", body=json.dumps(
            {"id": 930001, "title": "Fake scroll", "format": "cbz", "progress": None, "webtoon": True,
             "series": "", "series_prev": None, "series_next": None, "series_following": [],
             "file_size": 1, "modified_at": "x"}))
    if rest == "/comic-pages":
        return route.fulfill(status=200, content_type="application/json",
                             body=json.dumps({"pages": ["p_0.png", "p_1.png"], "total": 2, "content_version": "v"}))
    return route.fulfill(status=200, content_type="image/png", body=PNG)


@pytest.mark.parametrize("fixture", ["desktop_page", "phone_page"])
def test_reader_topbar_on_screen_after_scrolled_library(request, fixture):
    page = request.getfixturevalue(fixture)
    pattern = re.compile(r".*/api/books/930001(/.*)?$")
    page.route(pattern, _handler)
    try:
        page.evaluate("() => window.scrollTo(0, 0)")
        page.wait_for_timeout(200)
        scrollable = page.evaluate("() => document.scrollingElement.scrollHeight - innerHeight")
        if scrollable < 100:
            pytest.skip("library page too short to scroll on this database")
        page.evaluate("() => window.scrollTo(0, Math.min(1500, document.scrollingElement.scrollHeight))")
        page.wait_for_timeout(200)
        lib_y = page.evaluate("() => window.scrollY")
        assert lib_y > 50

        page.evaluate("() => openBook(930001)")
        page.wait_for_function("() => document.getElementById('comic-container').classList.contains('continuous')")
        page.wait_for_timeout(300)
        bar = page.evaluate("() => { const r = document.querySelector('.reader-topbar').getBoundingClientRect();"
                            " const b = document.querySelector('.reader-topbar .back-btn').getBoundingClientRect();"
                            " return {top: r.top, backTop: b.top, winY: window.scrollY}; }")
        assert bar["top"] >= 0 and bar["backTop"] >= 0 and bar["winY"] == 0, bar

        page.evaluate("() => closeReader()")
        page.wait_for_timeout(500)
        assert abs(page.evaluate("() => window.scrollY") - lib_y) < 5         # back where the library was
    finally:
        page.evaluate("() => window.scrollTo(0, 0)")
        page.unroute(pattern)
