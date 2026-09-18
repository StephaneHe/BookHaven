#!/usr/bin/env python3
"""Register the packaged manhua CBZs in BookHaven's database (surgical import).

Adds ONLY the 'Sir, Don't Show Off' chapter CBZs — one row per chapter with an
exact series_index (so 172.5 sorts between 172 and 173) and the cover extracted
via BookHaven's own scanner helper. It does NOT rescan the whole library and
touches no other rows. Idempotent: chapters already present (by path) are left
untouched.

Rows are inserted with genre='Comics', so a later full library scan skips them
(scan_library keeps rows that already have a genre) and this metadata survives.

The live server can pick the rows up immediately — no restart needed (Flask reads
the DB per request; covers are written to the cover cache here).
"""
import os
import re
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config          # noqa: E402  (loads .env, requires BOOKHAVEN_SECRET_KEY)
import database        # noqa: E402
import scanner         # noqa: E402

SERIES = "Sir, Don't Show Off"
SERIES_DIR = os.path.join(config.BOOKS_ROOT, "Comics", SERIES)
IMG_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp")


def chapter_num_from_name(fname):
    """'172 - Chapter 172.5.cbz' -> ('Chapter 172.5', 172.5)."""
    m = re.match(r"^\d{3} - (Chapter ([0-9.]+))\.cbz$", fname)
    if not m:
        return None, None
    return m.group(1), float(m.group(2))


def main():
    if not os.path.isdir(SERIES_DIR):
        print(f"Series dir not found: {SERIES_DIR}")
        return 1
    conn = database.get_db()
    existing = {r["path"] for r in conn.execute("SELECT path FROM books").fetchall()}

    inserted = skipped = failed = 0
    for fname in sorted(os.listdir(SERIES_DIR)):
        if not fname.lower().endswith(".cbz"):
            continue
        path = os.path.join(SERIES_DIR, fname)
        if path in existing:
            skipped += 1
            continue
        title, index = chapter_num_from_name(fname)
        if title is None:
            print(f"skip (unrecognised name): {fname}")
            continue
        try:
            with zipfile.ZipFile(path) as zf:
                imgs = sorted(n for n in zf.namelist()
                              if os.path.splitext(n)[1].lower() in IMG_EXTS)
                cover_data = zf.read(imgs[0]) if imgs else None
            has_cover = 1 if scanner._extract_cover(path, ".cbz", cover_data) else 0
            conn.execute("""
                INSERT INTO books (path, filename, title, author, genre, series,
                  series_index, category, format, file_size, has_cover,
                  page_count, description, collection_path)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (path, fname, title, "", "Comics", SERIES, index, "Comics",
                  "cbz", os.path.getsize(path), has_cover, len(imgs), "", SERIES))
            conn.commit()
            inserted += 1
        except Exception as e:
            failed += 1
            print(f"FAILED {fname}: {e}")

    total = conn.execute(
        "SELECT COUNT(*), MIN(series_index), MAX(series_index) FROM books WHERE series = ?",
        (SERIES,)).fetchone()
    conn.close()
    print("=" * 60)
    print(f"inserted={inserted} skipped(existing)={skipped} failed={failed}")
    print(f"series '{SERIES}': {total[0]} chapters in DB, "
          f"index range {total[1]}..{total[2]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
