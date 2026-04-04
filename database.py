"""BookHaven database layer"""
import sqlite3
import os
import config


def get_db():
    """Get a database connection."""
    os.makedirs(os.path.dirname(config.DB_PATH), exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=15000")
    return conn


def init_db():
    """Create tables if they don't exist."""
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS books (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            path TEXT UNIQUE NOT NULL,
            filename TEXT NOT NULL,
            title TEXT NOT NULL,
            author TEXT DEFAULT '',
            genre TEXT DEFAULT '',
            series TEXT DEFAULT '',
            series_index REAL DEFAULT 0,
            category TEXT DEFAULT '',
            format TEXT NOT NULL,
            file_size INTEGER DEFAULT 0,
            has_cover INTEGER DEFAULT 0,
            page_count INTEGER DEFAULT 0,
            description TEXT DEFAULT '',
            collection_path TEXT DEFAULT '',
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            modified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS reading_progress (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            book_id INTEGER NOT NULL,
            progress REAL DEFAULT 0,
            current_location TEXT DEFAULT '',
            last_read TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE,
            UNIQUE(user_id, book_id)
        );

        CREATE INDEX IF NOT EXISTS idx_books_category ON books(category);
        CREATE INDEX IF NOT EXISTS idx_books_author ON books(author);
        CREATE INDEX IF NOT EXISTS idx_books_genre ON books(genre);
        CREATE INDEX IF NOT EXISTS idx_books_format ON books(format);
        CREATE INDEX IF NOT EXISTS idx_books_title ON books(title);
        CREATE INDEX IF NOT EXISTS idx_progress_user ON reading_progress(user_id);
        CREATE INDEX IF NOT EXISTS idx_progress_last_read ON reading_progress(last_read);
    """)
    conn.commit()

    # Migrations: add columns that may not exist in older databases
    try:
        conn.execute("ALTER TABLE books ADD COLUMN collection_path TEXT DEFAULT ''")
        conn.commit()
    except Exception:
        pass  # Column already exists

    try:
        conn.execute("ALTER TABLE books ADD COLUMN genre_locked INTEGER DEFAULT 0")
        conn.commit()
    except Exception:
        pass  # Column already exists

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS user_category_order (
            user_id TEXT PRIMARY KEY,
            category_order TEXT NOT NULL DEFAULT '[]',
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.commit()
    conn.close()
