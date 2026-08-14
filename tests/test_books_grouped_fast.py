"""Parity matrix: the SQL-backed implementation vs the frozen v2.2.0 oracle.

Step 5 covers the top-level listing, step 6 the prefix browsing. The two
tolerated divergences (plan section 4.8) are handled by `normalize`, and
nothing else is allowed to differ -- payloads are compared whole, list order
included.
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

import grouped_fixtures                               # noqa: E402
from legacy_grouped import legacy_books_grouped_payload  # noqa: E402
from grouped_compare import normalize                    # noqa: E402
from test_books_grouped_parity import FILTER_COMBOS, PAGINATIONS  # noqa: E402


@pytest.fixture()
def conn(tmp_path):
    db_path = str(tmp_path / "test.db")
    with patch.object(config, "DB_PATH", db_path):
        database.init_db()
        c = database.get_db()
        grouped_fixtures.populate(c)
        yield c
        c.close()


def assert_parity(conn, **kwargs):
    new = bookhaven._books_grouped_payload(conn, **kwargs)
    old = legacy_books_grouped_payload(conn, **kwargs)
    assert normalize(new) == normalize(old)
    # the tolerated divergences must not hide a changed item count
    assert new["total"] == old["total"] and new["pages"] == old["pages"]
    return new, old


@pytest.mark.parametrize("filters", FILTER_COMBOS)
@pytest.mark.parametrize("pagination", PAGINATIONS)
def test_top_level_parity_matrix(conn, filters, pagination):
    kwargs = dict(filters, **pagination)
    kwargs["fmt"] = kwargs.pop("format", "")
    assert_parity(conn, **kwargs)


def test_top_level_parity_on_every_page(conn):
    """Walk the whole listing 7 items at a time: nothing may shift pages."""
    total = bookhaven._books_grouped_payload(conn, per_page=7)["total"]
    for page in range(1, (total + 6) // 7 + 1):
        assert_parity(conn, page=page, per_page=7)


PREFIXES = [
    "Collection 01",              # depth 2 underneath
    "Collection 02",              # depth 3 underneath
    "Collection 02/Saison 1",     # browsing a sub-level
    "Collection 00",              # flat collection: only books at this level
    "Variants Inside",            # multi-format variants at this level
    "Solo 0",                     # a one-book collection
    "Nope does not exist",
    "Collection 01/Saison 9",     # existing top, missing sub-level
]


@pytest.mark.parametrize("prefix", PREFIXES)
@pytest.mark.parametrize("pagination", PAGINATIONS)
def test_prefix_parity_matrix(conn, prefix, pagination):
    assert_parity(conn, prefix=prefix, **pagination)


@pytest.mark.parametrize("prefix", PREFIXES[:5])
@pytest.mark.parametrize("filters", FILTER_COMBOS)
def test_prefix_parity_under_filters(conn, prefix, filters):
    kwargs = dict(filters)
    kwargs["fmt"] = kwargs.pop("format", "")
    assert_parity(conn, prefix=prefix, per_page=50, **kwargs)


@pytest.mark.parametrize("prefix", ["100% Comics", "Under_score"])
def test_prefix_wildcard_quirk_is_reproduced(conn, prefix):
    """Risk #9: the legacy LIKE has no ESCAPE, so % and _ in a collection name
    match siblings. Pre-existing behaviour, deliberately kept identical."""
    new, old = assert_parity(conn, prefix=prefix, per_page=50)
    # the sibling's sub-folder leaks in on both sides -- that is the quirk
    assert len(new["items"]) > 1
    assert new["items"] == old["items"]


def test_prefix_browse_lists_sub_collections_and_books(conn):
    new = bookhaven._books_grouped_payload(conn, prefix="Collection 02", per_page=50)
    kinds = {i["type"] for i in new["items"]}
    assert kinds == {"collection"}
    for item in new["items"]:
        assert item["collection_path"].startswith("Collection 02/")


def test_prefix_browse_has_no_single_book_promotion(conn):
    """Unlike the top level, a one-book sub-folder stays a collection."""
    new = bookhaven._books_grouped_payload(conn, prefix="100% Comics", per_page=50)
    subs = [i for i in new["items"] if i["type"] == "collection"]
    assert subs and all(i["book_count"] >= 1 for i in subs)
    assert any(i["book_count"] == 1 for i in subs)


def test_multi_format_group_keeps_the_best_primary(conn):
    new = bookhaven._books_grouped_payload(conn, search="Triple Play", per_page=50)
    item = next(i for i in new["items"] if i["title"].startswith("Triple Play"))
    assert item["format"] == "epub"
    assert [f["format"] for f in item["formats"]] == ["epub", "pdf", "mobi"]


def test_format_filter_changes_the_primary(conn):
    """Legacy behaviour: the filter runs before grouping."""
    new = bookhaven._books_grouped_payload(conn, search="Triple Play", fmt="pdf",
                                        per_page=50)
    item = next(i for i in new["items"] if i["title"].startswith("Triple Play"))
    assert item["format"] == "pdf"
    assert [f["format"] for f in item["formats"]] == ["pdf"]


def test_variant_inside_a_collection_does_not_join_a_standalone(conn):
    """Risk #10: a book living in a multi-book collection is invisible to the
    top-level variant grouping, so it stays a separate item -- exactly as in
    the legacy code, which queried the two sets separately too."""
    new = bookhaven._books_grouped_payload(conn, search="Inside Story", per_page=50)
    by_title = {i["title"]: i for i in new["items"]}
    assert set(by_title) == {"Inside Story standalone", "Variants Inside"}
    assert [f["format"] for f in by_title["Inside Story standalone"]["formats"]] == ["mobi"]


def test_standalone_merges_with_a_single_book_collection_variant(conn):
    """Characterised legacy behaviour: single-book collections are pulled into
    the same query as the standalone books, so their variants DO merge."""
    new = bookhaven._books_grouped_payload(conn, search="Split Base", per_page=50)
    assert [i["title"] for i in new["items"]] == ["Split Base standalone"]
    assert [f["format"] for f in new["items"][0]["formats"]] == ["epub", "pdf"]


def test_case_sensitive_base_filenames_stay_separate(conn):
    new = bookhaven._books_grouped_payload(conn, search="Dune", per_page=50)
    assert sorted(i["title"] for i in new["items"]) == ["Dune", "dune lowercase"]


def test_hydrated_books_carry_every_column(conn):
    new = bookhaven._books_grouped_payload(conn, per_page=50)
    books = [i for i in new["items"] if i["type"] == "book"]
    assert books
    columns = {r[1] for r in conn.execute("PRAGMA table_info(books)")}
    for b in books:
        assert columns <= set(b)
        assert set(b) == columns | {"formats", "type"}


def test_no_internal_keys_leak(conn):
    new = bookhaven._books_grouped_payload(conn, per_page=50)
    assert all("_primary_id" not in i for i in new["items"])


def test_empty_database(tmp_path):
    with patch.object(config, "DB_PATH", str(tmp_path / "empty.db")):
        database.init_db()
        c = database.get_db()
        new = bookhaven._books_grouped_payload(c, per_page=50)
        assert new == legacy_books_grouped_payload(c, per_page=50)
        assert new["total"] == 0 and new["pages"] == 0 and new["items"] == []
        c.close()


def test_single_standalone_book(tmp_path):
    with patch.object(config, "DB_PATH", str(tmp_path / "one.db")):
        database.init_db()
        c = database.get_db()
        c.execute("INSERT INTO books (path, filename, title, format) "
                  "VALUES ('/a/Solo.epub', 'Solo.epub', 'Solo', 'epub')")
        c.commit()
        assert_parity(c, per_page=50)
        c.close()


def test_single_book_collection_without_children(tmp_path):
    """No single_tops at all on one side; and an empty IN () must never be
    emitted (risk #6)."""
    with patch.object(config, "DB_PATH", str(tmp_path / "one_coll.db")):
        database.init_db()
        c = database.get_db()
        c.execute("INSERT INTO books (path, filename, title, format, collection_path)"
                  " VALUES ('/a/Solo.epub', 'Solo.epub', 'Solo', 'epub', 'Only')")
        c.commit()
        new, _ = assert_parity(c, per_page=50)
        assert [i["type"] for i in new["items"]] == ["book"]
        c.close()


def test_no_single_tops_does_not_break_the_query(tmp_path):
    with patch.object(config, "DB_PATH", str(tmp_path / "no_singles.db")):
        database.init_db()
        c = database.get_db()
        for i in range(3):
            c.execute("INSERT INTO books (path, filename, title, format, collection_path)"
                      " VALUES (?, ?, ?, 'epub', 'Coll')",
                      (f"/a/{i}.epub", f"{i}.epub", f"Book {i}"))
        c.commit()
        new, _ = assert_parity(c, per_page=50)
        assert [i["type"] for i in new["items"]] == ["collection"]
        c.close()


def test_more_single_tops_than_the_in_chunk_limit(tmp_path, monkeypatch):
    """Chunked IN () lists must still produce one correctly ordered listing."""
    monkeypatch.setattr(bookhaven, "_IN_CHUNK", 7)
    with patch.object(config, "DB_PATH", str(tmp_path / "many.db")):
        database.init_db()
        c = database.get_db()
        for i in range(40):
            c.execute("INSERT INTO books (path, filename, title, format, collection_path)"
                      " VALUES (?, ?, ?, 'epub', ?)",
                      (f"/a/{i}.epub", f"{i:02d}.epub", f"Book {i:02d}", f"Solo {i:02d}"))
        c.commit()
        new, _ = assert_parity(c, per_page=50)
        assert len(new["items"]) == 40
        c.close()
