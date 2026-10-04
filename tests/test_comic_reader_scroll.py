"""Comic reader: paged mode starts every page at the TOP; webtoon mode is one
continuous scroll with no page notion, exact scroll-position progress and
chapter/series navigation; webtoon detection ignores credits/covers.

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
    900011: [(1200, 800)] + [(400, 2400)] * 3,                # webtoon series: chapters 1..3,
    900012: [(1200, 800)] + [(400, 2400)] * 3,                # one file per chapter
    900013: [(1200, 800)] + [(400, 2400)] * 3,
    900020: [(700, 1000)] * 4,                                # flagged webtoon, plates NOT tall
}
SERIES = "Fake Series"
SERIES_BOOKS = [900011, 900012, 900013]
WEBTOON_FLAGGED = {900020}
PROGRESS = {}          # bid -> current_location served by the fake book detail
PUTS = []              # progress bodies sent by the reader
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
        prev = nxt = None
        if bid in SERIES_BOOKS:
            i = SERIES_BOOKS.index(bid)
            sib = lambda b: {"id": b, "title": f"Fake {b}", "format": "cbz"}  # noqa: E731
            prev = sib(SERIES_BOOKS[i - 1]) if i > 0 else None
            nxt = sib(SERIES_BOOKS[i + 1]) if i + 1 < len(SERIES_BOOKS) else None
        loc = PROGRESS.get(bid)
        body = {"id": bid, "title": f"Fake {bid}", "format": "cbz",
                "progress": {"current_location": loc, "progress": 10} if loc else None,
                "file_size": 1, "modified_at": "x",
                "series": SERIES if bid in SERIES_BOOKS else "",
                "webtoon": bid in WEBTOON_FLAGGED, "series_prev": prev, "series_next": nxt}
        return route.fulfill(status=200, content_type="application/json", body=json.dumps(body))
    if rest == "/progress" and route.request.method == "PUT":
        PUTS.append((bid, json.loads(route.request.post_data)))
        return route.fulfill(status=200, content_type="application/json", body="{}")
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
    PROGRESS.clear()
    PUTS.clear()
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


# ── Navigation buttons: present, on screen, not covered, and working ──────────
_USABLE = """(sel) => { const e = document.querySelector(sel); if (!e) return 'absent';
    const cs = getComputedStyle(e), r = e.getBoundingClientRect();
    if (cs.display === 'none' || cs.visibility === 'hidden' || !r.width || !r.height) return 'hidden';
    if (r.right <= 0 || r.bottom <= 0 || r.left >= innerWidth || r.top >= innerHeight) return 'offscreen';
    const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
    if (!(hit === e || e.contains(hit))) return 'covered';
    return e.disabled ? 'disabled' : 'ok'; }"""


def _usable(page, sel):
    return page.evaluate(_USABLE, sel)


def _title(page):
    return page.evaluate("() => document.getElementById('reader-title').textContent")


def _wait_title(page, bid):
    # The title changes as soon as navigation starts, while the previous chapter's
    # strips are still displayed: wait for strips of THIS book (and its end
    # marker), or the checks that follow can run against the old chapter.
    page.wait_for_function(f"() => document.getElementById('reader-title').textContent === 'Fake {bid}'"
                           " && document.getElementById('comic-container').classList.contains('continuous')"
                           f" && (i => i && i.src.includes('/books/{bid}/'))(document.querySelector('#comic-scroll img'))"
                           " && document.querySelector('#comic-scroll .next-chapter-btn, #comic-scroll .end-of-manhua')",
                           timeout=15000)


@pytest.mark.parametrize("reader", ["desktop_page", "phone_page"], indirect=True)
def test_paged_mode_has_working_prev_next(reader):
    page = reader
    _open(page, 900004)
    _page_ready(page, 1)
    assert _usable(page, ".comic-nav.next") == "ok"
    assert _usable(page, ".comic-nav.prev") == "ok"
    for sel in ("#comic-cont-prev", "#comic-cont-next", "#comic-cont-top"):
        assert _usable(page, sel) == "hidden", f"{sel} must only show in continuous mode"
    page.click(".comic-nav.next"); _page_ready(page, 2)
    page.click(".comic-nav.next"); _page_ready(page, 3)
    page.click(".comic-nav.prev"); _page_ready(page, 2)


@pytest.mark.parametrize("reader", ["desktop_page", "phone_page"], indirect=True)
def test_continuous_mode_navigates_the_series(reader):
    page = reader
    _open(page, 900012)
    _wait_title(page, 900012)
    for sel in ("#comic-cont-prev", "#comic-cont-top", "#comic-cont-next"):
        assert _usable(page, sel) == "ok", f"{sel}: {_usable(page, sel)}"
    assert _usable(page, ".comic-nav.next") == "hidden"      # paged side bars stay off in this mode
    assert "Fake 900013" in page.inner_text("#comic-scroll .next-chapter-btn")

    # back to top
    page.evaluate("() => { const c = document.getElementById('comic-container'); c.scrollTop = c.scrollHeight; }")
    assert _scroll_top(page) > 100
    page.click("#comic-cont-top")
    page.wait_for_timeout(150)
    assert _scroll_top(page) == 0

    # next chapter = next file of the series, opened at its top
    page.click("#comic-cont-next")
    _wait_title(page, 900013)
    assert _scroll_top(page) == 0
    assert _usable(page, "#comic-cont-next") == "disabled"    # last book: nothing after
    assert page.locator("#comic-scroll .end-of-manhua").count() == 1

    # previous chapter
    page.click("#comic-cont-prev")
    _wait_title(page, 900012)

    # end-of-chapter button and keyboard arrows
    page.click("#comic-scroll .next-chapter-btn")
    _wait_title(page, 900013)
    page.keyboard.press("ArrowLeft")
    _wait_title(page, 900012)
    page.keyboard.press("ArrowLeft")
    _wait_title(page, 900011)
    assert _usable(page, "#comic-cont-prev") == "disabled"    # first book: nothing before
    page.keyboard.press("ArrowRight")
    _wait_title(page, 900012)


# ── Webtoon mode: one continuous scroll, no page notion ───────────────────────
def _wait_continuous(page, bid):
    page.wait_for_function(f"() => document.getElementById('reader-title').textContent === 'Fake {bid}'"
                           " && document.getElementById('comic-container').classList.contains('continuous')"
                           " && [...document.querySelectorAll('#comic-scroll img')].every(i => i.complete && i.naturalHeight)",
                           timeout=15000)


def _scroll_pos(page):
    return page.evaluate("() => { const p = comicReadPosition(); return p.idx + p.frac; }")


@pytest.mark.parametrize("reader", ["desktop_page", "phone_page"], indirect=True)
def test_webtoon_mode_has_no_page_notion(reader):
    page = reader
    _open(page, 900012)
    _wait_continuous(page, 900012)
    for sel in (".comic-nav.prev", ".comic-nav.next", "#comic-img",
                "#comic-page-input", "#comic-page-total", "#comic-page-go"):
        assert _usable(page, sel) == "hidden", f"{sel} must not show in webtoon mode"
    for sel in ("#comic-cont-prev", "#comic-cont-top", "#comic-cont-next"):
        assert _usable(page, sel) == "ok", f"{sel}: {_usable(page, sel)}"
    # plates glued: each one starts exactly where the previous one ends
    gaps = page.evaluate("""() => { const im = [...document.querySelectorAll('#comic-scroll img')];
        return im.slice(1).map((e, i) => Math.round(e.getBoundingClientRect().top - im[i].getBoundingClientRect().bottom)); }""")
    assert gaps and all(g == 0 for g in gaps), gaps
    # a horizontal swipe flips nothing: same book, scroll position untouched
    page.evaluate("() => { document.getElementById('comic-container').scrollTop = 500; }")
    _swipe(page, -200)
    _swipe(page, 200)
    page.wait_for_timeout(200)
    assert _title(page) == "Fake 900012"
    assert _scroll_top(page) == 500


@pytest.mark.parametrize("reader", ["desktop_page"], indirect=True)
def test_server_webtoon_flag_forces_continuous_mode(reader):
    _open(reader, 900020)             # ordinary portrait plates: detection alone says paged
    _wait_continuous(reader, 900020)


@pytest.mark.parametrize("reader", ["desktop_page", "phone_page"], indirect=True)
def test_webtoon_resumes_exactly_where_left(reader):
    page = reader
    PROGRESS[900012] = "2.5000"        # half-way through plate 2
    _open(page, 900012)
    _wait_continuous(page, 900012)
    page.wait_for_timeout(300)
    assert abs(_scroll_pos(page) - 2.5) < 0.01
    # old integer locations still work (top of that plate)
    page.evaluate("() => closeReader()")
    PROGRESS[900013] = "3"
    _open(page, 900013)
    _wait_continuous(page, 900013)
    page.wait_for_timeout(300)
    assert abs(_scroll_pos(page) - 3.0) < 0.01


@pytest.mark.parametrize("reader", ["desktop_page", "phone_page"], indirect=True)
def test_webtoon_saves_scroll_position_and_finishes_at_end(reader):
    page = reader
    _open(page, 900011)
    _wait_continuous(page, 900011)
    # 30 % into plate 1, then leave: that exact position is saved, not finished
    page.evaluate("""() => { const c = document.getElementById('comic-container');
        c.dispatchEvent(new WheelEvent('wheel', {deltaY: 100}));      // the reader scrolls
        const el = document.querySelector('#comic-scroll img[data-idx="1"]');
        c.scrollTop = el.offsetTop + 0.3 * el.offsetHeight; }""")
    page.wait_for_timeout(300)
    page.evaluate("() => closeReader()")
    page.wait_for_timeout(300)
    bid, body = PUTS[-1]
    assert bid == 900011 and abs(float(body["current_location"]) - 1.3) < 0.01, PUTS[-1]
    assert 1 <= body["progress"] < 100, PUTS[-1]
    # reopen: back at that place; read to the end -> 100 %
    PROGRESS[900011] = body["current_location"]
    _open(page, 900011)
    _wait_continuous(page, 900011)
    page.wait_for_timeout(300)
    assert abs(_scroll_pos(page) - 1.3) < 0.01
    page.evaluate("""() => { const c = document.getElementById('comic-container');
        c.dispatchEvent(new WheelEvent('wheel', {deltaY: 100})); c.scrollTop = c.scrollHeight; }""")
    page.wait_for_timeout(400)
    page.evaluate("() => closeReader()")
    page.wait_for_timeout(300)
    assert PUTS[-1][0] == 900011 and PUTS[-1][1]["progress"] == 100, PUTS[-1]


@pytest.mark.parametrize("reader", ["desktop_page"], indirect=True)
def test_reopening_a_finished_webtoon_keeps_it_finished(reader):
    """Open a finished chapter (positioned on its last plate) and leave without
    reading: the stored 100 % must not be rewritten by the restore scrolls."""
    page = reader
    PROGRESS[900013] = "3.2000"
    _open(page, 900013)
    _wait_continuous(page, 900013)
    page.wait_for_timeout(500)
    page.evaluate("() => closeReader()")
    page.wait_for_timeout(300)
    sent = [b for (bid, b) in PUTS if bid == 900013]
    assert sent and all(b["current_location"] == "3.2000" and b["progress"] == 10 for b in sent), sent
