"""T11-T14 — Reader responsive + touch gesture tests.

RED tests: all should FAIL before implementation.
"""


# ── T11: EPUB Swipe ──────────────────────────────────────────


def test_T11_epub_swipe_support(phone_page):
    """Phone: epub reader should respond to swipe gestures."""
    # Check that swipe handler JS is registered
    has_swipe = phone_page.evaluate("""
        typeof window._epubSwipeEnabled !== 'undefined' ||
        document.getElementById('epub-container')?.dataset?.swipeEnabled === 'true'
    """)
    assert has_swipe, "EPUB reader should have swipe support registered"


# ── T12: Comic Swipe ────────────────────────────────────────


def test_T12_comic_swipe_support(phone_page):
    """Phone: comic reader should respond to swipe gestures."""
    has_swipe = phone_page.evaluate("""
        typeof window._comicSwipeEnabled !== 'undefined' ||
        document.getElementById('comic-container')?.dataset?.swipeEnabled === 'true'
    """)
    assert has_swipe, "Comic reader should have swipe support registered"


# ── T13: Tap-to-toggle Topbar ────────────────────────────────


def test_T13_reader_topbar_toggle_function_exists(phone_page):
    """The toggleReaderTopbar function should exist."""
    exists = phone_page.evaluate("typeof toggleReaderTopbar === 'function'")
    assert exists, "toggleReaderTopbar() function should exist"


# ── T14: Reader Layouts ──────────────────────────────────────


def test_T14_epub_nav_buttons_wide_on_phone(phone_page):
    """Phone: epub nav buttons should be at least 25% viewport width."""
    # We can check CSS even if reader isn't open
    width = phone_page.evaluate("""
        (() => {
            const style = getComputedStyle(document.querySelector('.epub-nav.prev') || document.createElement('div'));
            return parseFloat(style.width) || 0;
        })()
    """)
    # Button is fixed and has 30% width on mobile per spec
    # Can't really test without opening reader, so check CSS rule exists
    css_has_rule = phone_page.evaluate("""
        (() => {
            for (const sheet of document.styleSheets) {
                try {
                    for (const rule of sheet.cssRules) {
                        if (rule.cssText && rule.cssText.includes('.epub-nav') && rule.cssText.includes('30%')) return true;
                        if (rule.cssRules) {
                            for (const sub of rule.cssRules) {
                                if (sub.cssText && sub.cssText.includes('.epub-nav') && sub.cssText.includes('30%')) return true;
                            }
                        }
                    }
                } catch(e) {}
            }
            return false;
        })()
    """)
    assert css_has_rule, "Should have CSS rule for .epub-nav width 30% on mobile"


def test_T14_comic_img_fits_viewport_phone(fresh_phone_page):
    """Phone: a comic page fits the viewport width, filling the area between
    the prev/next nav bars.

    The original check looked for a `#comic-container ... 100vw` CSS rule
    (`max-width:100vw; max-height:calc(100vh - 50px)`, fit-height). That rule
    was deliberately replaced in 2.5.2 (d1ea649, fit-WIDTH default for
    manhua/webtoon: `width:var(--comic-zoom); height:auto`) and refined in
    2.5.3 (fill the area BETWEEN the nav buttons, `--comic-nav-w` 44px on
    mobile). 2.7.14/2.7.15 only bound the column on desktop (>=769px); mobile
    keeps the full-width layout. So assert the rendered result instead of a
    CSS string: an oversized page image is scaled to sit inside the viewport,
    between the nav bars, at 100% zoom. Uses an inline SVG -- no library
    content needed.
    """
    page = fresh_phone_page
    vw = page.viewport_size["width"]
    r = page.evaluate("""() => new Promise((resolve, reject) => {
        document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
        document.getElementById('reader-view').classList.add('active');
        const c = document.getElementById('comic-container');
        c.classList.remove('continuous');
        c.style.display = '';
        const img = document.getElementById('comic-img');
        img.onload = () => {
            const ir = img.getBoundingClientRect();
            const nav = parseFloat(getComputedStyle(c).getPropertyValue('--comic-nav-w'));
            resolve({x: ir.x, w: ir.width, h: ir.height, nav});
        };
        img.onerror = reject;
        img.src = 'data:image/svg+xml,' + encodeURIComponent(
            '<svg xmlns="http://www.w3.org/2000/svg" width="2000" height="3000"></svg>');
    })""")
    assert r["x"] >= 0 and r["x"] + r["w"] <= vw, f"Comic page overflows the {vw}px viewport: {r}"
    expected = vw - 2 * r["nav"]
    assert abs(r["w"] - expected) <= 1, \
        f"Comic page should fill the area between nav bars ({expected}px), got {r['w']}px"
    assert abs(r["h"] / r["w"] - 1.5) < 0.01, f"Aspect ratio not preserved: {r}"
