"""Optimized conftest - reuse pages across tests in same viewport."""
import os
import tempfile

# Never write into the production log (bookhaven.log is what incident diagnosis
# reads): the app and the UI test server log to a temp file instead.
os.environ.setdefault("BOOKHAVEN_LOG_FILE", os.path.join(tempfile.gettempdir(), "bookhaven-tests.log"))
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
REAL_DB_PATH = os.path.join(_REPO_ROOT, "data", "bookhaven.db")


def _free_local_port():
    """Ask the OS for a currently free TCP port on 127.0.0.1."""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# Test port: BOOKHAVEN_TEST_PORT pins it; otherwise the OS picks a free one, so
# a foreign service on a fixed port (8098 is taken on the dev machine) can't
# break the UI suite. Use 127.0.0.1 (not "localhost", which some browsers
# resolve to IPv6 ::1 while waitress binds IPv4).
TEST_PORT = int(os.environ.get("BOOKHAVEN_TEST_PORT") or _free_local_port())
BASE_URL = f"http://127.0.0.1:{TEST_PORT}"

# The UI test server runs bookhaven's app against a *snapshot* of the library
# database, never the live data/bookhaven.db: running `bookhaven.py` directly
# would init/migrate the real DB and start the media-enrichment worker, which
# writes metadata into it (and races the production server on port 8097).
# Mirrors bookhaven.py's __main__ block minus the side effects on shared state
# (legacy-path migration, orphan-upload purge, media worker).
_SERVER_BOOTSTRAP = r"""
import sys
sys.path.insert(0, sys.argv[1])
import config
config.DB_PATH = sys.argv[2]
import bookhaven
bookhaven.database.init_db()
bookhaven._run_server(None)
"""


def _snapshot_db(dest):
    """Copy the real DB to `dest` through SQLite's backup API (read-only on the
    source, WAL-consistent). An empty DB is used if there is no library."""
    import sqlite3
    dst = sqlite3.connect(dest)
    try:
        if os.path.exists(REAL_DB_PATH):
            src = sqlite3.connect(f"file:{REAL_DB_PATH}?mode=ro", uri=True)
            try:
                src.backup(dst)
            finally:
                src.close()
    finally:
        dst.close()

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
def server(tmp_path_factory):
    work = tmp_path_factory.mktemp("bookhaven_ui_server")
    db_copy = str(work / "bookhaven.db")
    _snapshot_db(db_copy)
    log_path = work / "server.log"
    env = os.environ.copy()
    env["BOOKHAVEN_TEST_MODE"] = "1"
    env["BOOKHAVEN_ENV"] = "development"
    env["BOOKHAVEN_PORT"] = str(TEST_PORT)
    # Output goes to a file, not a PIPE nobody drains: a full pipe buffer
    # would eventually block the server mid-suite.
    log = open(log_path, "wb")
    proc = subprocess.Popen(
        [PYTHON, "-c", _SERVER_BOOTSTRAP, _REPO_ROOT, db_copy],
        cwd=_REPO_ROOT,
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    try:
        if not _wait_for_server(BASE_URL):
            proc.kill()
            proc.wait(timeout=5)
            log.close()
            tail = log_path.read_bytes().decode(errors="replace")[-800:]
            raise RuntimeError(
                f"BookHaven did not answer on {BASE_URL} (port {TEST_PORT} may "
                f"be in use by another service — unset BOOKHAVEN_TEST_PORT to "
                f"pick a free port automatically).\n{tail}")
        yield BASE_URL
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)
        if not log.closed:
            log.close()


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

@pytest.fixture()
def fresh_phone_page(pw_browser, server):
    """Throwaway phone page for tests that mutate the DOM (forcing a view
    open, injecting an image) so the shared session `phone_page` stays clean
    and test order doesn't matter."""
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
