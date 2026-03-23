"""T01 — Topbar responsive + hamburger button.
T02 — Sidebar drawer (slide-in + overlay).

RED tests: all should FAIL before implementation.
"""
import pytest


# ── T01: Topbar ──────────────────────────────────────────────


def test_T01_hamburger_visible_on_phone(phone_page):
    """Phone: a hamburger button must be visible."""
    btn = phone_page.locator("#hamburger-btn")
    assert btn.count() > 0 and btn.is_visible(), "Hamburger button should be visible on phone"


def test_T01_hamburger_hidden_on_desktop(desktop_page):
    """Desktop: hamburger must be hidden."""
    btn = desktop_page.locator("#hamburger-btn")
    assert btn.count() == 0 or not btn.is_visible(), "Hamburger should be hidden on desktop"


def test_T01_logo_text_hidden_on_phone(phone_page):
    """Phone: logo text 'BookHaven' hidden, only emoji visible."""
    logo_text = phone_page.locator(".topbar .logo .logo-text")
    assert logo_text.count() > 0, "Logo should have a .logo-text span"
    assert not logo_text.is_visible(), "Logo text should be hidden on phone"


def test_T01_logo_text_visible_on_desktop(desktop_page):
    """Desktop: full logo text visible."""
    logo_text = desktop_page.locator(".topbar .logo .logo-text")
    assert logo_text.count() > 0, "Logo should have a .logo-text span"
    assert logo_text.is_visible(), "Logo text should be visible on desktop"


def test_T01_scan_hidden_on_phone(phone_page):
    """Phone: Scan button should be hidden."""
    scan_btn = phone_page.locator("button:has-text('Scan')")
    if scan_btn.count() == 0:
        return  # no scan button at all is OK
    assert not scan_btn.is_visible(), "Scan button should be hidden on phone"


def test_T01_username_hidden_on_phone(phone_page):
    """Phone: username text should be hidden."""
    user_info = phone_page.locator(".user-info")
    if user_info.count() == 0:
        return
    assert not user_info.is_visible(), "Username should be hidden on phone"


def test_T01_logout_is_icon_on_phone(phone_page):
    """Phone: logout should be a compact icon button (<=50px wide, >=40px tall)."""
    logout_btn = phone_page.locator("#logout-btn")
    assert logout_btn.count() > 0, "Logout button needs id='logout-btn'"
    box = logout_btn.bounding_box()
    assert box is not None, "Logout button should be visible"
    assert box["width"] <= 50, f"Logout should be compact, got width={box['width']}"
    assert box["height"] >= 40, f"Logout touch target too small: {box['height']}px"


def test_T01_topbar_height_phone(phone_page):
    """Phone: topbar height should be ~48px."""
    topbar = phone_page.locator(".topbar")
    box = topbar.bounding_box()
    assert box is not None
    assert 40 <= box["height"] <= 56, f"Topbar height should be ~48px, got {box['height']}"


def test_T01_search_fills_space_phone(phone_page):
    """Phone: search box should take most of the available width (>40%)."""
    search = phone_page.locator(".search-box")
    topbar = phone_page.locator(".topbar")
    s_box = search.bounding_box()
    t_box = topbar.bounding_box()
    assert s_box is not None and t_box is not None
    ratio = s_box["width"] / t_box["width"]
    assert ratio > 0.4, f"Search should fill >40% of topbar, got {ratio:.0%}"


def test_T01_all_topbar_buttons_touch_friendly_phone(phone_page):
    """Phone: visible topbar buttons >= 40px touch target."""
    buttons = phone_page.locator(".topbar button").all()
    for btn in buttons:
        if btn.is_visible():
            box = btn.bounding_box()
            if box:
                target = max(box["width"], box["height"])
                assert target >= 40, (
                    f"Button touch target too small: {box['width']}x{box['height']}"
                )



def _ensure_sidebar_closed(page):
    """Close sidebar if open, to start from clean state."""
    page.evaluate("if(typeof closeSidebar==='function') closeSidebar()")
    page.wait_for_timeout(300)


def _open_sidebar(page):
    """Reliably open sidebar via JS."""
    _ensure_sidebar_closed(page)
    page.evaluate("toggleSidebar()")
    page.wait_for_timeout(400)

# ── T02: Sidebar Drawer ─────────────────────────────────────


def test_T02_sidebar_hidden_by_default_phone(phone_page):
    """Phone: sidebar should not be visible initially."""
    sidebar = phone_page.locator(".sidebar")
    # Either hidden, or off-screen
    if sidebar.is_visible():
        box = sidebar.bounding_box()
        assert box is None or box["x"] + box["width"] <= 0, \
            "Sidebar should be hidden or off-screen on phone"


def test_T02_hamburger_opens_sidebar(phone_page):
    """Phone: clicking hamburger opens the sidebar drawer."""
    btn = phone_page.locator("#hamburger-btn")
    if btn.count() == 0:
        pytest.fail("No #hamburger-btn found — T01 must be implemented first")
    btn.click(timeout=2000)
    sidebar = phone_page.locator(".sidebar")
    try:
        sidebar.wait_for(state="visible", timeout=1500)
    except Exception:
        pytest.fail("Sidebar should become visible after hamburger click")


def test_T02_sidebar_overlay_exists(phone_page):
    """Phone: sidebar overlay element must exist."""
    overlay = phone_page.locator("#sidebar-overlay")
    assert overlay.count() > 0, "Sidebar overlay (#sidebar-overlay) must exist"


def test_T02_overlay_closes_sidebar(phone_page):
    """Phone: clicking overlay closes the sidebar."""
    _open_sidebar(phone_page)
    overlay = phone_page.locator("#sidebar-overlay")
    if overlay.count() == 0:
        pytest.fail("No #sidebar-overlay")
    # Click to the right of the sidebar (280px wide) to hit the exposed overlay area
    phone_page.mouse.click(350, 333)
    phone_page.wait_for_timeout(500)
    sidebar = phone_page.locator(".sidebar")
    assert not sidebar.evaluate("el => el.classList.contains('open')"), "Sidebar should be closed"


def test_T02_sidebar_max_width_phone(phone_page):
    """Phone: open sidebar should be <= 280px."""
    _open_sidebar(phone_page)
    sidebar = phone_page.locator(".sidebar")
    box = sidebar.bounding_box()
    assert box is not None, "Sidebar should be visible when open"
    assert box["width"] <= 285, f"Sidebar too wide: {box['width']}px"
    _ensure_sidebar_closed(phone_page)


def test_T02_sidebar_close_button(phone_page):
    """Phone: open sidebar should have a close button."""
    _open_sidebar(phone_page)
    close = phone_page.locator("#sidebar-close-btn")
    assert close.count() > 0 and close.is_visible(), "Sidebar needs a visible close button"
    _ensure_sidebar_closed(phone_page)


def test_T02_sidebar_filters_accessible(phone_page):
    """Phone: open sidebar has filter dropdowns."""
    _open_sidebar(phone_page)
    assert phone_page.locator("#filter-category").is_visible(), "Category filter missing"
    assert phone_page.locator("#filter-format").is_visible(), "Format filter missing"
    assert phone_page.locator("#filter-genre").is_visible(), "Genre filter missing"
    _ensure_sidebar_closed(phone_page)


def test_T02_sidebar_always_visible_desktop(desktop_page):
    """Desktop: sidebar should always be visible (not a drawer)."""
    sidebar = desktop_page.locator(".sidebar")
    assert sidebar.is_visible(), "Sidebar should always be visible on desktop"


def test_T02_no_overlay_desktop(desktop_page):
    """Desktop: no sidebar overlay visible."""
    overlay = desktop_page.locator("#sidebar-overlay")
    if overlay.count() > 0:
        assert not overlay.is_visible(), "No overlay on desktop"
