"""Safe library maintenance operations.

move_folder(): rename/move a folder of the library on disk AND in the database
without re-creating the books. Book ids, reading progress (and so Continue
Reading), series, webtoon flag, genre... live on the rows and are untouched;
only `books.path` changes. `modified_at` is left alone so content_version -- and
every cache keyed on it (browser HTTP cache, Android page cache) -- stays valid.
Covers are cached as md5(path).jpg, so they are copied to the new name before
the database changes and the old copies removed afterwards (no request ever
sees a missing cover). Any failure rolls everything back.
"""
import hashlib
import logging
import os
import shutil

import config
import database

logger = logging.getLogger("bookhaven.library_ops")


class MoveError(Exception):
    """The move was refused or failed; nothing was changed."""


def _norm(path):
    return os.path.normcase(os.path.abspath(path))


def _in_library(path):
    p = _norm(path)
    return any(p.startswith(_norm(lib) + os.sep) for lib in config.LIBRARY_PATHS)


def _cover(path):
    return os.path.join(config.COVER_CACHE_DIR, hashlib.md5(path.encode()).hexdigest() + ".jpg")


def plan_move(old_dir, new_dir):
    """[(book_id, old_path, new_path)] for every book stored under old_dir."""
    old_dir, new_dir = os.path.abspath(old_dir), os.path.abspath(new_dir)
    prefix = old_dir + os.sep
    conn = database.get_db()
    try:
        rows = conn.execute("SELECT id, path FROM books WHERE substr(path, 1, ?) = ? ORDER BY id",
                            (len(prefix), prefix)).fetchall()
    finally:
        conn.close()
    return [(r["id"], r["path"], new_dir + os.sep + r["path"][len(prefix):]) for r in rows]


def move_folder(old_dir, new_dir, dry_run=False):
    """Move a library folder (on disk + in the database). Returns a report dict.

    Raises MoveError (with nothing changed) if the move is unsafe: source
    missing, target already present, outside the library, or a file inside is
    open (Windows refuses to rename a folder with an open file: a reader is
    using it -- retry later rather than forcing).
    """
    old_dir, new_dir = os.path.abspath(old_dir), os.path.abspath(new_dir)
    if not os.path.isdir(old_dir):
        raise MoveError(f"source folder not found: {old_dir}")
    if os.path.exists(new_dir):
        raise MoveError(f"target already exists: {new_dir}")
    if not (_in_library(old_dir) and _in_library(new_dir)):
        raise MoveError("both folders must be inside the library (config.LIBRARY_PATHS)")
    if _norm(new_dir).startswith(_norm(old_dir) + os.sep):
        raise MoveError("cannot move a folder inside itself")

    plan = plan_move(old_dir, new_dir)
    report = {"old": old_dir, "new": new_dir, "books": len(plan), "covers": 0,
              "ids": [b for b, _, _ in plan], "dry_run": dry_run}
    if dry_run:
        report["covers"] = sum(1 for _, o, _ in plan if os.path.exists(_cover(o)))
        return report

    # 1. Disk first: fails cleanly (nothing changed) if a file inside is open.
    try:
        os.rename(old_dir, new_dir)
    except OSError as e:
        raise MoveError(f"could not rename the folder (a file inside is probably open by a reader): {e}") from e

    copied = []
    try:
        # 2. Covers to their new name, before any row points there.
        for _, old, new in plan:
            src, dst = _cover(old), _cover(new)
            if os.path.exists(src) and not os.path.exists(dst):
                shutil.copy2(src, dst)
                copied.append(dst)
        # 3. Paths, all or nothing (ids, progress, series, flags untouched).
        with database.writing() as conn:
            for book_id, old, new in plan:
                cur = conn.execute("UPDATE books SET path = ? WHERE id = ? AND path = ?", (new, book_id, old))
                if cur.rowcount != 1:
                    raise MoveError(f"book {book_id} changed during the move")
    except Exception:
        for dst in copied:
            try:
                os.remove(dst)
            except OSError:
                pass
        try:
            os.rename(new_dir, old_dir)
        except OSError as e:
            logger.error(f"move_folder rollback could not rename {new_dir} back: {e}")
        raise

    # 4. Old covers are now unused.
    for _, old, new in plan:
        if os.path.exists(_cover(new)) and os.path.exists(_cover(old)):
            try:
                os.remove(_cover(old))
            except OSError:
                pass
    report["covers"] = len(copied)
    logger.info(f"Moved library folder {old_dir} -> {new_dir}: {len(plan)} books, {len(copied)} covers")
    return report
