"""Continue Reading suggests the next volume of a series once the previous one is finished.

Books split one file per chapter/volume (scanlated webtoons, tomes) used to drop
out of Continue Reading when finished, with nothing pointing at the next one.
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

# id, title, series, series_index
BOOKS = [
    (1, "Chapitre 1", "Saga", 1.0),
    (2, "Chapitre 2", "Saga", 2.0),
    (3, "Chapitre 10", "Saga", 10.0),     # numeric order, not alphabetical
    (4, "Tome 1", "Other", 1.0),
    (5, "Tome 2", "Other", 2.0),
    (6, "Standalone", "", 0.0),
]


@pytest.fixture()
def client(tmp_path):
    db_path = str(tmp_path / "test.db")
    bookhaven.app.config["TESTING"] = True
    with patch.object(config, "DB_PATH", db_path):
        database.init_db()
        conn = database.get_db()
        for bid, title, series, idx in BOOKS:
            conn.execute("INSERT INTO books (id, path, filename, title, format, series, series_index) "
                         "VALUES (?, ?, ?, ?, 'cbz', ?, ?)", (bid, f"/a/{bid}.cbz", f"{bid}.cbz", title, series, idx))
        conn.commit()
        conn.close()
        with bookhaven.app.test_client() as c:
            yield c


def put(client, bid, progress, location="0"):
    assert client.put(f"/api/books/{bid}/progress",
                      json={"progress": progress, "current_location": location}).status_code == 200


def set_last_read(bid, ts):
    conn = database.get_db()
    conn.execute("UPDATE reading_progress SET last_read = ? WHERE book_id = ?", (ts, bid))
    conn.commit()
    conn.close()


def listing(client):
    return client.get("/api/continue-reading").get_json()


def ids(client):
    return [b["id"] for b in listing(client)]


def test_finishing_a_volume_suggests_the_next_one(client):
    put(client, 1, 50)
    assert ids(client) == [1]
    put(client, 1, 100, "19")                    # finished
    rows = listing(client)
    assert [b["id"] for b in rows] == [2]
    assert rows[0]["up_next"] == 1 and rows[0]["progress"] == 0 and rows[0]["current_location"] == ""


def test_next_volume_follows_series_index_not_title(client):
    put(client, 2, 100)
    assert ids(client) == [3]                    # "Chapitre 10" after "Chapitre 2"


def test_no_suggestion_after_the_last_volume(client):
    put(client, 3, 100)
    assert ids(client) == []


def test_opening_the_suggestion_turns_it_into_normal_progress(client):
    put(client, 1, 100)
    put(client, 2, 10, "1")
    rows = listing(client)
    assert [b["id"] for b in rows] == [2]
    assert not rows[0].get("up_next") and rows[0]["progress"] == 10


def test_unfinished_book_of_the_series_blocks_the_suggestion(client):
    put(client, 2, 30)                           # reading chapter 2
    put(client, 1, 100)                          # then re-read chapter 1 to the end
    set_last_read(1, "2030-01-02 00:00:00")
    assert ids(client) == [2]                    # chapter 2 listed once, as in progress


def test_dismissing_a_suggestion_keeps_it_away(client):
    put(client, 1, 100)
    assert ids(client) == [2]
    assert client.delete("/api/books/2/progress").status_code == 200
    assert ids(client) == []


def test_removing_an_in_progress_book_does_not_resurrect_it(client):
    put(client, 1, 100)
    set_last_read(1, "2030-01-01 00:00:00")
    put(client, 2, 40)
    set_last_read(2, "2030-01-02 00:00:00")
    assert client.delete("/api/books/2/progress").status_code == 200
    assert ids(client) == []
    data = client.get("/api/books/2/progress").get_json()
    assert data["progress"] == 0 and data["current_location"] == ""


def test_series_are_independent_and_ordered_by_last_read(client):
    put(client, 1, 100)
    set_last_read(1, "2030-01-01 00:00:00")
    put(client, 4, 100)
    set_last_read(4, "2030-01-03 00:00:00")
    put(client, 6, 20)
    set_last_read(6, "2030-01-02 00:00:00")
    assert ids(client) == [5, 6, 2]


def test_book_without_series_gets_no_suggestion(client):
    put(client, 6, 100)
    assert ids(client) == []
