"""P0-A: database.writing() must release the write lock even when the unit fails.

Reproduces the recurring lock: a failed write (FK violation on progress to a
deleted book) used to leave the transaction open until cyclic GC, blocking every
other writer. With database.writing() the connection is always closed, so the
next writer succeeds immediately — WITHOUT a gc.collect().

Runs entirely on a temp DB; never touches the live library.
"""
import os
import gc
import sqlite3
import tempfile
import pytest


@pytest.fixture()
def temp_db(monkeypatch):
    import config
    d = tempfile.mkdtemp()
    path = os.path.join(d, "test.db")
    monkeypatch.setattr(config, "DB_PATH", path)
    import database
    conn = database.get_db()
    conn.executescript(
        "CREATE TABLE books(id INTEGER PRIMARY KEY);"
        "CREATE TABLE reading_progress("
        "  user_id TEXT, book_id INTEGER REFERENCES books(id),"
        "  progress REAL, UNIQUE(user_id, book_id));"
        "INSERT INTO books VALUES (1);"
    )
    conn.commit()
    conn.close()
    return database


def _can_write(database):
    """True if a fresh connection can immediately grab the write lock."""
    w = database.get_db()
    try:
        w.execute("BEGIN IMMEDIATE")
        w.rollback()
        return True
    except sqlite3.OperationalError:
        return False
    finally:
        w.close()


def test_failed_write_does_not_leak_the_lock(temp_db):
    database = temp_db
    gc.disable()
    try:
        # A write unit that fails on an FK violation (progress to a missing book).
        with pytest.raises(sqlite3.IntegrityError):
            with database.writing() as conn:
                conn.execute(
                    "INSERT INTO reading_progress(user_id, book_id, progress) VALUES ('u', 999, 5)"
                )
        # Without database.writing(), this needed gc.collect() to pass. It must
        # now be writable straight away.
        assert _can_write(database), "write lock leaked after a failed write unit"
    finally:
        gc.enable()


def test_successful_write_commits(temp_db):
    database = temp_db
    with database.writing() as conn:
        conn.execute(
            "INSERT INTO reading_progress(user_id, book_id, progress) VALUES ('u', 1, 42)"
        )
    with __import__("contextlib").closing(database.get_db()) as conn:
        row = conn.execute(
            "SELECT progress FROM reading_progress WHERE user_id='u' AND book_id=1"
        ).fetchone()
    assert row is not None and row[0] == 42


def test_rollback_on_error_leaves_no_partial_row(temp_db):
    database = temp_db
    with pytest.raises(sqlite3.IntegrityError):
        with database.writing() as conn:
            conn.execute("INSERT INTO reading_progress(user_id, book_id, progress) VALUES ('u', 1, 10)")
            conn.execute("INSERT INTO reading_progress(user_id, book_id, progress) VALUES ('u', 1, 10)")  # UNIQUE violation
    with __import__("contextlib").closing(database.get_db()) as conn:
        n = conn.execute("SELECT COUNT(*) FROM reading_progress").fetchone()[0]
    assert n == 0, "first insert should have rolled back with the failing unit"
