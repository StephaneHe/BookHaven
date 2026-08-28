"""Optimized conftest - reuse pages across tests in same viewport."""
import os
import sys
import time
import subprocess
import pytest
from urllib.request import urlopen
from urllib.error import URLError

# Repo root = parent of this tests/ directory. Keeps the harness portable
# instead of hard-coding a machine-specific checkout path.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Interpreter: BOOKHAVEN_PYTHON overrides, else reuse the one running pytest.
PYTHON = os.environ.get("BOOKHAVEN_PYTHON", sys.executable)
SERVER_SCRIPT = os.path.join(_REPO_ROOT, "bookhaven.py")
# Test port: override with BOOKHAVEN_TEST_PORT if 8098 is taken by another
# local service. Use 127.0.0.1 (not "localhost", which some browsers resolve
# to IPv6 ::1 while waitress binds IPv4).
TEST_PORT = int(os.environ.get("BOOKHAVEN_TEST_PORT", "8098"))
BASE_URL = f"http://127.0.0.1:{TEST_PORT}"

@pytest.fixture(autouse=True)
def _config_module_identity():
    """Fail loudly if a test leaves sys.modules['config'] diverged.

    database.py and bookhaven.py hold a reference to the config module object
    captured at their import. If a test replaces sys.modules['config'] with a
    fresh object, a later test that monkeypatches config.DB_PATH patches only
    the new object -- database.py keeps writing to the real library database.
    That silently polluted data/bookhaven.db once already.
    """
    yield
    import sys as _sys
    cfg = _sys.modules.get("config")
    db = _sys.modules.get("database")
    if cfg is not None and db is not None:
        assert db.config is cfg, (
            "sys.modules['config'] diverged from database.config -- a test "
            "replaced the config module and DB redirection will silently fail"
        )


PHONE = {"width": 375, "height": 667}
TABLET = {"width": 768, "height": 1024}
DESKTOP = {"width": 1280, "height": 800}


def _wait_for_server(url, timeout=15):
    """Wait until *our* BookHaven answers on `url`.

    Probes /api/version and requires a JSON version back, so a foreign service
    already bound to the test port (a false 200 on "/") can't be mistaken for a
    started server — that used to yield a live URL pointing at the wrong app.
    """
    import json
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urlopen(url + "/api/version", timeout=2) as r:
                if json.loads(r.read().decode("utf-8")).get("version"):
                    return True
        except (URLError, OSError, ValueError):
            pass
        time.sleep(0.3)
    return False


@pytest.fixture(scope="session")
def server():
    # Kill any lingering python processes on test port
    env = os.environ.copy()
    env["BOOKHAVEN_TEST_MODE"] = "1"
    env["BOOKHAVEN_ENV"] = "development"
    env["BOOKHAVEN_PORT"] = str(TEST_PORT)
    proc = subprocess.Popen(
        [PYTHON, SERVER_SCRIPT],
        cwd=_REPO_ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if not _wait_for_server(BASE_URL):
        proc.kill()
        out, err = proc.communicate(timeout=5)
        raise RuntimeError(
            f"BookHaven did not answer on {BASE_URL} (port {TEST_PORT} may be "
            f"in use by another service — set BOOKHAVEN_TEST_PORT to a free "
            f"port).\n{err.decode(errors='replace')[-500:]}")
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
