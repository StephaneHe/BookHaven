"""2.3 — Bounded request size + streamed book files (no full read into RAM)."""
import os
import pytest
from unittest.mock import MagicMock, patch

os.environ.setdefault("BOOKHAVEN_SECRET_KEY", "test-secret-key-32chars-minimum!")
os.environ.setdefault("BOOKHAVEN_TEST_MODE", "1")
os.environ.setdefault("BOOKHAVEN_ENV", "development")

import bookhaven  # noqa: E402
import config     # noqa: E402


@pytest.fixture()
def client():
    bookhaven.app.config["TESTING"] = True
    with bookhaven.app.test_client() as c:
        yield c


def test_max_content_length_configured():
    assert bookhaven.app.config["MAX_CONTENT_LENGTH"] == config.MAX_UPLOAD_BYTES
    assert config.MAX_UPLOAD_BYTES > 0


def test_oversized_upload_rejected_413(client):
    original = bookhaven.app.config["MAX_CONTENT_LENGTH"]
    bookhaven.app.config["MAX_CONTENT_LENGTH"] = 1024
    try:
        import io
        resp = client.post(
            "/api/upload/analyze",
            data={"file": (io.BytesIO(b"x" * 4096), "big.epub", "application/epub+zip")},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 413
    finally:
        bookhaven.app.config["MAX_CONTENT_LENGTH"] = original


def test_book_file_supports_range_streaming(client, tmp_path):
    """send_file on the path with conditional=True → 206 partial responses.

    The old code read the whole file into a BytesIO (bookhaven.py:1097-1103),
    which loaded multi-hundred-MB comics fully into RAM per request and could
    not answer Range requests.
    """
    book_file = tmp_path / "book.epub"
    book_file.write_bytes(b"A" * 10000)
    mock_conn = MagicMock()
    mock_conn.execute.return_value.fetchone.return_value = {
        "path": str(book_file), "format": "epub", "filename": "book.epub",
    }
    with patch.object(bookhaven.database, "get_db", return_value=mock_conn):
        resp = client.get("/api/books/1/file", headers={"Range": "bytes=0-99"})
    assert resp.status_code == 206
    assert len(resp.data) == 100


def test_book_file_not_read_into_ram_by_handler(client, tmp_path):
    """The handler must delegate to send_file(path) instead of open().read().

    bookhaven.py:1097-1103 pre-read the whole file into a BytesIO, loading
    multi-hundred-MB comics fully into RAM on every request. Patching open()
    inside the bookhaven module proves the handler no longer reads the file
    itself (werkzeug streams it from the path in chunks).
    """
    book_file = tmp_path / "book.epub"
    book_file.write_bytes(b"C" * 8192)
    mock_conn = MagicMock()
    mock_conn.execute.return_value.fetchone.return_value = {
        "path": str(book_file), "format": "epub", "filename": "book.epub",
    }

    def no_open(*args, **kwargs):
        raise AssertionError("api_book_file must not open()+read() the book itself")

    with patch.object(bookhaven.database, "get_db", return_value=mock_conn), \
         patch("bookhaven.open", no_open, create=True):
        resp = client.get("/api/books/1/file")
    assert resp.status_code == 200
    assert resp.data == b"C" * 8192


def test_book_file_full_download_still_works(client, tmp_path):
    book_file = tmp_path / "book.epub"
    book_file.write_bytes(b"B" * 5000)
    mock_conn = MagicMock()
    mock_conn.execute.return_value.fetchone.return_value = {
        "path": str(book_file), "format": "epub", "filename": "book.epub",
    }
    with patch.object(bookhaven.database, "get_db", return_value=mock_conn):
        resp = client.get("/api/books/1/file")
    assert resp.status_code == 200
    assert resp.data == b"B" * 5000
    assert resp.content_type.startswith("application/epub+zip")
