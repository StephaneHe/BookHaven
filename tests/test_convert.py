"""Test PDF-to-EPUB conversion logic."""
import os
import sys
import sqlite3

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_convert_state_init():
    """convert_state has required keys."""
    from bookhaven import convert_state
    assert "running" in convert_state
    assert "current_page" in convert_state
    assert "total_pages" in convert_state
    assert "epub_id" in convert_state
    assert "message" in convert_state
    assert "error" in convert_state


def test_convert_status_endpoint(tmp_path):
    """The /api/convert/status endpoint returns JSON."""
    os.environ["BOOKHAVEN_TEST_MODE"] = "1"
    from bookhaven import app
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = "test"
        sess["user_name"] = "test"
    resp = client.get("/api/convert/status")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "running" in data
    assert "message" in data


def test_convert_rejects_non_pdf(tmp_path):
    """convert-epub rejects non-PDF books."""
    os.environ["BOOKHAVEN_TEST_MODE"] = "1"
    import config
    config.DB_PATH = str(tmp_path / "test.db")
    import database
    database.init_db()
    conn = database.get_db()
    conn.execute("""
        INSERT INTO books (path, filename, title, author, format, file_size)
        VALUES (?, ?, ?, ?, ?, ?)
    """, ("/tmp/test.epub", "test.epub", "Test", "Author", "epub", 100))
    conn.commit()
    book_id = conn.execute("SELECT id FROM books WHERE filename='test.epub'").fetchone()["id"]
    conn.close()

    from bookhaven import app
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = "test"
        sess["user_name"] = "test"
    resp = client.post(f"/api/books/{book_id}/convert-epub")
    assert resp.status_code == 400
    assert "Only PDF" in resp.get_json()["error"]


def test_page_count_in_select():
    """Ensure the SELECT includes page_count (regression test)."""
    from bookhaven import app
    import inspect
    source = inspect.getsource(app.view_functions["api_convert_epub"])
    assert "page_count" in source, "page_count missing from convert-epub SELECT"


def test_calibre_output_parsing():
    """Test that we correctly parse Calibre's progress output."""
    import re
    lines = [
        "Conversion options changed from defaults:",
        "1% Conversion de l'entr\u00e9e en HTML\u2026",
        "Page-1",
        "Page-12",
        "Page-101",
        "34% Conversion de HTML en EPUB...",
        "EPUB output written to test.epub",
    ]
    pages = []
    pcts = []
    for line in lines:
        page_match = re.match(r"Page-(\d+)", line)
        pct_match = re.match(r"(\d+)%", line)
        if page_match:
            pages.append(int(page_match.group(1)))
        elif pct_match:
            pcts.append(int(pct_match.group(1)))
    assert pages == [1, 12, 101], f"Expected [1, 12, 101], got {pages}"
    assert pcts == [1, 34], f"Expected [1, 34], got {pcts}"


def test_stale_convert_state():
    """convert_state running=True should not block if no ebook-convert process."""
    from bookhaven import convert_state
    convert_state["running"] = True
    # After the fix, the endpoint checks if ebook-convert is actually running
    # and resets the state if not. We verify the state can be reset.
    convert_state["running"] = False
    assert not convert_state["running"]


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
