"""2.6 — Internal exception details must not be echoed to the client."""
import os
import time
import pytest
from unittest.mock import MagicMock, patch

os.environ.setdefault("BOOKHAVEN_SECRET_KEY", "test-secret-key-32chars-minimum!")
os.environ.setdefault("BOOKHAVEN_TEST_MODE", "1")
os.environ.setdefault("BOOKHAVEN_ENV", "development")

import bookhaven  # noqa: E402

SECRET = "SECRET-DETAIL-c0ffee"


@pytest.fixture()
def client():
    bookhaven.app.config["TESTING"] = True
    with bookhaven.app.test_client() as c:
        yield c


def _boom(*args, **kwargs):
    raise ValueError(SECRET)


@pytest.mark.parametrize("method,url,kwargs", [
    ("get", "/api/books", {}),
    ("get", "/api/books/1", {}),
    ("put", "/api/books/1/progress", {"json": {"progress": 10}}),
    ("put", "/api/books/1/genre", {"json": {"genre": "SF"}}),
    ("delete", "/api/books/1/series", {}),
    ("get", "/api/books/grouped", {}),
    ("get", "/api/collections", {}),
])
def test_exception_detail_not_leaked(client, method, url, kwargs):
    with patch.object(bookhaven.database, "get_db", _boom):
        resp = getattr(client, method)(url, **kwargs)
    assert resp.status_code == 500
    assert SECRET.encode() not in resp.data
    assert b"error" in resp.data


def _wait_until(pred, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if pred():
            return True
        time.sleep(0.01)
    return False


def test_scan_status_does_not_leak_exception_detail(client):
    """3.4 — scan_state['message'] = f'Error: {e}' leaked str(e) via /api/scan/status."""
    bookhaven.scan_state.update({"running": False, "message": "", "cancel": False})
    with patch.object(bookhaven.scanner, "scan_library", _boom):
        assert client.post("/api/scan").status_code == 200
        assert _wait_until(lambda: not bookhaven.scan_state["running"]
                           and bookhaven.scan_state["message"])
    resp = client.get("/api/scan/status")
    assert SECRET.encode() not in resp.data
    assert b"rror" in resp.data  # still signals an error state


def test_convert_status_does_not_leak_exception_detail(client):
    """3.4 — convert_state['error'] = str(e) leaked via /api/convert/status."""
    bookhaven.convert_state.update({"running": False, "error": None, "message": ""})
    book = {"id": 1, "path": "x.pdf", "filename": "x.pdf", "title": "T",
            "author": "A", "genre": "", "format": "pdf", "page_count": 3}
    mock_conn = MagicMock()
    mock_conn.execute.return_value.fetchone.return_value = book
    with patch.object(bookhaven.database, "get_db", return_value=mock_conn), \
         patch.object(bookhaven.subprocess, "Popen", _boom):
        assert client.post("/api/books/1/convert-epub").status_code == 200
        assert _wait_until(lambda: not bookhaven.convert_state["running"]
                           and bookhaven.convert_state["error"])
    resp = client.get("/api/convert/status")
    assert SECRET.encode() not in resp.data
    bookhaven.convert_state.update({"running": False, "error": None, "message": ""})
