"""3.1 — Brute-force guard on the login PIN: BOOKHAVEN_PIN is a 4-digit PIN,
so unlimited attempts from the LAN would fall in seconds. After N failed PIN
attempts from one IP, further logins are locked out — even with the right PIN."""
import os
import time
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("BOOKHAVEN_SECRET_KEY", "test-secret-key-32chars-minimum!")
os.environ.setdefault("BOOKHAVEN_TEST_MODE", "1")
os.environ.setdefault("BOOKHAVEN_ENV", "development")

import bookhaven  # noqa: E402
import config     # noqa: E402


@pytest.fixture()
def client():
    bookhaven.app.config["TESTING"] = True
    mock_conn = MagicMock()
    mock_conn.execute.return_value.fetchone.return_value = {"id": "u1", "name": "Steph"}
    with patch.object(bookhaven.database, "get_db", return_value=mock_conn):
        with bookhaven.app.test_client() as c:
            yield c


@pytest.fixture(autouse=True)
def reset_limiter():
    bookhaven._failed_logins.clear()
    yield
    bookhaven._failed_logins.clear()


def _fail_login(client, n):
    for _ in range(n):
        resp = client.post("/api/auth/login", json={"username": "Steph", "pin": "0000"})
        assert resp.status_code in (403, 429)


def test_lockout_after_repeated_failures_even_with_correct_pin(client):
    with patch.object(config, "AUTH_PIN", "4321"):
        _fail_login(client, bookhaven.LOGIN_MAX_FAILURES)
        resp = client.post("/api/auth/login", json={"username": "Steph", "pin": "4321"})
    assert resp.status_code == 429


def test_lockout_expires(client):
    with patch.object(config, "AUTH_PIN", "4321"):
        _fail_login(client, bookhaven.LOGIN_MAX_FAILURES)
        for entry in bookhaven._failed_logins.values():
            entry["locked_until"] = time.time() - 1
        resp = client.post("/api/auth/login", json={"username": "Steph", "pin": "4321"})
    assert resp.status_code == 200


def test_successful_login_resets_counter(client):
    with patch.object(config, "AUTH_PIN", "4321"):
        _fail_login(client, bookhaven.LOGIN_MAX_FAILURES - 1)
        assert client.post("/api/auth/login",
                           json={"username": "Steph", "pin": "4321"}).status_code == 200
        # counter was reset: a single new failure is a 403, not a lockout
        resp = client.post("/api/auth/login", json={"username": "Steph", "pin": "0000"})
    assert resp.status_code == 403


def test_create_user_is_same_pin_oracle_so_also_limited(client):
    with patch.object(config, "AUTH_PIN", "4321"):
        for _ in range(bookhaven.LOGIN_MAX_FAILURES):
            resp = client.post("/api/auth/users", json={"name": "Mallory", "pin": "0000"})
            assert resp.status_code in (403, 429)
        resp = client.post("/api/auth/login", json={"username": "Steph", "pin": "4321"})
    assert resp.status_code == 429


def test_no_lockout_when_pin_disabled(client):
    with patch.object(config, "AUTH_PIN", ""):
        for _ in range(bookhaven.LOGIN_MAX_FAILURES + 2):
            assert client.post("/api/auth/login",
                               json={"username": "Steph"}).status_code == 200
