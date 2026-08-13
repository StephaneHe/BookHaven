"""3.11 — api_optimize_epub carried an `except subprocess.TimeoutExpired`
although it never spawns a subprocess (pure zipfile rewrite): dead code that
suggests a timeout protection which does not exist."""
import inspect
import os

os.environ.setdefault("BOOKHAVEN_SECRET_KEY", "test-secret-key-32chars-minimum!")
os.environ.setdefault("BOOKHAVEN_TEST_MODE", "1")
os.environ.setdefault("BOOKHAVEN_ENV", "development")

import bookhaven  # noqa: E402


def test_optimize_epub_has_no_dead_subprocess_handler():
    src = inspect.getsource(bookhaven.api_optimize_epub)
    assert "subprocess" not in src, (
        "api_optimize_epub does not call subprocess; the TimeoutExpired "
        "handler is unreachable dead code")
