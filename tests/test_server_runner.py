"""2.7 — Production serving must go through waitress, not the Flask dev server."""
import os
from unittest.mock import patch

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


def test_run_server_keeps_flask_for_tls():
    """waitress has no TLS support: with certs present the existing Flask+ssl
    path must keep working (don't break startup)."""
    with patch("waitress.serve") as serve, \
         patch.object(bookhaven.app, "run") as flask_run:
        bookhaven._run_server(ssl_ctx=("crt", "key"))
    serve.assert_not_called()
    flask_run.assert_called_once()
    assert flask_run.call_args.kwargs.get("ssl_context") == ("crt", "key")
    assert flask_run.call_args.kwargs.get("debug") is False
