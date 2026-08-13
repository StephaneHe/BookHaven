"""2.2 — Optional PIN gate on login: with BOOKHAVEN_PIN set, selecting a user
without the correct PIN must be rejected (LAN exposure without passwords)."""
import os
import pytest
from unittest.mock import MagicMock, patch

os.environ.setdefault("BOOKHAVEN_SECRET_KEY", "test-secret-key-32chars-minimum!")
os.environ.setdefault("BOOKHAVEN_TEST_MODE", "1")
os.environ.setdefault("BOOKHAVEN_ENV", "development")

import bookhaven  # noqa: E402
import config     # noqa: E402


@pytest.fixture(autouse=True)
def reset_limiter():
    """Failed-PIN attempts here must not trip the brute-force lockout."""
    bookhaven._failed_logins.clear()
    yield
    bookhaven._failed_logins.clear()


@pytest.fixture()
def client():
    bookhaven.app.config["TESTING"] = True
    mock_conn = MagicMock()
    mock_conn.execute.return_value.fetchone.return_value = {"id": "u1", "name": "Steph"}
    with patch.object(bookhaven.database, "get_db", return_value=mock_conn):
        with bookhaven.app.test_client() as c:
            yield c


def test_login_without_pin_rejected_when_pin_set(client):
    with patch.object(config, "AUTH_PIN", "4321"):
        resp = client.post("/api/auth/login", json={"username": "Steph"})
    assert resp.status_code == 403


def test_login_with_wrong_pin_rejected(client):
    with patch.object(config, "AUTH_PIN", "4321"):
        resp = client.post("/api/auth/login", json={"username": "Steph", "pin": "0000"})
    assert resp.status_code == 403


def test_login_with_correct_pin_ok(client):
    with patch.object(config, "AUTH_PIN", "4321"):
        resp = client.post("/api/auth/login", json={"username": "Steph", "pin": "4321"})
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True


def test_login_without_pin_ok_when_pin_disabled(client):
    with patch.object(config, "AUTH_PIN", ""):
        resp = client.post("/api/auth/login", json={"username": "Steph"})
    assert resp.status_code == 200


def test_create_user_requires_pin_when_set(client):
    with patch.object(config, "AUTH_PIN", "4321"):
        resp = client.post("/api/auth/users", json={"name": "Mallory"})
    assert resp.status_code == 403


def test_non_ascii_pin_rejected_not_500(client):
    """hmac.compare_digest raises TypeError on non-ASCII str -> was a 500."""
    with patch.object(config, "AUTH_PIN", "4321"):
        resp = client.post("/api/auth/login", json={"username": "Steph", "pin": "12é4"})
    assert resp.status_code == 403


def test_non_string_pin_rejected_not_500(client):
    with patch.object(config, "AUTH_PIN", "4321"):
        for bad in ({"a": 1}, ["4", "3"], 4321, None, True):
            resp = client.post("/api/auth/login", json={"username": "Steph", "pin": bad})
            assert resp.status_code == 403, f"pin={bad!r}"


def test_login_regenerates_session(client):
    """Session fixation: data planted in a pre-login session must not survive
    a successful login — the session is rebuilt from scratch."""
    with client.session_transaction() as s:
        s["planted"] = "attacker-data"
    with patch.object(config, "AUTH_PIN", ""):
        resp = client.post("/api/auth/login", json={"username": "Steph"})
    assert resp.status_code == 200
    with client.session_transaction() as s:
        assert "planted" not in s
        assert s["user_id"] == "u1"


def test_pin_required_endpoint(client):
    with patch.object(config, "AUTH_PIN", "4321"):
        assert client.get("/api/auth/pin-required").get_json()["pin_required"] is True
    with patch.object(config, "AUTH_PIN", ""):
        assert client.get("/api/auth/pin-required").get_json()["pin_required"] is False
