"""Reading-progress endpoint contract — the cross-device sync the Android app
now relies on (DownloadRepository.resolveProgress).

The web reader saves the position as a reflow-independent EPUB CFI. The bug was
that the Android app restored only its stale LOCAL copy and never pulled the
server's newer position, so a book read on the web later opened on the phone at
the START of the web session. The app fix reads GET /api/books/<id>/progress and
adopts it when the local row is already synced; these tests pin the server side
of that contract: a CFI round-trips exactly, later writes win, and last_read is
exposed.
"""
import os
import pytest
from unittest.mock import patch

os.environ.setdefault("BOOKHAVEN_SECRET_KEY", "test-secret-key-32chars-minimum!")
os.environ.setdefault("BOOKHAVEN_TEST_MODE", "1")
os.environ.setdefault("BOOKHAVEN_ENV", "development")

import bookhaven  # noqa: E402
import config     # noqa: E402
import database   # noqa: E402

CFI = "epubcfi(/6/14!/4/2[chap-01]/10/34/1:0)"


@pytest.fixture()
def client(tmp_path):
    db_path = str(tmp_path / "test.db")
    bookhaven.app.config["TESTING"] = True
    with patch.object(config, "DB_PATH", db_path):
        database.init_db()
        conn = database.get_db()
        conn.execute("INSERT INTO books (id, path, filename, title, format) "
                     "VALUES (1, '/a/B.epub', 'B.epub', 'B', 'epub')")
        conn.commit()
        conn.close()
        with bookhaven.app.test_client() as c:
            yield c


def put(client, progress, location):
    return client.put("/api/books/1/progress",
                      json={"progress": progress, "current_location": location})


def test_cfi_round_trips_exactly(client):
    assert put(client, 1, CFI).status_code == 200
    data = client.get("/api/books/1/progress").get_json()
    assert data["current_location"] == CFI
    assert data["progress"] == 1


def test_get_exposes_last_read(client):
    """The Android sync uses last_read to reason about freshness."""
    put(client, 5, CFI)
    data = client.get("/api/books/1/progress").get_json()
    assert data.get("last_read"), "GET must return a last_read timestamp"


def test_latest_write_wins_across_devices(client):
    """Server is the shared source of truth: a second reader's newer CFI
    overwrites the first, which is exactly what lets the app catch up to the web."""
    put(client, 1, "epubcfi(/6/8!/4/2/2/1:0)")     # web session start
    later = "epubcfi(/6/20!/4/2/50/1:0)"             # after reading on the web
    put(client, 3, later)
    data = client.get("/api/books/1/progress").get_json()
    assert data["current_location"] == later


def test_missing_progress_reads_empty(client):
    data = client.get("/api/books/1/progress").get_json()
    assert data == {"progress": 0, "current_location": ""}
