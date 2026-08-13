"""3.5 — TOCTOU on the 'running' flags: the flag used to be set inside the
worker thread, after the endpoint's check. Two quick POSTs could both pass the
check and launch two concurrent workers (e.g. two Calibre runs on the same
epub_path). The endpoints must test-and-set the flag before spawning.

The thread is made inert so the flag is only True if the endpoint itself set
it (test-and-set) — with the old code the second POST then also succeeded."""
import os
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("BOOKHAVEN_SECRET_KEY", "test-secret-key-32chars-minimum!")
os.environ.setdefault("BOOKHAVEN_TEST_MODE", "1")
os.environ.setdefault("BOOKHAVEN_ENV", "development")

import bookhaven     # noqa: E402
import media_worker  # noqa: E402


class _InertThread:
    """Stands in for threading.Thread: never actually runs the target."""
    def __init__(self, *args, **kwargs):
        pass

    def start(self):
        pass


@pytest.fixture()
def client():
    bookhaven.app.config["TESTING"] = True
    with bookhaven.app.test_client() as c:
        yield c


def test_scan_start_is_test_and_set(client):
    bookhaven.scan_state.update({"running": False, "message": "", "cancel": False})
    try:
        with patch.object(bookhaven.threading, "Thread", _InertThread):
            assert client.post("/api/scan").status_code == 200
            assert client.post("/api/scan").status_code == 409
    finally:
        bookhaven.scan_state.update({"running": False, "cancel": False})


def test_convert_start_is_test_and_set(client):
    bookhaven.convert_state.update({"running": False, "error": None,
                                    "message": "", "started_at": 0})
    book = {"id": 1, "path": "x.pdf", "filename": "x.pdf", "title": "T",
            "author": "A", "genre": "", "format": "pdf", "page_count": 3}
    mock_conn = MagicMock()
    mock_conn.execute.return_value.fetchone.return_value = book
    try:
        with patch.object(bookhaven.database, "get_db", return_value=mock_conn), \
             patch.object(bookhaven.threading, "Thread", _InertThread):
            assert client.post("/api/books/1/convert-epub").status_code == 200
            assert client.post("/api/books/1/convert-epub").status_code == 409
    finally:
        bookhaven.convert_state.update({"running": False, "started_at": 0})


def test_convert_flag_released_when_precheck_fails(client):
    """Early returns (book not found, ...) must not leave the flag stuck."""
    bookhaven.convert_state.update({"running": False, "started_at": 0})
    mock_conn = MagicMock()
    mock_conn.execute.return_value.fetchone.return_value = None
    with patch.object(bookhaven.database, "get_db", return_value=mock_conn):
        assert client.post("/api/books/1/convert-epub").status_code == 404
    assert bookhaven.convert_state["running"] is False


def test_enrichment_start_is_test_and_set(client):
    media_worker.worker_status["running"] = False
    try:
        with patch.object(media_worker.threading, "Thread", _InertThread):
            assert client.post("/api/enrichment/start").status_code == 200
            assert client.post("/api/enrichment/start").status_code == 409
    finally:
        media_worker.worker_status["running"] = False


def test_media_worker_start_worker_returns_none_when_running():
    media_worker.worker_status["running"] = False
    try:
        with patch.object(media_worker.threading, "Thread", _InertThread):
            assert media_worker.start_worker() is not None
            assert media_worker.start_worker() is None
    finally:
        media_worker.worker_status["running"] = False
