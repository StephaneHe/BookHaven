"""Step 4: SQL aggregation of top-level collections (Q1).

_query_top_collections must return exactly what the legacy Python loop over
every row produced -- book_count, has_children, the "A, B +N" author string
(N counts the empty author!) -- with cover_book_id canonicalised to MIN(id)
(documented divergence, plan section 4.8).
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

import grouped_fixtures  # noqa: E402
from test_books_grouped_parity import FILTER_COMBOS  # noqa: E402


@pytest.fixture()
def conn(tmp_path):
    db_path = str(tmp_path / "test.db")
    with patch.object(config, "DB_PATH", db_path):
        database.init_db()
        c = database.get_db()
        grouped_fixtures.populate(c)
        yield c
        c.close()


def naive_top_collections(conn, where, params):
    """Reference implementation: the legacy row-by-row loop, in the test."""
    rows = conn.execute(
        f"SELECT id, author, collection_path, has_cover FROM books {where}", params
    ).fetchall()
    groups = {}
    for r in rows:
        cp = r["collection_path"]
        if not cp:
            continue
        top = cp.split("/")[0]
        g = groups.setdefault(top, {"count": 0, "covers": [], "authors": set(),
                                    "has_children": False})
        g["count"] += 1
        if "/" in cp:
            g["has_children"] = True
        if r["has_cover"]:
            g["covers"].append(r["id"])
        g["authors"].add(r["author"])

    items, singles = [], []
    for top in sorted(groups):
        g = groups[top]
        if g["count"] == 1 and not g["has_children"]:
            singles.append(top)
            continue
        author_str = ", ".join(sorted(a for a in g["authors"] if a)[:2])
        if len(g["authors"]) > 2:
            author_str += f" +{len(g['authors'])-2}"
        items.append({
            "type": "collection",
            "title": top,
            "collection_path": top,
            "book_count": g["count"],
            "cover_book_id": min(g["covers"]) if g["covers"] else 0,
            "author": author_str,
        })
    return items, singles


@pytest.mark.parametrize("filters", FILTER_COMBOS)
def test_q1_matches_the_row_by_row_reference(conn, filters):
    kwargs = dict(filters)
    kwargs["fmt"] = kwargs.pop("format", "")
    where, params = bookhaven._grouped_where(**kwargs)
    items, singles = bookhaven._query_top_collections(conn, where, params)
    exp_items, exp_singles = naive_top_collections(conn, where, params)
    assert sorted(items, key=lambda i: i["title"]) == exp_items
    assert sorted(singles) == exp_singles


def test_single_book_groups_are_not_collections(conn):
    where, params = bookhaven._grouped_where()
    items, singles = bookhaven._query_top_collections(conn, where, params)
    assert "Solo 0" in singles and "Solo 7" in singles
    assert not any(i["title"].startswith("Solo ") for i in items)
    # a one-book group WITH children stays a collection
    assert "Collection 00" in {i["title"] for i in items}


def test_author_plus_n_counts_the_empty_author(conn):
    """Legacy used a set() that included '' -- the +N must keep counting it."""
    where, params = bookhaven._grouped_where()
    items, _ = bookhaven._query_top_collections(conn, where, params)
    many = next(i for i in items if i["title"] == "Many Authors")
    n_authors = len(grouped_fixtures.AUTHORS)  # includes one ""
    assert many["author"].endswith(f" +{n_authors - 2}")
    # a comma-bearing author must not be split into two
    assert "Doe, John" in many["author"] or "Ecrivain, Anne-Marie" in many["author"]


def test_collection_of_anonymous_books_has_empty_author(conn):
    where, params = bookhaven._grouped_where()
    items, _ = bookhaven._query_top_collections(conn, where, params)
    anon = next(i for i in items if i["title"] == "Anonymes")
    assert anon["author"] == ""      # one distinct author (''), so no +N either


def test_cover_book_id_is_the_smallest_id_with_a_cover(conn):
    where, params = bookhaven._grouped_where()
    items, _ = bookhaven._query_top_collections(conn, where, params)
    for item in items:
        expected = conn.execute(
            "SELECT COALESCE(MIN(id), 0) AS m FROM books"
            " WHERE has_cover AND (collection_path = ? OR collection_path LIKE ? || '/%')",
            (item["title"], item["title"]),
        ).fetchone()["m"]
        assert item["cover_book_id"] == expected, item["title"]


def test_empty_database_yields_nothing(tmp_path):
    with patch.object(config, "DB_PATH", str(tmp_path / "empty.db")):
        database.init_db()
        c = database.get_db()
        where, params = bookhaven._grouped_where()
        assert bookhaven._query_top_collections(c, where, params) == ([], [])
        c.close()
