"""User requirements of the web reader (comic zoom / column / chapters / prefetch,
XSS helpers, EPUB reader, deep link), checked end-to-end in Chromium.

Every book used here is FAKE (ids 9100xx) and served through Playwright routes;
every PUT/POST/DELETE to /api/ is intercepted, so the real library database the
test server points at is never written to.
"""
import io
import json
import re
import zipfile

import pytest
from PIL import Image

TALL = (400, 2400)
PORTRAIT = (700, 1000)


def _plates(names, dims):
    return [(n, dims) for n in names]


def _manhua_names(spec):
    """spec: [(prefix, count)] -> ['00010_001.png', ...]"""
    return [f"{p}_{i:03d}.png" for p, n in spec for i in range(1, n + 1)]


# ── Fake EPUB ─────────────────────────────────────────────────────────────────
def _xhtml(title, paras):
    body = "".join(f"<p>{p}</p>" for p in paras)
    return (f'<?xml version="1.0" encoding="utf-8"?>\n'
            f'<html xmlns="http://www.w3.org/1999/xhtml"><head><title>{title}</title></head>'
            f'<body><h1>{title}</h1>{body}</body></html>')


_LOREM = ("Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor "
          "incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud "
          "exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat. ")


def _build_epub():
    chapters = {
        "ch1.xhtml": _xhtml("Chapter One", ["Le Caf\\u00e9 du coin est ouvert."] + [_LOREM] * 25),
        "ch2.xhtml": _xhtml("Chapter Two", [_LOREM] * 25),
        "ch3.xhtml": _xhtml("Chapter Three", [_LOREM] * 25),
    }
    opf = ('<?xml version="1.0" encoding="utf-8"?>\n'
           '<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="uid">'
           '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
           '<dc:title>Fake Epub</dc:title><dc:identifier id="uid">fake-epub-910050</dc:identifier>'
           '<dc:language>fr</dc:language></metadata><manifest>'
           '<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>'
           + "".join(f'<item id="c{i}" href="{h}" media-type="application/xhtml+xml"/>'
                     for i, h in enumerate(chapters, 1))
           + '</manifest><spine toc="ncx">'
           + "".join(f'<itemref idref="c{i}"/>' for i in range(1, len(chapters) + 1))
           + '</spine></package>')
    ncx = ('<?xml version="1.0" encoding="utf-8"?>\n'
           '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">'
           '<head><meta name="dtb:uid" content="fake-epub-910050"/></head>'
           '<docTitle><text>Fake Epub</text></docTitle><navMap>'
           + "".join(f'<navPoint id="n{i}" playOrder="{i}"><navLabel><text>Ch {i}</text></navLabel>'
                     f'<content src="{h}"/></navPoint>' for i, h in enumerate(chapters, 1))
           + '</navMap></ncx>')
    container = ('<?xml version="1.0"?>\n'
                 '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
                 '<rootfiles><rootfile full-path="content.opf" media-type="application/oebps-package+xml"/>'
                 '</rootfiles></container>')
    files = {"META-INF/container.xml": container, "content.opf": opf, "toc.ncx": ncx, **chapters}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        for name, data in files.items():
            z.writestr(name, data, compress_type=zipfile.ZIP_DEFLATED)
    return buf.getvalue(), files


EPUB_BYTES, EPUB_FILES = _build_epub()

# ── Fake library ──────────────────────────────────────────────────────────────
XSS_TITLE = '<img src=x onerror="window.__xss=1;alert(1)">Evil'
BOOKS = {
    910030: {"pages": _plates([f"p_{i}.png" for i in range(4)], PORTRAIT)},       # paged
    910033: {"pages": _plates([f"p_{i}.png" for i in range(3)], PORTRAIT)},       # zoom book A
    910034: {"pages": _plates([f"p_{i}.png" for i in range(3)], PORTRAIT)},       # zoom book B
    910035: {"pages": _plates([f"p_{i}.png" for i in range(4)], TALL)},           # single-chapter webtoon
    910041: {"pages": _plates(_manhua_names([("00010", 2), ("00020", 1), ("01725", 1)]), TALL)},
    910046: {"pages": _plates(_manhua_names([("00010", 4), ("00020", 3), ("00030", 1)]), TALL)},
    910018: {"pages": _plates([f"p_{i}.png" for i in range(2)], PORTRAIT), "title": XSS_TITLE},
    910050: {"format": "epub", "file": EPUB_BYTES},
    910051: {"format": "epub", "file": EPUB_BYTES},
    910059: {"format": "epub", "file": None},                                    # file -> 404
    910077: {"format": "epub", "file": EPUB_BYTES, "title": "Deep Link Fake Title"},
}
PUTS = []        # (bid, body) progress PUTs sent by the reader
REQS = []        # (bid, rest) every request seen for a fake book
_PNG = {}


def _png(w, h, shade):
    key = (w, h, shade)
    if key not in _PNG:
        buf = io.BytesIO()
        Image.new("RGB", (w, h), (shade, 40, 255 - shade)).save(buf, "PNG")
        _PNG[key] = buf.getvalue()
    return _PNG[key]


def _json(route, obj, status=200):
    return route.fulfill(status=status, content_type="application/json", body=json.dumps(obj))


def _handler(route):
    req = route.request
    m = re.search(r"/api/books/(9100\d\d)(/[^?]*)?(\?.*)?$", req.url)
    bid, rest = int(m.group(1)), (m.group(2) or "")
    REQS.append((bid, rest))
    spec = BOOKS[bid]
    fmt = spec.get("format", "cbz")
    if req.method in ("PUT", "POST", "DELETE"):
        if rest == "/progress" and req.method == "PUT":
            PUTS.append((bid, json.loads(req.post_data or "{}")))
        return _json(route, {})
    if rest == "":
        return _json(route, {"id": bid, "title": spec.get("title", f"Fake {bid}"), "format": fmt,
                             "progress": None, "file_size": 1, "modified_at": "x", "series": "",
                             "webtoon": False, "series_prev": None, "series_next": None,
                             "author": "Fake Author"})
    if rest == "/cover":
        return route.fulfill(status=200, content_type="image/png", body=_png(20, 30, 90))
    if rest == "/comic-pages":
        names = [n for n, _ in spec["pages"]]
        return _json(route, {"pages": names, "total": len(names)})
    pm = re.match(r"/comic-page/(\d+)$", rest)
    if pm:
        i = int(pm.group(1))
        w, h = spec["pages"][i][1]
        return route.fulfill(status=200, content_type="image/png", body=_png(w, h, (i * 60) % 256))
    if rest == "/file":
        if spec.get("file") is None:
            return _json(route, {"error": "not found"}, status=404)
        return route.fulfill(status=200, content_type="application/epub+zip", body=spec["file"])
    rm = re.match(r"/epub-resource/(.+)$", rest)
    if rm:
        data = EPUB_FILES.get(rm.group(1))
        if data is None:
            return _json(route, {"error": "not found"}, status=404)
        return route.fulfill(status=200, content_type="application/xhtml+xml", body=data)
    if rest == "/epub-locations":
        return _json(route, {"error": "no cache"}, status=404)
    return _json(route, {})


def _write_guard(route):
    """Nothing but GETs may reach the real server (it uses the real library DB)."""
    if route.request.method in ("PUT", "POST", "DELETE", "PATCH"):
        return _json(route, {})
    return route.fallback()


FAKE = re.compile(r".*/api/books/9100\d\d(/[^?]*)?(\?.*)?$")
API = re.compile(r".*/api/.*")


def _install(target):
    target.route(API, _write_guard)
    target.route(FAKE, _handler)     # registered last -> matched first


def _uninstall(target):
    target.unroute(FAKE)
    target.unroute(API)


def _close(page):
    page.evaluate("() => { if (document.getElementById('reader-view').classList.contains('active')) {"
                  " comicZoomApply(100, false); return closeReader(); } }")
    page.wait_for_timeout(200)


def _clear_zoom_keys(page):
    page.evaluate("""() => Object.keys(localStorage)
        .filter(k => /^bookhaven\\.zoom\\.comic\\.9100\\d\\d$/.test(k))
        .forEach(k => localStorage.removeItem(k))""")


@pytest.fixture
def reader(request):
    page = request.getfixturevalue(request.param)
    _install(page)
    PUTS.clear()
    REQS.clear()
    yield page
    _close(page)
    _clear_zoom_keys(page)
    _uninstall(page)


# ── helpers (same semantics as tests/test_comic_reader_scroll.py) ─────────────
def _open(page, bid):
    page.evaluate(f"() => openBook({bid})")
    page.wait_for_function(
        "() => [...document.querySelectorAll('#comic-img, #comic-scroll img')]"
        ".some(i => i.offsetParent !== null && i.complete && i.naturalWidth > 0)", timeout=15000)


def _page_ready(page, n):
    page.wait_for_function(
        f"""() => document.getElementById('comic-page-input').value === '{n}'
              && document.getElementById('comic-img').complete
              && document.getElementById('comic-img').naturalWidth > 0
              && document.getElementById('comic-img').src.endsWith('/comic-page/{n - 1}')""",
        timeout=10000)


_USABLE = """(sel) => { const e = document.querySelector(sel); if (!e) return 'absent';
    const cs = getComputedStyle(e), r = e.getBoundingClientRect();
    if (cs.display === 'none' || cs.visibility === 'hidden' || !r.width || !r.height) return 'hidden';
    if (r.right <= 0 || r.bottom <= 0 || r.left >= innerWidth || r.top >= innerHeight) return 'offscreen';
    const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
    if (!(hit === e || e.contains(hit))) return 'covered';
    return e.disabled ? 'disabled' : 'ok'; }"""


def _usable(page, sel):
    return page.evaluate(_USABLE, sel)


def _zoom_label(page):
    return page.inner_text("#comic-zoom-label").strip()


def _rect(page, sel):
    return page.evaluate("(s) => { const r = document.querySelector(s).getBoundingClientRect();"
                         " return {l: r.left, r: r.right, w: r.width, t: r.top, b: r.bottom}; }", sel)


def _geom(page):
    """Comic container inner geometry: clientWidth, padding and rect."""
    return page.evaluate("""() => { const c = document.getElementById('comic-container');
        const cs = getComputedStyle(c), r = c.getBoundingClientRect();
        return {cw: c.clientWidth, sw: c.scrollWidth, pl: parseFloat(cs.paddingLeft),
                pr: parseFloat(cs.paddingRight), l: r.left, r: r.right}; }""")


# ── R32 comic zoom ────────────────────────────────────────────────────────────
@pytest.mark.parametrize("reader", ["desktop_page", "phone_page"], indirect=True)
def test_R32_zoom_keys_and_ctrl_wheel(reader):
    """'+', '-', '0' and Ctrl+wheel change the comic zoom label; 100% fits the width."""
    page = reader
    _open(page, 910030)
    _page_ready(page, 1)
    assert _zoom_label(page) == "100%"
    g = _geom(page)
    img = _rect(page, "#comic-img")
    area = g["cw"] - g["pl"] - g["pr"]
    # 100 % = fit the central area (bounded by the desktop column cap of 900 px)
    assert abs(img["w"] - min(area, 900)) <= 1, (img, g)

    page.keyboard.press("+")
    assert _zoom_label(page) == "115%"
    page.keyboard.press("+")
    assert _zoom_label(page) == "130%"
    page.keyboard.press("-")
    assert _zoom_label(page) == "115%"
    page.keyboard.press("0")
    assert _zoom_label(page) == "100%"
    wheel = """(dy) => document.getElementById('comic-container').dispatchEvent(
        new WheelEvent('wheel', {deltaY: dy, ctrlKey: true, bubbles: true, cancelable: true}))"""
    page.evaluate(wheel, -100)
    assert _zoom_label(page) == "115%"
    page.evaluate(wheel, 100)
    page.evaluate(wheel, 100)
    assert _zoom_label(page) == "85%"
    assert page.evaluate("() => document.getElementById('comic-container').style"
                         ".getPropertyValue('--comic-zoom')") == "85%"
    page.keyboard.press("0")
    assert _zoom_label(page) == "100%"


# Desktop case was a real bug until 2.9.1: the 900px column cap made the paged zoom a no-op.
@pytest.mark.parametrize("reader", ["desktop_page", "phone_page"], indirect=True)
def test_R32_zoom_in_overflows_and_nav_stays_usable(reader):
    """At >100% the paged plate is wider than the area (h-scroll) and prev/next stay usable."""
    page = reader
    _open(page, 910030)
    _page_ready(page, 1)
    base_w = _rect(page, "#comic-img")["w"]
    for _ in range(3):
        page.keyboard.press("+")
    assert _zoom_label(page) == "145%"
    page.wait_for_timeout(100)
    g = _geom(page)
    img = _rect(page, "#comic-img")
    area = g["cw"] - g["pl"] - g["pr"]
    assert img["w"] > base_w * 1.3, (base_w, img)
    assert img["w"] > area, (img, g)
    assert g["sw"] > g["cw"], f"no horizontal scroll: {g}"
    assert _usable(page, ".comic-nav.prev") == "ok"
    assert _usable(page, ".comic-nav.next") == "ok"
    page.click(".comic-nav.next")
    _page_ready(page, 2)


# ── R33 zoom remembered per book ──────────────────────────────────────────────
@pytest.mark.parametrize("reader", ["desktop_page"], indirect=True)
def test_R33_zoom_remembered_per_book(reader):
    """Zoom is stored per book in localStorage (bookhaven.zoom.comic.<id>)."""
    page = reader
    _clear_zoom_keys(page)
    _open(page, 910033)
    _page_ready(page, 1)
    page.keyboard.press("+")
    page.keyboard.press("+")
    assert _zoom_label(page) == "130%"
    assert page.evaluate("() => localStorage.getItem('bookhaven.zoom.comic.910033')") == "130"
    page.evaluate("() => closeReader()")
    page.wait_for_timeout(200)
    _open(page, 910033)
    assert _zoom_label(page) == "130%"
    assert page.evaluate("() => getComputedStyle(document.getElementById('comic-container'))"
                         ".getPropertyValue('--comic-zoom').trim()") == "130%"
    page.evaluate("() => closeReader()")
    page.wait_for_timeout(200)
    _open(page, 910034)
    assert _zoom_label(page) == "100%"
    assert page.evaluate("() => localStorage.getItem('bookhaven.zoom.comic.910034')") is None


# ── R34 desktop bounded column ────────────────────────────────────────────────
def _new_page(pw_browser, server, viewport):
    ctx = pw_browser.new_context(viewport=viewport)
    page = ctx.new_page()
    page.goto(server)
    page.wait_for_selector(".topbar", timeout=10000)
    _install(page)
    return page, ctx


@pytest.mark.parametrize("vw,vh", [(1600, 900), (390, 844)])
def test_R34_bounded_column_on_desktop_full_width_on_phone(pw_browser, server, vw, vh):
    """At 1600px the paged plate and webtoon column are <=900px and centred; at 390px full width."""
    page, ctx = _new_page(pw_browser, server, {"width": vw, "height": vh})
    try:
        # paged
        _open(page, 910030)
        _page_ready(page, 1)
        g = _geom(page)
        img = _rect(page, "#comic-img")
        area = g["cw"] - g["pl"] - g["pr"]
        centre = g["l"] + g["pl"] + area / 2
        if vw >= 1600:
            assert 800 < img["w"] <= 900, img
        else:
            assert abs(img["w"] - area) <= 1, (img, g)
        assert abs((img["l"] + img["r"]) / 2 - centre) <= 2, (img, g)
        page.evaluate("() => closeReader()")
        page.wait_for_timeout(200)
        # continuous
        _open(page, 910035)
        page.wait_for_function("() => document.getElementById('comic-container').classList.contains('continuous')")
        g = _geom(page)
        col = _rect(page, "#comic-scroll")
        plate = _rect(page, "#comic-scroll img")
        if vw >= 1600:
            assert 800 < col["w"] <= 900, col
            assert plate["w"] <= 900, plate
        else:
            assert abs(col["w"] - g["cw"]) <= 1, (col, g)
            assert abs(plate["w"] - g["cw"]) <= 1, (plate, g)
        assert abs((col["l"] + col["r"]) / 2 - (g["l"] + g["cw"] / 2)) <= 2, (col, g)
        page.evaluate("() => closeReader()")
        page.wait_for_timeout(200)
    finally:
        ctx.close()


# ── R41 chapter picker ────────────────────────────────────────────────────────
@pytest.mark.parametrize("reader", ["desktop_page"], indirect=True)
def test_R41_chapter_picker(reader):
    """Multi-chapter manhua file shows the chapter picker; single-chapter webtoon hides it."""
    page = reader
    _open(page, 910041)
    page.wait_for_function("() => document.getElementById('comic-container').classList.contains('continuous')")
    assert _usable(page, "#comic-chapter-controls") == "ok"
    opts = page.eval_on_selector_all("#comic-chapter-select option", "els => els.map(e => e.textContent.trim())")
    assert opts == ["Ch. 1", "Ch. 2", "Ch. 172.5"], opts
    idxs = lambda: page.eval_on_selector_all(  # noqa: E731
        "#comic-scroll img", "els => els.map(e => parseInt(e.dataset.idx, 10))")
    assert idxs() == [0, 1]
    page.select_option("#comic-chapter-select", "2")
    page.wait_for_function("() => document.querySelector('#comic-scroll img')?.dataset.idx === '3'")
    assert idxs() == [3]
    page.select_option("#comic-chapter-select", "1")
    page.wait_for_function("() => document.querySelector('#comic-scroll img')?.dataset.idx === '2'")
    assert idxs() == [2]
    page.evaluate("() => closeReader()")
    page.wait_for_timeout(200)

    _open(page, 910035)
    page.wait_for_function("() => document.getElementById('comic-container').classList.contains('continuous')")
    assert _usable(page, "#comic-chapter-controls") == "hidden"


# ── R46 continuous prefetch ───────────────────────────────────────────────────
@pytest.mark.parametrize("reader", ["desktop_page"], indirect=True)
def test_R46_next_chapter_prefetched_on_idle(reader):
    """Opening chapter 1 of a multi-chapter webtoon warms the next chapter's plates on idle."""
    page = reader
    _open(page, 910046)
    page.wait_for_function("() => document.getElementById('comic-container').classList.contains('continuous')")
    shown = page.eval_on_selector_all("#comic-scroll img", "els => els.map(e => parseInt(e.dataset.idx, 10))")
    assert shown == [0, 1, 2, 3]
    next_chapter = {4, 5, 6}
    seen = set()
    for _ in range(50):          # up to ~5 s
        seen = {int(r.rsplit("/", 1)[1]) for b, r in REQS
                if b == 910046 and r.startswith("/comic-page/")} & (next_chapter | {7})
        if next_chapter <= seen:
            break
        page.wait_for_timeout(100)
    assert next_chapter <= seen, f"next chapter plates requested: {sorted(seen)}"
    assert 7 not in seen, "only the NEXT chapter is warmed, not the one after"


# ── R18 XSS helpers ───────────────────────────────────────────────────────────
def test_R18_esc_and_jsq(desktop_page):
    """esc() escapes & < > " ' and jsq() escapes backslash and single quote."""
    out = desktop_page.evaluate("""() => esc('"\\'<>&')""")
    assert out == "&quot;&#39;&lt;&gt;&amp;"
    assert not re.search(r"[\"'<>]", out)
    assert desktop_page.evaluate("() => jsq(\"a\\\\b'c\")") == "a\\\\b\\'c"
    assert desktop_page.evaluate("() => esc(null)") == ""


@pytest.mark.parametrize("reader", ["desktop_page"], indirect=True)
def test_R18_malicious_title_not_executed(reader):
    """A title with <img onerror> in the continue card and reader title is inert text."""
    page = reader
    dialogs = []
    page.on("dialog", lambda d: (dialogs.append(d.message), d.dismiss()))
    page.evaluate("() => { delete window.__xss; }")
    cr = re.compile(r".*/api/continue-reading(\?.*)?$")
    page.route(cr, lambda r: _json(r, [{"id": 910018, "title": XSS_TITLE, "progress": 40,
                                        "series": "", "up_next": False, "format": "cbz"}]))
    try:
        page.evaluate("() => loadContinueReading()")
        page.wait_for_function("() => document.querySelector('#continue-row .continue-card .title')")
        page.wait_for_timeout(300)
        card_title = page.inner_text("#continue-row .continue-card .title")
        assert "<img" in card_title and "Evil" in card_title
        assert page.locator("#continue-row .continue-card .title img").count() == 0
        assert page.locator("#continue-row img[src='x']").count() == 0
        # reader title
        _open(page, 910018)
        assert page.inner_text("#reader-title") == XSS_TITLE
        assert page.locator("#reader-title img").count() == 0
        page.wait_for_timeout(300)
        assert page.evaluate("() => window.__xss") is None
        assert dialogs == []
    finally:
        _close(page)
        page.unroute(cr)
        page.evaluate("() => loadContinueReading()")


# ── R59 EPUB load failure ─────────────────────────────────────────────────────
@pytest.mark.parametrize("reader", ["desktop_page"], indirect=True)
def test_R59_epub_404_shows_error_not_spinner(reader):
    """An EPUB whose file 404s shows an error in the reader instead of endless loading."""
    page = reader
    page.evaluate("() => openBook(910059)")
    page.wait_for_function("() => /Error loading EPUB/.test(document.getElementById('epub-area').innerText)",
                           timeout=15000)
    assert "Loading EPUB" not in page.inner_text("#epub-area")


# ── EPUB reader ───────────────────────────────────────────────────────────────
def _open_epub(page, bid, locations=True):
    page.evaluate(f"() => openBook({bid})")
    page.wait_for_function(
        "() => state.epubRendition && document.querySelector('#epub-area iframe')"
        " && state.epubRendition.getContents().some(c => c.document && c.document.body"
        " && c.document.body.textContent.length > 20)", timeout=20000)
    if locations:
        page.wait_for_function("() => !document.getElementById('epub-seekbar').disabled", timeout=20000)


def _iframe_text(page):
    return page.evaluate("() => state.epubRendition.getContents().map(c => c.document.body.textContent).join(' ')")


@pytest.mark.parametrize("reader", ["desktop_page"], indirect=True)
def test_R61_seekbar_and_page_pill(reader):
    """Once locations are ready the seekbar is enabled and the pill reads 'X / total'."""
    page = reader
    _open_epub(page, 910050)
    page.wait_for_function("() => /^\\d+ \\/ \\d+$/.test(document.getElementById('epub-page-pill').textContent.trim())",
                           timeout=10000)
    pill = page.inner_text("#epub-page-pill").strip()
    cur, total = (int(x) for x in pill.split(" / "))
    assert total >= 2 and 1 <= cur <= total, pill
    assert page.evaluate("() => document.getElementById('epub-seekbar').disabled") is False


@pytest.mark.parametrize("reader", ["desktop_page"], indirect=True)
def test_R63_font_size_bounds_and_reset(reader):
    """A+ caps at 200%, A- floors at 60%, reopening the book resets to 100%."""
    page = reader
    _open_epub(page, 910050, locations=False)
    assert page.evaluate("() => epubFontSize") == 100
    plus = page.locator("#font-controls button", has_text="A+")
    minus = page.locator("#font-controls button", has_text="A−")
    for _ in range(14):
        plus.click()
    assert page.evaluate("() => epubFontSize") == 200
    page.wait_for_timeout(200)
    body_fs = page.evaluate("() => state.epubRendition.getContents()[0].document.body.style.fontSize")
    assert body_fs == "200%", body_fs
    for _ in range(20):
        minus.click()
    assert page.evaluate("() => epubFontSize") == 60
    plus.click()
    assert page.evaluate("() => epubFontSize") == 70
    page.evaluate("() => closeReader()")
    page.wait_for_timeout(300)
    _open_epub(page, 910050, locations=False)
    assert page.evaluate("() => epubFontSize") == 100


@pytest.mark.parametrize("reader", ["desktop_page"], indirect=True)
def test_R64_sepia_theme_applied_and_persisted(reader):
    """Clicking the sepia dot themes the reader and persists 'epubTheme' in localStorage."""
    page = reader
    before = page.evaluate("() => localStorage.getItem('epubTheme')")
    try:
        _open_epub(page, 910050, locations=False)
        page.click(".theme-dot[data-theme='sepia']")
        assert page.evaluate("() => localStorage.getItem('epubTheme')") == "sepia"
        assert page.evaluate("() => document.querySelector(\".theme-dot[data-theme='sepia']\")"
                             ".classList.contains('active')")
        assert page.evaluate("() => getComputedStyle(document.getElementById('epub-container'))"
                             ".backgroundColor") == "rgb(246, 241, 231)"
        bg = page.evaluate("() => { const d = state.epubRendition.getContents()[0].document;"
                           " return getComputedStyle(d.body).backgroundColor; }")
        assert bg == "rgb(246, 241, 231)", bg
        # persisted: a reopened book starts in sepia
        page.evaluate("() => closeReader()")
        page.wait_for_timeout(300)
        _open_epub(page, 910050, locations=False)
        assert page.evaluate("() => state.epubRendition.getContents()[0].document"
                             ".getElementById('reader-theme').textContent").count("#f6f1e7") == 1
    finally:
        _close(page)
        page.evaluate("(t) => { epubSetTheme(t || 'light');"
                      " if (t === null) localStorage.removeItem('epubTheme'); }", before)


@pytest.mark.parametrize("reader", ["desktop_page"], indirect=True)
def test_R66_literal_unicode_escape_rendered(reader):
    """A literal \\u00e9 in the EPUB source text is rendered as 'é'."""
    page = reader
    assert "Caf\\u00e9" in EPUB_FILES["ch1.xhtml"]          # the source really holds the escape
    _open_epub(page, 910050, locations=False)
    text = _iframe_text(page)
    assert "Café du coin" in text, text[:200]
    assert "\\u00e9" not in text


@pytest.mark.parametrize("reader", ["desktop_page"], indirect=True)
def test_R54_epub_never_saves_empty_location(reader):
    """Every progress PUT of the EPUB reader carries a non-empty epubcfi location."""
    page = reader
    _open_epub(page, 910051)
    for _ in range(4):
        page.evaluate("() => epubNext()")
        page.wait_for_timeout(250)
    page.click("#font-controls button >> text=A+")      # reflow: transient relocations
    page.wait_for_timeout(300)
    page.evaluate("() => epubPrev()")
    page.wait_for_timeout(250)
    page.evaluate("() => closeReader()")
    page.wait_for_timeout(400)
    sent = [b for bid, b in PUTS if bid == 910051]
    assert sent, "the reader saved no progress at all"
    for b in sent:
        loc = b.get("current_location")
        assert loc and loc.startswith("epubcfi("), b


@pytest.mark.parametrize("reader", ["desktop_page"], indirect=True)
def test_R65_epub_prefetch_on_idle_and_cleared_on_close(reader):
    """Upcoming spine sections are fetched on idle and the prefetch cache is cleared on close."""
    page = reader
    _open_epub(page, 910050, locations=False)
    page.wait_for_function("() => _epubPrefetch.sections.has('ch2.xhtml') && _epubPrefetch.sections.has('ch3.xhtml')",
                           timeout=8000)
    page.wait_for_timeout(200)
    fetched = {r for b, r in REQS if b == 910050 and r.startswith("/epub-resource/")}
    assert {"/epub-resource/ch2.xhtml", "/epub-resource/ch3.xhtml"} <= fetched, fetched
    assert page.evaluate("() => _epubPrefetch.bookId") == 910050
    page.evaluate("() => closeReader()")
    page.wait_for_timeout(200)
    st = page.evaluate("() => ({s: _epubPrefetch.sections.size, i: _epubPrefetch.imgs.size, b: _epubPrefetch.bookId})")
    assert st == {"s": 0, "i": 0, "b": None}, st


# ── R77 deep link ─────────────────────────────────────────────────────────────
def test_R77_deep_link_opens_book_detail(pw_browser, server):
    """Loading /#book/<id> shows that book's detail view with its title."""
    ctx = pw_browser.new_context(viewport={"width": 1280, "height": 800})
    try:
        _install(ctx)
        page = ctx.new_page()
        page.goto(server + "/#book/910077")
        page.wait_for_function("() => document.getElementById('detail-view').classList.contains('active')"
                               " && document.querySelector('#detail-body h1')", timeout=10000)
        assert page.inner_text("#detail-title") == "Deep Link Fake Title"
        assert page.inner_text("#detail-body h1") == "Deep Link Fake Title"
        assert page.evaluate("() => location.hash") == "#book/910077"
        assert not page.evaluate("() => document.getElementById('library-view').classList.contains('active')")
    finally:
        ctx.close()


# ── R30 paged plate between the nav bars ──────────────────────────────────────
@pytest.mark.parametrize("reader", ["desktop_page", "phone_page"], indirect=True)
def test_R30_paged_image_between_nav_bars(reader):
    """At 100% the paged plate sits between the prev and next bars, never under them."""
    page = reader
    _open(page, 910030)
    _page_ready(page, 1)
    img = _rect(page, "#comic-img")
    prev = _rect(page, ".comic-nav.prev")
    nxt = _rect(page, ".comic-nav.next")
    assert img["w"] > 0
    assert img["l"] >= prev["r"] - 0.5, (img, prev)
    assert img["r"] <= nxt["l"] + 0.5, (img, nxt)
    g = _geom(page)
    if g["cw"] < 769:   # phone: fills the whole gap between the bars
        assert abs(img["l"] - prev["r"]) <= 1 and abs(img["r"] - nxt["l"]) <= 1, (img, prev, nxt)
