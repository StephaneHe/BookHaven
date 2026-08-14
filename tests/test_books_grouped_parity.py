"""Characterization harness for GET /api/books/grouped.

Step 1 of the v2.3.0 optimisation: pin the current behaviour before touching
anything. `tests/legacy_grouped.py` holds a frozen copy of the v2.2.0
implementation; the first test proves that copy is a faithful oracle by
comparing it to the live route. The later steps compare the new SQL-backed
implementation to that same oracle.
"""
import json
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


# Filter combinations exercised by every parity matrix.
FILTER_COMBOS = [
    {},
    {"category": "Comics"},
    {"genre": "Fantasy"},
    {"author": "Zola"},
    {"format": "epub"},
    {"format": "pdf"},
    {"search": "Multi"},
    {"search": "Collection 0"},
    {"category": "Books", "format": "pdf"},
    {"genre": "Policier", "author": "Hugo"},
    {"search": "no-such-book-anywhere"},
]

PAGINATIONS = [
    {"page": 1, "per_page": 50},
    {"page": 2, "per_page": 7},
    {"page": 1, "per_page": 1},
    {"page": 9999, "per_page": 50},
]


def jsonable(payload):
    """Round-trip through JSON so Row-derived values compare like the API's."""
    return json.loads(json.dumps(payload))


@pytest.fixture()
def env(tmp_path):
    """Client + patched DB_PATH, holding the deterministic fixture library."""
    db_path = str(tmp_path / "test.db")
    bookhaven.app.config["TESTING"] = True
    with patch.object(config, "DB_PATH", db_path):
        database.init_db()
        conn = database.get_db()
        grouped_fixtures.populate(conn)
        conn.close()
        with bookhaven.app.test_client() as c:
            yield c


def oracle(**kwargs):
    conn = database.get_db()
    try:
        return jsonable(legacy_books_grouped_payload(conn, **kwargs))
    finally:
        conn.close()


@pytest.mark.parametrize("filters", FILTER_COMBOS)
@pytest.mark.parametrize("pagination", PAGINATIONS)
def test_frozen_oracle_matches_the_live_route(env, filters, pagination):
    """The frozen copy really is the current endpoint, byte for byte."""
    query = dict(filters, **pagination)
    resp = env.get("/api/books/grouped", query_string=query)
    assert resp.status_code == 200
    kwargs = dict(query)
    kwargs["fmt"] = kwargs.pop("format", "")
    assert resp.get_json() == oracle(**kwargs)


@pytest.mark.parametrize("prefix", [
    "Collection 01",             # depth-1 browse
    "Collection 02/Saison 1",    # depth-2 browse
    "Variants Inside",
    "Nope does not exist",
])
def test_frozen_oracle_matches_the_live_route_with_prefix(env, prefix):
    resp = env.get("/api/books/grouped", query_string={"prefix": prefix, "per_page": 50})
    assert resp.status_code == 200
    assert resp.get_json() == oracle(prefix=prefix, per_page=50)


def test_envelope_shape(env):
    data = env.get("/api/books/grouped", query_string={"per_page": 10}).get_json()
    assert set(data) == {"items", "total", "page", "per_page", "pages", "prefix"}
    assert data["page"] == 1 and data["per_page"] == 10
    assert data["pages"] == (data["total"] + 9) // 10
    assert len(data["items"]) == 10


def test_items_sorted_by_lowercased_title(env):
    data = env.get("/api/books/grouped", query_string={"per_page": 200}).get_json()
    titles = [(i.get("title") or "").lower() for i in data["items"]]
    assert titles == sorted(titles)


def test_collection_items_carry_exactly_the_contract_keys(env):
    data = env.get("/api/books/grouped", query_string={"per_page": 200}).get_json()
    cols = [i for i in data["items"] if i["type"] == "collection"]
    assert cols, "fixture must produce collections"
    for c in cols:
        assert set(c) == {"type", "title", "collection_path", "book_count",
                          "cover_book_id", "author"}


def test_book_items_carry_all_columns_plus_formats(env):
    data = env.get("/api/books/grouped", query_string={"per_page": 200}).get_json()
    books = [i for i in data["items"] if i["type"] == "book"]
    assert books, "fixture must produce books"
    for b in books:
        assert {"id", "path", "filename", "title", "author", "genre", "format",
                "description", "collection_path", "formats"} <= set(b)
        assert b["format"] == b["formats"][0]["format"]


def test_fixture_covers_the_tricky_cases(env):
    """Guard the fixture itself: the edge cases the parity tests rely on."""
    data = env.get("/api/books/grouped", query_string={"per_page": 200,
                                                       "search": "Multi"}).get_json()
    multi = [i for i in data["items"] if len(i.get("formats", [])) > 1]
    assert len(multi) >= 10, "need multi-format groups"

    all_items = env.get("/api/books/grouped",
                        query_string={"per_page": 200, "page": 1}).get_json()["items"]
    all_items += env.get("/api/books/grouped",
                         query_string={"per_page": 200, "page": 2}).get_json()["items"]
    all_items += env.get("/api/books/grouped",
                         query_string={"per_page": 200, "page": 3}).get_json()["items"]
    titles = [(i.get("title") or "").lower() for i in all_items]
    assert titles.count("tie title") >= 2, "need title.lower() ties"
    # Dune.epub and dune.pdf must stay two separate groups (case-sensitive base)
    dunes = [i for i in all_items if (i.get("title") or "").lower().startswith("dune")]
    assert len(dunes) == 2
    # single-book collections are rendered as books
    solos = [i for i in all_items if (i.get("title") or "").startswith("Solo Collection")]
    assert solos and all(i["type"] == "book" for i in solos)
