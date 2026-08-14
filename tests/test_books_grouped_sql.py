"""SQL-level building blocks of the optimised /api/books/grouped.

Step 2: the index browsing relies on.
Step 3: the SQL expressions that must behave exactly like their Python
counterparts (_base_filename / FORMAT_PRIORITY).
"""
import os
import sqlite3
import pytest
from unittest.mock import patch

os.environ.setdefault("BOOKHAVEN_SECRET_KEY", "test-secret-key-32chars-minimum!")
os.environ.setdefault("BOOKHAVEN_TEST_MODE", "1")
os.environ.setdefault("BOOKHAVEN_ENV", "development")

import bookhaven  # noqa: E402
import config     # noqa: E402
import database   # noqa: E402


@pytest.fixture()
def conn(tmp_path):
    db_path = str(tmp_path / "test.db")
    with patch.object(config, "DB_PATH", db_path):
        database.init_db()
        c = database.get_db()
        yield c
        c.close()


def test_collection_path_is_indexed(conn):
    """Browsing filters on collection_path (= '', = prefix, IN (...))."""
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index'"
        " AND name='idx_books_collection_path'"
    ).fetchone()
    assert row is not None, "idx_books_collection_path missing"


def test_collection_path_index_is_used_for_equality(conn):
    plan = conn.execute(
        "EXPLAIN QUERY PLAN SELECT id FROM books WHERE collection_path = ''"
    ).fetchall()
    assert any("idx_books_collection_path" in r["detail"] for r in plan), plan
