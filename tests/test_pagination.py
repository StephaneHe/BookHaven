"""3.17 — page/per_page/n query args are validated and clamped (no 500 on
garbage input, no unbounded per_page)."""
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
        with bookhaven.app.test_client() as c:
            yield c


@pytest.mark.parametrize("url", ["/api/books", "/api/books/grouped", "/api/collections"])
def test_non_numeric_page_does_not_500(client, url):
    resp = client.get(url, query_string={"page": "abc", "per_page": "xyz"})
    assert resp.status_code == 200


@pytest.mark.parametrize("url", ["/api/books", "/api/books/grouped", "/api/collections"])
def test_per_page_clamped(client, url):
    data = client.get(url, query_string={"per_page": "999999"}).get_json()
    assert data["per_page"] <= 200


@pytest.mark.parametrize("url", ["/api/books", "/api/books/grouped", "/api/collections"])
def test_negative_page_clamped_to_one(client, url):
    data = client.get(url, query_string={"page": "-5"}).get_json()
    assert data["page"] == 1


def test_recent_n_validated(client):
    resp = client.get("/api/books/recent", query_string={"n": "abc"})
    assert resp.status_code == 200
    assert resp.get_json() == {"books": []}
    resp = client.get("/api/books/recent-by-category", query_string={"n": "-3"})
    assert resp.status_code == 200
