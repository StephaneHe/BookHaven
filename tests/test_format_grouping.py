"""3.12 — Characterization of _group_format_variants / _base_filename.

bookhaven.py defined both functions TWICE (first pair grouped by
(base, grandparent folder), second pair by base filename only). Python keeps
the last definition, so the active semantic is: group by base filename alone,
epub preferred as primary. These tests pin that behaviour so the dead first
pair can be removed safely.
"""
import os

os.environ.setdefault("BOOKHAVEN_SECRET_KEY", "test-secret-key-32chars-minimum!")
os.environ.setdefault("BOOKHAVEN_TEST_MODE", "1")
os.environ.setdefault("BOOKHAVEN_ENV", "development")

import bookhaven  # noqa: E402


def test_base_filename_strips_known_extensions():
    assert bookhaven._base_filename("Dune.epub") == "Dune"
    assert bookhaven._base_filename("Dune.PDF") == "Dune"
    assert bookhaven._base_filename("Dune.txt") == "Dune.txt"


def test_variants_grouped_by_base_filename_epub_primary():
    books = [
        {"id": 1, "filename": "Dune.pdf", "format": "pdf", "path": "/a/PDF/Dune.pdf"},
        {"id": 2, "filename": "Dune.epub", "format": "epub", "path": "/a/EPUB/Dune.epub"},
        {"id": 3, "filename": "Other.pdf", "format": "pdf", "path": "/a/Other.pdf"},
    ]
    result = bookhaven._group_format_variants(books)
    assert len(result) == 2
    dune = next(b for b in result if b["id"] == 2)
    assert dune["format"] == "epub"
    assert [f["format"] for f in dune["formats"]] == ["epub", "pdf"]


def test_grouping_ignores_parent_folder():
    """Active semantic: same base filename groups even across folders
    (sibling CBR/ and PDF/ dirs hold variants of the same book)."""
    books = [
        {"id": 1, "filename": "X.cbr", "format": "cbr", "path": "/lib/A/CBR/X.cbr"},
        {"id": 2, "filename": "X.pdf", "format": "pdf", "path": "/lib/B/PDF/X.pdf"},
    ]
    result = bookhaven._group_format_variants(books)
    assert len(result) == 1
    assert result[0]["id"] == 1  # cbr outranks pdf


def test_only_one_definition_of_each_helper():
    """The dead first definitions must be gone from the source."""
    import inspect
    src = inspect.getsource(bookhaven)
    assert src.count("def _base_filename(") == 1
    assert src.count("def _group_format_variants(") == 1
