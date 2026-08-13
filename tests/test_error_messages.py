"""2.6 — Internal exception details must not be echoed to the client."""
import os
import pytest
from unittest.mock import patch

os.environ.setdefault("BOOKHAVEN_SECRET_KEY", "test-secret-key-32chars-minimum!")
os.environ.setdefault("BOOKHAVEN_TEST_MODE", "1")

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
