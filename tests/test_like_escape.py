"""2.11 — % and _ in user search/filter input are literals, not LIKE wildcards."""
import os
import pytest
from unittest.mock import patch

os.environ.setdefault("BOOKHAVEN_SECRET_KEY", "test-secret-key-32chars-minimum!")
os.environ.setdefault("BOOKHAVEN_TEST_MODE", "1")
os.environ.setdefault("BOOKHAVEN_ENV", "development")

import bookhaven  # noqa: E402
import config     # noqa: E402
import database   # noqa: E402


@pytest.fixture()
def client(tmp_path):
    db_path = str(tmp_path / "test.db")
    bookhaven.app.config["TESTING"] = True
    with patch.object(config, "DB_PATH", db_path):
        database.init_db()
        conn = database.get_db()
        rows = [
            ("/t/a.epub", "a.epub", "Save 50% today", "Ann"),
            ("/t/b.epub", "b.epub", "Save 50x today", "Bob"),
            ("/t/c.epub", "c.epub", "AI_Book", "Cid"),
            ("/t/d.epub", "d.epub", "AIxBook", "Dan"),
        ]
        for path, fn, title, author in rows:
            conn.execute(
                "INSERT INTO books (path, filename, title, author, format) "
                "VALUES (?, ?, ?, ?, 'epub')", (path, fn, title, author))
        conn.commit()
        conn.close()
        with bookhaven.app.test_client() as c:
            yield c


def test_percent_is_literal_in_search(client):
    data = client.get("/api/books", query_string={"search": "50%"}).get_json()
    titles = [b["title"] for b in data["books"]]
    assert titles == ["Save 50% today"]


def test_underscore_is_literal_in_search(client):
    data = client.get("/api/books", query_string={"search": "AI_"}).get_json()
    titles = [b["title"] for b in data["books"]]
    assert titles == ["AI_Book"]


def test_normal_search_still_works(client):
    data = client.get("/api/books", query_string={"search": "Save"}).get_json()
    assert data["total"] == 2


def test_author_filter_escapes_wildcards(client):
    data = client.get("/api/books", query_string={"author": "A_n"}).get_json()
    assert data["total"] == 0
    data = client.get("/api/books", query_string={"author": "Ann"}).get_json()
    assert data["total"] == 1
