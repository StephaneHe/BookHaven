"""3.6 — PUT /api/books/<id>/epub-locations: unbounded disk write (up to the
512 MB request cap, repeatable) for any book_id, even nonexistent ones."""
import os
from unittest.mock import MagicMock, patch

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


def _client_with_book(exists):
    mock_conn = MagicMock()
    mock_conn.execute.return_value.fetchone.return_value = (
        {"id": 1} if exists else None)
    return patch.object(bookhaven.database, "get_db", return_value=mock_conn)


def test_put_locations_unknown_book_404(client, tmp_path):
    with _client_with_book(exists=False), \
         patch.object(bookhaven, "EPUB_LOC_CACHE_DIR", str(tmp_path)):
        resp = client.put("/api/books/999/epub-locations",
                          json={"locations": "[]"})
    assert resp.status_code == 404
    assert not os.path.exists(tmp_path / "999.json")


def test_put_locations_oversized_413(client, tmp_path):
    huge = "x" * (bookhaven.MAX_EPUB_LOCATIONS_BYTES + 1)
    with _client_with_book(exists=True), \
         patch.object(bookhaven, "EPUB_LOC_CACHE_DIR", str(tmp_path)):
        resp = client.put("/api/books/1/epub-locations",
                          json={"locations": huge})
    assert resp.status_code == 413
    assert not os.path.exists(tmp_path / "1.json")


def test_put_locations_valid_roundtrip(client, tmp_path):
    with _client_with_book(exists=True), \
         patch.object(bookhaven, "EPUB_LOC_CACHE_DIR", str(tmp_path)):
        resp = client.put("/api/books/1/epub-locations",
                          json={"locations": '["epubcfi(/6/2)"]'})
        assert resp.status_code == 200
        got = client.get("/api/books/1/epub-locations")
    assert got.get_json()["locations"] == '["epubcfi(/6/2)"]'
