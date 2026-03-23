"""Optimized conftest - reuse pages across tests in same viewport."""
import os
import sys
import time
import subprocess
import pytest
from urllib.request import urlopen
from urllib.error import URLError

PYTHON = r"C:\Users\user\AppData\Local\Programs\Python\Python312\python.exe"
SERVER_SCRIPT = r"H:\BookHaven\bookhaven.py"
TEST_PORT = 8098
BASE_URL = f"http://localhost:{TEST_PORT}"

PHONE = {"width": 375, "height": 667}
TABLET = {"width": 768, "height": 1024}
DESKTOP = {"width": 1280, "height": 800}


def _wait_for_server(url, timeout=15):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urlopen(url, timeout=2)
            return True
        except (URLError, OSError):
            time.sleep(0.3)
    return False


@pytest.fixture(scope="session")
def server():
    # Kill any lingering python processes on test port
    env = os.environ.copy()
    env["BOOKHAVEN_TEST_MODE"] = "1"
    env["BOOKHAVEN_PORT"] = str(TEST_PORT)
    proc = subprocess.Popen(
        [PYTHON, SERVER_SCRIPT],
        cwd=r"H:\BookHaven",
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if not _wait_for_server(BASE_URL):
        proc.kill()
        out, err = proc.communicate(timeout=5)
        raise RuntimeError(f"Server failed:\n{err.decode(errors='replace')[-500:]}")
    yield BASE_URL
    proc.kill()
    proc.wait(timeout=5)


@pytest.fixture(scope="session")
def pw_browser():
    from playwright.sync_api import sync_playwright
    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=True)
    yield browser
    browser.close()
    pw.stop()


def _make_logged_in_page(pw_browser, server, viewport):
    """Create a page at given viewport, auto-logged in via test mode."""
    ctx = pw_browser.new_context(viewport=viewport)
    page = ctx.new_page()
    # In test mode, /api/auth/me auto-sets session → checkAuth() → showLibrary()
    page.goto(server)
    try:
        page.wait_for_selector(".topbar", timeout=8000)
    except Exception:
        # Fallback: call test-login endpoint then reload
        page.evaluate("""
            fetch('/api/test-login', {method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({})
            })
        """)
        page.reload()
        page.wait_for_selector(".topbar", timeout=5000)
    return page, ctx


@pytest.fixture(scope="session")
def phone_page(pw_browser, server):
    page, ctx = _make_logged_in_page(pw_browser, server, PHONE)
    yield page
    ctx.close()

@pytest.fixture(scope="session")
def tablet_page(pw_browser, server):
    page, ctx = _make_logged_in_page(pw_browser, server, TABLET)
    yield page
    ctx.close()

@pytest.fixture(scope="session")
def desktop_page(pw_browser, server):
    page, ctx = _make_logged_in_page(pw_browser, server, DESKTOP)
    yield page
    ctx.close()
