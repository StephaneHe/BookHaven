"""3.1 — Brute-force guard on the login PIN: BOOKHAVEN_PIN is a 4-digit PIN,
so unlimited attempts from the LAN would fall in seconds. After N *distinct*
wrong PINs from one IP, further logins are locked out — even with the right PIN.

Distinct-PIN counting (and skipping the empty PIN) is what stops a stuck client
— an app replaying the same wrong/empty body on every launch — from exhausting
the lockout budget of the IP it shares with a human browser."""
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


def _distinct_wrong_pins(n):
    """n distinct wrong 4-digit PINs (none equal to the test's real PIN 4321)."""
    return [f"{i:04d}" for i in range(n)]


def _fail_login(client, n):
    for pin in _distinct_wrong_pins(n):
        resp = client.post("/api/auth/login", json={"username": "Steph", "pin": pin})
        assert resp.status_code in (403, 429)


def test_lockout_after_distinct_failures_even_with_correct_pin(client):
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
        resp = client.post("/api/auth/login", json={"username": "Steph", "pin": "9999"})
    assert resp.status_code == 403


def test_create_user_is_same_pin_oracle_so_also_limited(client):
    with patch.object(config, "AUTH_PIN", "4321"):
        for pin in _distinct_wrong_pins(bookhaven.LOGIN_MAX_FAILURES):
            resp = client.post("/api/auth/users", json={"name": "Mallory", "pin": pin})
            assert resp.status_code in (403, 429)
        resp = client.post("/api/auth/login", json={"username": "Steph", "pin": "4321"})
    assert resp.status_code == 429


def test_no_lockout_when_pin_disabled(client):
    with patch.object(config, "AUTH_PIN", ""):
        for _ in range(bookhaven.LOGIN_MAX_FAILURES + 2):
            assert client.post("/api/auth/login",
                               json={"username": "Steph"}).status_code == 200


# ── The hardening itself: a stuck/misconfigured client must not lock the IP ──

def test_repeating_one_wrong_pin_never_locks_out(client):
    """A stuck client hammering the SAME wrong PIN is not brute-forcing: it must
    not advance the lockout, no matter how many times it retries."""
    with patch.object(config, "AUTH_PIN", "4321"):
        for _ in range(bookhaven.LOGIN_MAX_FAILURES * 4):
            resp = client.post("/api/auth/login", json={"username": "Steph", "pin": "0000"})
            assert resp.status_code == 403  # always 403, never 429
        # the real PIN still works — the IP was never locked
        assert client.post("/api/auth/login",
                           json={"username": "Steph", "pin": "4321"}).status_code == 200


def test_pinless_client_never_locks_out(client):
    """The reported bug: an app built before the PIN existed posts no `pin`.
    Those attempts must not count, so they can't lock a human on the same IP."""
    with patch.object(config, "AUTH_PIN", "4321"):
        for _ in range(bookhaven.LOGIN_MAX_FAILURES * 4):
            resp = client.post("/api/auth/login", json={"username": "Steph"})
            assert resp.status_code == 403
        assert client.post("/api/auth/login",
                           json={"username": "Steph", "pin": "4321"}).status_code == 200


def test_empty_string_pin_never_locks_out(client):
    with patch.object(config, "AUTH_PIN", "4321"):
        for _ in range(bookhaven.LOGIN_MAX_FAILURES * 4):
            resp = client.post("/api/auth/login", json={"username": "Steph", "pin": ""})
            assert resp.status_code == 403
        assert client.post("/api/auth/login",
                           json={"username": "Steph", "pin": "4321"}).status_code == 200


def test_brute_force_across_distinct_pins_still_locks(client):
    """Protection preserved: searching the space (distinct guesses) still trips
    the lockout at the threshold."""
    with patch.object(config, "AUTH_PIN", "4321"):
        for pin in _distinct_wrong_pins(bookhaven.LOGIN_MAX_FAILURES - 1):
            assert client.post("/api/auth/login",
                               json={"username": "Steph", "pin": pin}).status_code == 403
        # the Nth distinct wrong PIN reaches the threshold (still 403 on that call,
        # since the lockout is checked at the START of a request)
        assert client.post("/api/auth/login",
                           json={"username": "Steph", "pin": "8888"}).status_code == 403
        # now the IP is locked: the next attempt — even the correct PIN — is 429
        resp = client.post("/api/auth/login", json={"username": "Steph", "pin": "4321"})
    assert resp.status_code == 429
