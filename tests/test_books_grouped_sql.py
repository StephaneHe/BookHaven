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


# ── Step 3: SQL equivalents of the Python grouping helpers ───────────────────

FILENAMES = [
    "Dune.epub",
    "Dune.PDF",
    "Dune.txt",
    "Dune.epub.epub",
    ".epub",
    "epub",
    "Livre.Épub",          # accented "extension" -> not stripped
    "a%b_c.cbz",                 # LIKE wildcards inside the DATA are literal
    "100%.pdf",
    "Tome 1.2.mobi",
    "noext",
    "中文小说.epub",   # non-ASCII base: length() counts chars
    "École buissonnière.cbr",
    "Trailing dot.",
    "UPPER.EPUB",
    "Mixed.CbZ",
]


def test_sql_base_expr_matches_python_base_filename(conn):
    for name in FILENAMES:
        got = conn.execute(
            f"SELECT {bookhaven._SQL_BASE_EXPR} AS base FROM (SELECT ? AS filename)",
            (name,),
        ).fetchone()["base"]
        assert got == bookhaven._base_filename(name), name


def test_sql_prio_expr_matches_format_priority(conn):
    for f in ["epub", "cbz", "cbr", "pdf", "mobi", "txt", "EPUB", "Pdf", "", "xyz"]:
        got = conn.execute(
            f"SELECT {bookhaven._SQL_PRIO_EXPR} AS prio FROM (SELECT ? AS format)",
            (f,),
        ).fetchone()["prio"]
        assert got == bookhaven.FORMAT_PRIORITY.get(f, 9), f


def test_sql_base_grouping_is_case_sensitive_like_the_python_dict(conn):
    """Dune.epub and dune.pdf are two groups: only the extension is case-blind."""
    rows = conn.execute(
        f"SELECT {bookhaven._SQL_BASE_EXPR} AS base"
        " FROM (SELECT 'Dune.epub' AS filename UNION ALL SELECT 'dune.pdf')"
        " GROUP BY base"
    ).fetchall()
    assert sorted(r["base"] for r in rows) == ["Dune", "dune"]


def test_sqlite_supports_json_group_array_distinct(conn):
    """Guard-rail: the collection aggregation needs json1 (SQLite >= 3.39)."""
    assert sqlite3.sqlite_version_info >= (3, 39), sqlite3.sqlite_version
    row = conn.execute(
        "SELECT json_group_array(DISTINCT a) AS j FROM"
        " (SELECT 'Doe, John' AS a UNION ALL SELECT '' UNION ALL SELECT 'Doe, John')"
    ).fetchone()
    import json
    assert sorted(json.loads(row["j"])) == ["", "Doe, John"]
