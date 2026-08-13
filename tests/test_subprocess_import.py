"""3.13 — `except subprocess.TimeoutExpired` in api_optimize_epub referenced a
module that was only imported locally in another function: any error in the
handler raised NameError instead of the intended 500 JSON response."""
import os
import pytest
from unittest.mock import patch

os.environ.setdefault("BOOKHAVEN_SECRET_KEY", "test-secret-key-32chars-minimum!")
os.environ.setdefault("BOOKHAVEN_TEST_MODE", "1")
os.environ.setdefault("BOOKHAVEN_ENV", "development")

import bookhaven  # noqa: E402


@pytest.fixture()
def client():
    bookhaven.app.config["TESTING"] = True
    with bookhaven.app.test_client() as c:
        yield c


def _boom(*args, **kwargs):
    raise ValueError("db down")


def test_optimize_epub_error_returns_500_json(client):
    with patch.object(bookhaven.database, "get_db", _boom):
        resp = client.post("/api/books/1/optimize-epub")
    assert resp.status_code == 500
    assert resp.get_json()["error"] == "Internal server error"


def test_subprocess_imported_at_module_level():
    import subprocess
    assert getattr(bookhaven, "subprocess", None) is subprocess
