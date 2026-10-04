"""Book detail exposes the webtoon reading mode and the series neighbours.

webtoon = always the continuous vertical reader (manhua / manhwa / webtoon), set
by the book flag, a webtoon category, or any flagged book of the same series.
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

# id, title, format, category, series, series_index, reading_mode
BOOKS = [
    (1, "Chapitre 1", "cbz", "Comics", "Saga", 1.0, "webtoon"),
    (2, "Chapitre 2", "cbz", "Comics", "Saga", 2.0, ""),          # inherits from the series
    (3, "Chapitre 10", "cbz", "Comics", "Saga", 10.0, ""),
    (4, "Manhua", "cbz", "Webcomics", "", 0.0, ""),               # webtoon category
    (5, "Batman 1", "cbz", "Comics", "Batman", 1.0, ""),          # classic comic
    (6, "Novel", "epub", "Books", "Saga", 3.0, "webtoon"),        # not an image format
]


@pytest.fixture()
def client(tmp_path):
    db_path = str(tmp_path / "test.db")
    bookhaven.app.config["TESTING"] = True
    with patch.object(config, "DB_PATH", db_path):
        database.init_db()
        conn = database.get_db()
        for bid, title, fmt, cat, series, idx, mode in BOOKS:
            conn.execute("INSERT INTO books (id, path, filename, title, format, category, series, "
                         "series_index, reading_mode) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                         (bid, f"/a/{bid}.{fmt}", f"{bid}.{fmt}", title, fmt, cat, series, idx, mode))
        conn.commit()
        conn.close()
        with bookhaven.app.test_client() as c:
            yield c


def detail(client, bid):
    return client.get(f"/api/books/{bid}").get_json()


@pytest.mark.parametrize("bid,expected", [(1, True), (2, True), (3, True), (4, True), (5, False), (6, False)])
def test_webtoon_flag(client, bid, expected):
    assert detail(client, bid)["webtoon"] is expected


def test_series_neighbours_follow_series_index(client):
    d1, d2, d3 = detail(client, 1), detail(client, 2), detail(client, 3)
    assert d1["series_prev"] is None and d1["series_next"]["id"] == 2
    assert d2["series_prev"]["id"] == 1 and d2["series_next"]["id"] == 6      # index 3 (epub) sits between
    assert d3["series_prev"]["id"] == 6 and d3["series_next"] is None
    assert set(d2["series_next"]) == {"id", "title", "format"}


def test_no_neighbours_without_series(client):
    d = detail(client, 4)
    assert d["series_prev"] is None and d["series_next"] is None


def test_init_db_creates_reading_mode_on_existing_db(tmp_path):
    db_path = str(tmp_path / "old.db")
    with patch.object(config, "DB_PATH", db_path):
        database.init_db()
        database.init_db()          # idempotent
        conn = database.get_db()
        cols = {r[1] for r in conn.execute("PRAGMA table_info(books)")}
        conn.close()
    assert {"reading_mode", "sub_series", "sub_series_2"} <= cols
