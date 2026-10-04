"""2.10 — /api/books/<id>/cover and /api/enrichment/status require a session."""
import os
import pytest
from unittest.mock import MagicMock, patch

os.environ.setdefault("BOOKHAVEN_SECRET_KEY", "test-secret-key-32chars-minimum!")
os.environ.setdefault("BOOKHAVEN_TEST_MODE", "1")
os.environ.setdefault("BOOKHAVEN_ENV", "development")

import bookhaven  # noqa: E402


@pytest.fixture()
def client():
    bookhaven.app.config["TESTING"] = True
    with bookhaven.app.test_client() as c:
        yield c


@pytest.fixture()
def login_enforced():
    """Force login-required mode for the duration of one test.

    Since 2.7.16 (passwordless entry) the default -- BOOKHAVEN_LOGIN_REQUIRED
    unset -- makes _ensure_session_user() auto-select the default user, so a
    session-less request is *not* rejected. The 401 contract only holds when
    login is required and the TEST_MODE bypass is off; set both explicitly so
    the result never depends on the environment or on test order.
    """
    with patch.object(bookhaven, "TEST_MODE", False), \
         patch.object(bookhaven.config, "LOGIN_REQUIRED", True):
        yield


def test_cover_requires_auth(client, login_enforced):
    resp = client.get("/api/books/1/cover")
    assert resp.status_code == 401


def test_enrichment_status_requires_auth(client, login_enforced):
    resp = client.get("/api/enrichment/status")
    assert resp.status_code == 401


def test_cover_works_with_session(client):
    mock_conn = MagicMock()
    mock_conn.execute.return_value.fetchone.return_value = None
    with client.session_transaction() as sess:
        sess["user_id"] = "u1"
        sess["user_name"] = "U"
    with patch.object(bookhaven, "TEST_MODE", False), \
         patch.object(bookhaven.database, "get_db", return_value=mock_conn):
        resp = client.get("/api/books/1/cover")
    assert resp.status_code == 200
    assert resp.content_type.startswith("image/svg+xml")
