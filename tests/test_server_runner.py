"""2.7 — Production serving must go through waitress, not the Flask dev server."""
import os
from unittest.mock import patch

import pytest

os.environ.setdefault("BOOKHAVEN_SECRET_KEY", "test-secret-key-32chars-minimum!")
os.environ.setdefault("BOOKHAVEN_TEST_MODE", "1")
os.environ.setdefault("BOOKHAVEN_ENV", "development")

import bookhaven  # noqa: E402
import config     # noqa: E402


def test_run_server_uses_waitress_without_tls():
    calls = {}

    def fake_serve(app, **kwargs):
        calls["app"] = app
        calls.update(kwargs)

    with patch("waitress.serve", fake_serve), \
         patch.object(bookhaven.app, "run") as flask_run:
        bookhaven._run_server(ssl_ctx=None)

    assert calls.get("app") is bookhaven.app
    assert calls.get("host") == config.HOST
    assert calls.get("port") == config.PORT
    flask_run.assert_not_called()


def test_waitress_body_size_matches_upload_cap():
    """3.8 — waitress default max_request_body_size (~1 GB) spools the whole
    body to disk before Flask's 512 MB cap can reject it: align both caps."""
    calls = {}

    def fake_serve(app, **kwargs):
        calls.update(kwargs)

    with patch("waitress.serve", fake_serve):
        bookhaven._run_server(ssl_ctx=None)

    assert calls.get("max_request_body_size") == config.MAX_UPLOAD_BYTES


def test_run_server_refuses_tls():
    """3.7 — server.crt/server.key used to silently re-route serving through
    the Werkzeug dev server, undoing the waitress fix. Startup must refuse
    with a clear message instead (TLS belongs in a reverse proxy)."""
    with patch("waitress.serve") as serve, \
         patch.object(bookhaven.app, "run") as flask_run, \
         pytest.raises(SystemExit) as exc:
        bookhaven._run_server(ssl_ctx=("crt", "key"))
    serve.assert_not_called()
    flask_run.assert_not_called()
    assert "reverse proxy" in str(exc.value)
