"""T03-T10 — CSS responsive tests.

RED tests: all should FAIL before implementation.
"""
import pytest


# ── T03: Book Grid + Cards + Touch Targets ───────────────────


def test_T03_info_btn_visible_on_phone(phone_page):
    """Phone: info button should always be visible (not hover-only)."""
    # Check for any visible info-btn
    btns = phone_page.locator(".info-btn").all()
    visible = [b for b in btns if b.is_visible()]
    if not btns:
        pytest.skip("No info buttons on page")
    assert len(visible) > 0, "Info buttons should be visible without hover on phone"
    box = visible[0].bounding_box()
    assert box["width"] >= 30 and box["height"] >= 30, \
        f"Info btn too small: {box['width']}x{box['height']}"


def test_T03_format_badge_visible_on_phone(phone_page):
    """Phone: format badges should be always visible."""
    badges = phone_page.locator(".format-badge").all()
    visible = [b for b in badges if b.is_visible()]
    if not badges:
        pytest.skip("No format badges on page")
    assert len(visible) > 0, "Format badges should be visible on phone"


def test_T03_grid_columns_phone(phone_page):
    """Phone (375px): grid should have ~3 columns."""
    cards = phone_page.locator(".book-grid > *").all()
    visible = [c for c in cards if c.is_visible() and c.bounding_box()]
    if len(visible) < 3:
        pytest.skip("Not enough cards")
    boxes = [c.bounding_box() for c in visible[:6]]
    first_y = boxes[0]["y"]
    same_row = sum(1 for b in boxes if abs(b["y"] - first_y) < 10)
    assert 2 <= same_row <= 4, f"Expected ~3 columns, got {same_row}"


# ── T04: Category Rows ──────────────────────────────────────


def test_T04_cat_card_smaller_on_phone(phone_page):
    """Phone: category card images <= 110px wide."""
    imgs = phone_page.locator(".cat-card img").all()
    visible = [i for i in imgs if i.is_visible()]
    if not visible:
        pytest.skip("No cat cards visible")
    box = visible[0].bounding_box()
    assert box["width"] <= 115, f"Cat card too wide: {box['width']}px"


# ── T05: Continue Reading ────────────────────────────────────


def test_T05_continue_card_smaller_on_phone(phone_page):
    """Phone: continue reading card images <= 120px wide."""
    imgs = phone_page.locator(".continue-card img").all()
    visible = [i for i in imgs if i.is_visible()]
    if not visible:
        pytest.skip("No continue reading cards")
    box = visible[0].bounding_box()
    assert box["width"] <= 125, f"Continue card too wide: {box['width']}px"


# ── T06: Breadcrumb ──────────────────────────────────────────


def test_T06_no_horizontal_overflow_phone(phone_page):
    """Phone: no horizontal overflow on library page."""
    body_w = phone_page.evaluate("document.body.scrollWidth")
    assert body_w <= 380, f"Page overflows: body scrollWidth={body_w}px"


# ── T07: Pagination ──────────────────────────────────────────


def test_T07_pagination_touch_friendly(phone_page):
    """Phone: pagination buttons >= 40px tall."""
    btns = phone_page.locator(".pagination button").all()
    visible = [b for b in btns if b.is_visible()]
    if not visible:
        pytest.skip("No pagination visible")
    for btn in visible:
        box = btn.bounding_box()
        assert box["height"] >= 40, f"Pagination btn too small: {box['height']}px"


# ── T08: Login Page ──────────────────────────────────────────


def test_T08_login_fits_phone(phone_page):
    """Phone: verify login page CSS rules exist for responsive sizing."""
    # In test mode, auto-login skips login page. So we verify CSS rules exist.
    has_login_css = phone_page.evaluate("""
        (() => {
            for (const sheet of document.styleSheets) {
                try {
                    for (const rule of sheet.cssRules) {
                        if (rule.cssRules) {
                            for (const sub of rule.cssRules) {
                                if (sub.cssText && sub.cssText.includes('.login-box') && sub.cssText.includes('padding'))
                                    return true;
                            }
                        }
                    }
                } catch(e) {}
            }
            return false;
        })()
    """)
    assert has_login_css, "Login responsive CSS rules should exist"
    # Also verify input min-height rule
    has_input_css = phone_page.evaluate("""
        (() => {
            for (const sheet of document.styleSheets) {
                try {
                    for (const rule of sheet.cssRules) {
                        if (rule.cssRules) {
                            for (const sub of rule.cssRules) {
                                if (sub.cssText && sub.cssText.includes('.login-box') && sub.cssText.includes('48px'))
                                    return true;
                            }
                        }
                    }
                } catch(e) {}
            }
            return false;
        })()
    """)
    assert has_input_css, "Login inputs should have min-height: 48px CSS rule"


# ── T09: Modals ──────────────────────────────────────────────


def test_T09_modal_fullscreen_on_phone(phone_page):
    """Phone: verify modal CSS rules exist for full-screen on mobile."""
    has_modal_css = phone_page.evaluate("""
        (() => {
            for (const sheet of document.styleSheets) {
                try {
                    for (const rule of sheet.cssRules) {
                        if (rule.cssRules) {
                            for (const sub of rule.cssRules) {
                                if (sub.cssText && sub.cssText.includes('.modal-box') && sub.cssText.includes('100vw'))
                                    return true;
                            }
                        }
                    }
                } catch(e) {}
            }
            return false;
        })()
    """)
    assert has_modal_css, "Modal should have width: 100vw CSS rule on mobile"
    has_close_css = phone_page.evaluate("""
        (() => {
            for (const sheet of document.styleSheets) {
                try {
                    for (const rule of sheet.cssRules) {
                        if (rule.cssRules) {
                            for (const sub of rule.cssRules) {
                                if (sub.cssText && sub.cssText.includes('.modal-close') && sub.cssText.includes('44px'))
                                    return true;
                            }
                        }
                    }
                } catch(e) {}
            }
            return false;
        })()
    """)
    assert has_close_css, "Modal close button should be 44px on mobile"


# ── T10: Enrichment Bar ─────────────────────────────────────


def test_T10_enrichment_bar_compact(phone_page):
    """Phone: enrichment bar (if active) should be compact (<= 40px)."""
    bar = phone_page.locator(".enrichment-bar.active")
    if bar.count() == 0:
        pytest.skip("Enrichment bar not active")
    box = bar.bounding_box()
    assert box["height"] <= 40, f"Bar too tall: {box['height']}px"
