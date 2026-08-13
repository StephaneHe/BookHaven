"""2.4 — Session cookie hardening: SameSite=Lax (CSRF: cross-site form POSTs
no longer carry the session) and HttpOnly explicit."""
import os
import pytest

os.environ.setdefault("BOOKHAVEN_SECRET_KEY", "test-secret-key-32chars-minimum!")
os.environ.setdefault("BOOKHAVEN_TEST_MODE", "1")
os.environ.setdefault("BOOKHAVEN_ENV", "development")

import bookhaven  # noqa: E402


@pytest.fixture()
def client():
    bookhaven.app.config["TESTING"] = True
    with bookhaven.app.test_client() as c:
        yield c


def test_cookie_flags_configured():
    assert bookhaven.app.config["SESSION_COOKIE_SAMESITE"] == "Lax"
    assert bookhaven.app.config["SESSION_COOKIE_HTTPONLY"] is True


def test_session_cookie_has_samesite_and_httponly(client):
    resp = client.post("/api/test-login", json={})
    cookie = resp.headers.get("Set-Cookie", "")
    assert "SameSite=Lax" in cookie
    assert "HttpOnly" in cookie
