"""Comic reader: page changes start at the TOP; webtoon detection ignores credits/covers.

Fake books are served through Playwright routes (ids 9000xx), so these tests do
not depend on the local library.
"""
import io
import json
import re

import pytest
from PIL import Image

# (w, h) per plate
BOOKS = {
    900001: [(600, 1080)] * 4,                                # paged, pages taller than the viewport
    900002: [(1200, 800)] + [(400, 2400)] * 4,                # webtoon chapter, landscape credits first
    900003: [(700, 1000)] + [(400, 2400)] * 4,                # webtoon volume, portrait cover first
    900004: [(700, 1000)] * 5,                                # normal comic
}
_PNG = {}


def _png(w, h, shade):
    key = (w, h, shade)
    if key not in _PNG:
        buf = io.BytesIO()
        Image.new("RGB", (w, h), (shade, 40, 255 - shade)).save(buf, "PNG")
        _PNG[key] = buf.getvalue()
    return _PNG[key]


def _handler(route):
    url = route.request.url
    m = re.search(r"/api/books/(9000\d\d)(/.*)?$", url)
    bid, rest = int(m.group(1)), (m.group(2) or "")
    plates = BOOKS[bid]
    if rest == "":
        body = {"id": bid, "title": f"Fake {bid}", "format": "cbz", "progress": None,
                "file_size": 1, "modified_at": "x"}
        return route.fulfill(status=200, content_type="application/json", body=json.dumps(body))
    if rest == "/comic-pages":
        pages = [f"p_{i}.png" for i in range(len(plates))]
        return route.fulfill(status=200, content_type="application/json",
                             body=json.dumps({"pages": pages, "total": len(pages)}))
    pm = re.match(r"/comic-page/(\d+)$", rest)
    if pm:
        i = int(pm.group(1))
        w, h = plates[i]
        return route.fulfill(status=200, content_type="image/png", body=_png(w, h, (i * 60) % 256))
    return route.fulfill(status=200, content_type="application/json", body="{}")  # progress, etc.


@pytest.fixture
def reader(request):
    page = request.getfixturevalue(request.param)
    pattern = re.compile(r".*/api/books/9000\d\d(/.*)?$")
    page.route(pattern, _handler)
    yield page
    page.evaluate("() => { comicZoomApply(100, false); closeReader(); }")
    page.wait_for_timeout(300)
    page.unroute(pattern)


def _open(page, bid):
    page.evaluate(f"() => openBook({bid})")
    page.wait_for_function(
        "() => [...document.querySelectorAll('#comic-img, #comic-scroll img')]"
        ".some(i => i.offsetParent !== null && i.complete && i.naturalWidth > 0)", timeout=15000)


def _page_ready(page, n):
    """Paged mode shows plate n (1-based indicator) and its image is decoded."""
    page.wait_for_function(
        f"""() => document.getElementById('comic-page-input').value === '{n}'
              && document.getElementById('comic-img').complete
              && document.getElementById('comic-img').src.endsWith('/comic-page/{n - 1}')""",
        timeout=10000)


def _scroll_to_bottom(page):
    return page.evaluate("""() => { const c = document.getElementById('comic-container');
        c.scrollTop = c.scrollHeight; c.scrollLeft = c.scrollWidth; return c.scrollTop; }""")


def _scroll_top(page):
    return page.evaluate("() => document.getElementById('comic-container').scrollTop")


def _scroll_left(page):
    return page.evaluate("() => document.getElementById('comic-container').scrollLeft")


def _is_continuous(page):
    return page.evaluate("() => document.getElementById('comic-container').classList.contains('continuous')")


def _swipe(page, dx):
    page.evaluate("""(dx) => {
        const el = document.getElementById('comic-container');
        const r = el.getBoundingClientRect(), x = r.left + r.width / 2, y = r.top + r.height / 2;
        const t = (cx) => new Touch({identifier: 1, target: el, clientX: cx, clientY: y});
        el.dispatchEvent(new TouchEvent('touchstart', {touches: [t(x)], changedTouches: [t(x)], bubbles: true}));
        el.dispatchEvent(new TouchEvent('touchend', {touches: [], changedTouches: [t(x + dx)], bubbles: true}));
    }""", dx)


@pytest.mark.parametrize("reader", ["desktop_page", "phone_page"], indirect=True)
def test_every_page_change_starts_at_top(reader):
    page = reader
    _open(page, 900001)
    assert not _is_continuous(page)
    _page_ready(page, 1)
    # Zoom in (not persisted) so pages overflow on every viewport, phone included,
    # and horizontally too: a page change must reset both axes.
    page.evaluate("() => comicZoomApply(300, false)")

    steps = [
        ("next button", lambda: page.click(".comic-nav.next"), 2),
        ("ArrowRight", lambda: page.keyboard.press("ArrowRight"), 3),
        ("prev button", lambda: page.click(".comic-nav.prev"), 2),
        ("ArrowLeft", lambda: page.keyboard.press("ArrowLeft"), 1),
        ("ArrowDown", lambda: page.keyboard.press("ArrowDown"), 2),
        ("ArrowUp", lambda: page.keyboard.press("ArrowUp"), 1),
        ("swipe left", lambda: _swipe(page, -200), 2),
        ("swipe right", lambda: _swipe(page, 200), 1),
        ("page jump", lambda: page.evaluate(
            "() => { document.getElementById('comic-page-input').value = '4'; comicJumpToInput(); }"), 4),
    ]
    for label, action, expected in steps:
        assert _scroll_to_bottom(page) > 100, f"{label}: page is not scrollable, test is meaningless"
        action()
        _page_ready(page, expected)
        page.wait_for_timeout(150)
        assert _scroll_top(page) == 0, f"{label}: landed at scrollTop={_scroll_top(page)}, expected top"
        assert _scroll_left(page) == 0, f"{label}: landed at scrollLeft={_scroll_left(page)}, expected left edge"


@pytest.mark.parametrize("reader", ["desktop_page"], indirect=True)
@pytest.mark.parametrize("bid,continuous", [(900002, True), (900003, True), (900004, False)])
def test_webtoon_detection_ignores_credits_and_cover(reader, bid, continuous):
    _open(reader, bid)
    assert _is_continuous(reader) is continuous


@pytest.mark.parametrize("dims,expected", [
    ([[1200, 800], [400, 2400], [400, 2400], [400, 2400]], True),    # landscape credits ignored
    ([[700, 1000], [400, 2400], [400, 2400], [400, 2400]], True),    # cover outvoted
    ([[400, 2400]], True),                                           # single tall plate
    ([[700, 1000]] * 4, False),                                      # normal comic
    ([[700, 1000], [400, 2400]], False),                             # tie -> paged
    ([[1200, 800], [1600, 900]], False),                             # only landscape
    ([None, [400, 2400], [400, 2400]], True),                        # failed load ignored
    ([], False),
])
def test_is_webtoon_dims_rule(desktop_page, dims, expected):
    js_dims = [None if d is None else {"w": d[0], "h": d[1]} for d in dims]
    assert desktop_page.evaluate("(d) => comicIsWebtoonDims(d)", js_dims) is expected
