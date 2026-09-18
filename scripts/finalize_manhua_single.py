#!/usr/bin/env python3
"""Switch the manhua from 217 per-chapter entries to ONE continuous book.

- Backs up the DB (SQLite online backup).
- Removes the 217 per-chapter rows (series 'Sir, Don't Show Off') and their
  cached cover files, plus the per-chapter CBZ folder in the library.
- Registers the single combined CBZ (Comics\\Sir, Don't Show Off.cbz) as one
  book so it reads continuously in the comic reader.

Idempotent-ish: safe to re-run; it re-derives state from disk/DB each time.
"""
import os
import sys
import time
import shutil
import hashlib
import sqlite3
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config          # noqa: E402
import database        # noqa: E402
import scanner         # noqa: E402

SERIES = "Sir, Don't Show Off"
COMICS = os.path.join(config.BOOKS_ROOT, "Comics")
PER_CHAPTER_DIR = os.path.join(COMICS, SERIES)
COMBINED = os.path.join(COMICS, "Sir, Don't Show Off.cbz")
IMG_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp")


def backup_db():
    dst = os.path.join(config.BASE_DIR, "backup",
                       f"bookhaven_pre-manhua-single_{time.strftime('%Y%m%d_%H%M%S')}.db")
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    s = sqlite3.connect(config.DB_PATH); d = sqlite3.connect(dst)
    with d:
        s.backup(d)
    s.close(); d.close()
    print("DB backup ->", dst)


def main():
    if not os.path.exists(COMBINED):
        print("Combined CBZ missing — run combine_manhua_cbz.py first."); return 1
    backup_db()
    conn = database.get_db()
    conn.execute("PRAGMA busy_timeout=120000")   # wait out the live server's writes

    # Prepare the combined book's cover/metadata BEFORE taking the write lock.
    with zipfile.ZipFile(COMBINED) as zf:
        imgs = sorted(n for n in zf.namelist()
                      if os.path.splitext(n)[1].lower() in IMG_EXTS)
        cover_data = zf.read(imgs[0]) if imgs else None
    has_cover = 1 if scanner._extract_cover(COMBINED, ".cbz", cover_data) else 0

    rows = conn.execute("SELECT id, path FROM books WHERE series = ?", (SERIES,)).fetchall()

    # DB mutations in one transaction, retried against transient lock contention.
    for attempt in range(6):
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("DELETE FROM books WHERE series = ?", (SERIES,))
            if not conn.execute("SELECT 1 FROM books WHERE path = ?", (COMBINED,)).fetchone():
                conn.execute("""
                    INSERT INTO books (path, filename, title, author, genre, series,
                      series_index, category, format, file_size, has_cover,
                      page_count, description, collection_path)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (COMBINED, os.path.basename(COMBINED), SERIES, "", "Comics", "",
                      0, "Comics", "cbz", os.path.getsize(COMBINED), has_cover,
                      len(imgs), "Manhua - 217 chapters read as one continuous book.", ""))
            conn.commit()
            break
        except sqlite3.OperationalError as e:
            conn.rollback()
            if attempt == 5:
                raise
            print(f"  DB busy ({e}); retry {attempt + 1}/5 ...")
            time.sleep(5)
    print(f"Removed {len(rows)} per-chapter rows; inserted single book ({len(imgs)} pages, cover={has_cover})")

    # Now that the rows are gone, clean their orphaned cover-cache files and the
    # per-chapter CBZ folder.
    for r in rows:
        h = hashlib.md5(r["path"].encode()).hexdigest()
        cover = os.path.join(config.COVER_CACHE_DIR, f"{h}.jpg")
        try:
            if os.path.exists(cover):
                os.remove(cover)
        except OSError:
            pass
    if os.path.isdir(PER_CHAPTER_DIR):
        shutil.rmtree(PER_CHAPTER_DIR, ignore_errors=True)
        print(f"Removed folder {PER_CHAPTER_DIR}")

    bid = conn.execute("SELECT id, page_count FROM books WHERE path = ?", (COMBINED,)).fetchone()
    conn.close()
    print(f"Book id={bid['id']} page_count={bid['page_count']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
