"""Step 8: a row-count budget proving the endpoint no longer loads the table.

The optimisation is only worth having if the number of rows pulled out of
SQLite stays proportional to the number of ITEMS listed, not to the number of
books in the library -- and if the expensive SELECT * (it carries the
description TEXT) is limited to the requested page.

Run against the frozen oracle instead of the new code, every assertion here
fails: on this 10 000-book fixture the legacy path fetches ~13 400 rows, of
which ~3 400 are full ones.
"""
import os
import time
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

N_BOOKS = 10000
PER_PAGE = 50


@pytest.fixture(scope="module")
def large_db(tmp_path_factory):
    db_path = str(tmp_path_factory.mktemp("large") / "large.db")
    with patch.object(config, "DB_PATH", db_path):
        database.init_db()
        conn = database.get_db()
        grouped_fixtures.populate_large(conn, n_books=N_BOOKS)
        conn.close()
        yield db_path


@pytest.fixture()
def measure(large_db):
    """Run one request through a counting connection; return (payload, spy)."""
    def run(**query):
        bookhaven.app.config["TESTING"] = True
        with patch.object(config, "DB_PATH", large_db):
            spy = SpyConnection(database.get_db())
            with patch.object(bookhaven.database, "get_db", lambda: spy), \
                 bookhaven.app.test_client() as c:
                started = time.perf_counter()
                resp = c.get("/api/books/grouped", query_string=query)
                elapsed = time.perf_counter() - started
            assert resp.status_code == 200
            payload = resp.get_json()
            print(f"\n{query} -> {payload['total']} items, "
                  f"{spy.total_rows()} rows read, {len(spy.queries)} queries, "
                  f"{elapsed * 1000:.0f} ms")
            return payload, spy
    return run


def test_the_fixture_is_actually_big(large_db):
    with patch.object(config, "DB_PATH", large_db):
        conn = database.get_db()
        assert conn.execute("SELECT COUNT(*) FROM books").fetchone()[0] == N_BOOKS
        conn.close()


def test_select_star_never_exceeds_one_page(measure):
    payload, spy = measure(per_page=PER_PAGE)
    stars = spy.select_star_queries()
    assert sum(q["rows"] for q in stars) <= PER_PAGE
    assert len(stars) <= 1
    assert len(payload["items"]) == PER_PAGE


def test_rows_read_scale_with_items_not_with_the_library(measure):
    payload, spy = measure(per_page=PER_PAGE)
    budget = payload["total"] + PER_PAGE + 50
    assert spy.total_rows() <= budget, [q["sql"][:80] for q in spy.queries]
    # the real point: far fewer rows than books in the library
    assert spy.total_rows() < N_BOOKS


def test_no_n_plus_one(measure):
    """A per-item query for authors, formats or covers would blow this up."""
    payload, spy = measure(per_page=PER_PAGE)
    assert len(spy.book_queries()) <= 3
    assert len(spy.queries) <= 10


def test_deep_page_costs_the_same_as_the_first(measure):
    first, spy_first = measure(per_page=PER_PAGE, page=1)
    deep, spy_deep = measure(per_page=PER_PAGE, page=first["pages"])
    assert abs(spy_deep.total_rows() - spy_first.total_rows()) <= PER_PAGE


def test_prefix_browsing_stays_within_budget(measure):
    payload, spy = measure(prefix="Coll 0000", per_page=PER_PAGE)
    assert payload["total"] > 0
    assert spy.total_rows() <= payload["total"] + PER_PAGE + 50
    assert sum(q["rows"] for q in spy.select_star_queries()) <= PER_PAGE


def test_filtered_listing_stays_within_budget(measure):
    payload, spy = measure(category="Comics", per_page=PER_PAGE)
    assert spy.total_rows() <= payload["total"] + PER_PAGE + 50
