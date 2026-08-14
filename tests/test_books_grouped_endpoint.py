"""Step 7: the /api/books/grouped ROUTE itself, on the new implementation.

These go through the Flask client, so they cover the argument parsing, the
clamping, the auth gate and the error handling on top of the payload builder.
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

import grouped_fixtures        # noqa: E402
from sql_spy import SpyConnection  # noqa: E402


def spy_connection():
    """A wrapped connection the route can use for one request."""
    return SpyConnection(database.get_db())


def _client(db_path, populate=None):
    bookhaven.app.config["TESTING"] = True
    patcher = patch.object(config, "DB_PATH", db_path)
    patcher.start()
    database.init_db()
    if populate:
        conn = database.get_db()
        populate(conn)
        conn.close()
    return patcher


@pytest.fixture()
def client(tmp_path):
    patcher = _client(str(tmp_path / "full.db"), grouped_fixtures.populate)
    with bookhaven.app.test_client() as c:
        yield c
    patcher.stop()


@pytest.fixture()
def empty_client(tmp_path):
    patcher = _client(str(tmp_path / "empty.db"))
    with bookhaven.app.test_client() as c:
        yield c
    patcher.stop()


def test_requires_a_session(empty_client):
    with patch.object(bookhaven, "TEST_MODE", False):
        assert empty_client.get("/api/books/grouped").status_code == 401


def test_empty_database(empty_client):
    data = empty_client.get("/api/books/grouped").get_json()
    assert data == {"items": [], "total": 0, "page": 1, "per_page": 50,
                    "pages": 0, "prefix": ""}


def test_single_standalone_book(tmp_path):
    def one(conn):
        conn.execute("INSERT INTO books (path, filename, title, format)"
                     " VALUES ('/a/Solo.epub', 'Solo.epub', 'Solo', 'epub')")
        conn.commit()
    patcher = _client(str(tmp_path / "one.db"), one)
    try:
        with bookhaven.app.test_client() as c:
            data = c.get("/api/books/grouped").get_json()
        assert data["total"] == 1 and data["pages"] == 1
        assert data["items"][0]["type"] == "book"
        assert data["items"][0]["formats"] == [{"id": 1, "format": "epub"}]
    finally:
        patcher.stop()


def test_single_book_collection_is_shown_as_a_book(tmp_path):
    def one(conn):
        conn.execute("INSERT INTO books (path, filename, title, format,"
                     " collection_path) VALUES ('/a/S.epub', 'S.epub', 'S',"
                     " 'epub', 'Lonely')")
        conn.commit()
    patcher = _client(str(tmp_path / "lonely.db"), one)
    try:
        with bookhaven.app.test_client() as c:
            data = c.get("/api/books/grouped").get_json()
        assert [i["type"] for i in data["items"]] == ["book"]
        assert data["items"][0]["collection_path"] == "Lonely"
    finally:
        patcher.stop()


def test_page_beyond_the_end_is_empty_but_total_is_right(client):
    first = client.get("/api/books/grouped", query_string={"per_page": 50}).get_json()
    data = client.get("/api/books/grouped",
                      query_string={"per_page": 50, "page": 9999}).get_json()
    assert data["items"] == []
    assert data["total"] == first["total"] and data["pages"] == first["pages"]


def test_per_page_one_walks_the_same_listing(client):
    wide = client.get("/api/books/grouped", query_string={"per_page": 5}).get_json()
    narrow = [client.get("/api/books/grouped",
                         query_string={"per_page": 1, "page": p}).get_json()["items"][0]
              for p in range(1, 6)]
    assert narrow == wide["items"]
    assert wide["pages"] == (wide["total"] + 4) // 5


def test_filter_with_no_result(client):
    data = client.get("/api/books/grouped",
                      query_string={"search": "zzz-nothing-here"}).get_json()
    assert data == {"items": [], "total": 0, "page": 1, "per_page": 50,
                    "pages": 0, "prefix": ""}


def test_format_filter_promotes_another_primary(client):
    """The filter runs before grouping, so a pdf can become the primary even
    though an epub exists."""
    unfiltered = client.get("/api/books/grouped",
                            query_string={"search": "Triple Play"}).get_json()
    item = next(i for i in unfiltered["items"] if i["title"].startswith("Triple Play"))
    assert item["format"] == "epub"

    filtered = client.get("/api/books/grouped",
                          query_string={"search": "Triple Play", "format": "pdf"}).get_json()
    item = next(i for i in filtered["items"] if i["title"].startswith("Triple Play"))
    assert item["format"] == "pdf" and len(item["formats"]) == 1


def test_prefix_is_echoed_back(client):
    data = client.get("/api/books/grouped",
                      query_string={"prefix": "Collection 02"}).get_json()
    assert data["prefix"] == "Collection 02"
    assert data["items"]


def test_unknown_prefix_returns_an_empty_listing(client):
    data = client.get("/api/books/grouped",
                      query_string={"prefix": "Nope"}).get_json()
    assert data["items"] == [] and data["total"] == 0


def test_internal_error_is_generic(client):
    with patch.object(bookhaven, "_books_grouped_payload",
                      side_effect=RuntimeError("boom")):
        resp = client.get("/api/books/grouped")
    assert resp.status_code == 500
    assert resp.get_json() == {"error": "Internal server error"}


def test_the_only_select_star_is_the_page_hydration(client):
    """The route must not fall back to loading the table (step 8 measures the
    row counts; this one pins the shape of the SQL)."""
    spy = spy_connection()
    with patch.object(bookhaven.database, "get_db", lambda: spy):
        client.get("/api/books/grouped", query_string={"per_page": 10})

    stars = spy.select_star_queries()
    assert len(stars) == 1, [q["sql"] for q in stars]
    assert stars[0]["sql"].startswith("SELECT * FROM books WHERE id IN (")
    assert len(stars[0]["params"]) <= 10      # at most one id per page slot
    assert stars[0]["rows"] <= 10
