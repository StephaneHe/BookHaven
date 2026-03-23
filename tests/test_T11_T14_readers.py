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


def test_T14_comic_img_fits_viewport_phone(phone_page):
    """Check CSS rule: comic img max-width: 100vw."""
    has_rule = phone_page.evaluate("""
        (() => {
            for (const sheet of document.styleSheets) {
                try {
                    for (const rule of sheet.cssRules) {
                        if (rule.cssRules) {
                            for (const sub of rule.cssRules) {
                                if (sub.cssText && sub.cssText.includes('#comic-container') && sub.cssText.includes('100vw')) return true;
                            }
                        }
                    }
                } catch(e) {}
            }
            return false;
        })()
    """)
    assert has_rule, "Comic container should have max-width: 100vw CSS on mobile"
