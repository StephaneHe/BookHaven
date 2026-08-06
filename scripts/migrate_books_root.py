#!/usr/bin/env python
"""Migrate books.path from WSL-style /mnt/X/... to native Windows X:\\...

Background
----------
BOOKS_ROOT was left at /mnt/h/Books after the move off Docker/WSL. Reads still
work because _resolve_book_path() translates /mnt/X/... back to X:\\..., but
writes bypass that translation, so uploads land in phantom directories such as
I:\\mnt\\h\\Books. This script normalises the stored paths so BOOKS_ROOT can be
set to a native path.

Cover cache
-----------
Cached covers are named md5(book_path).jpg. Changing a path changes the hash,
so every cover must be moved alongside its row or it disappears from the UI.
Covers are COPIED to the new hash before the database is updated and the old
copies removed afterwards, so no request can observe a missing cover.

Usage
-----
    python scripts/migrate_books_root.py             # dry-run, writes nothing
    python scripts/migrate_books_root.py --apply     # perform the migration

After --apply, set BOOKS_ROOT=H:\\Books in .env and restart the server.
"""
import argparse
import hashlib
import os
import re
import shutil
import sqlite3
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(ROOT, "data", "bookhaven.db")
COVER_DIR = os.path.join(ROOT, "cache", "covers")
LOG_DIR = os.path.join(ROOT, "logs")

WSL_RE = re.compile(r"^/mnt/([a-zA-Z])(/.*)$")


def to_windows(path):
    """/mnt/h/Books/x.epub -> H:\\Books\\x.epub, or None if not a WSL path."""
    m = WSL_RE.match(path)
    if not m:
        return None
    return m.group(1).upper() + ":" + m.group(2).replace("/", os.sep)


def cover_for(path):
    return os.path.join(COVER_DIR, hashlib.md5(path.encode()).hexdigest() + ".jpg")


def plan(conn):
    """Classify every /mnt row. Returns (movable, missing, colliding)."""
    existing = {r["path"] for r in conn.execute("SELECT path FROM books")}
    rows = conn.execute(
        "SELECT id, path FROM books WHERE path LIKE '/mnt/%' ORDER BY id"
    ).fetchall()

    movable, missing, colliding = [], [], []
    for r in rows:
        old = r["path"]
        new = to_windows(old)
        if new is None:
            continue
        if new in existing:
            # books.path is UNIQUE -- updating would raise IntegrityError.
            colliding.append((r["id"], old, new))
        elif not os.path.exists(new):
            missing.append((r["id"], old, new))
        else:
            movable.append((r["id"], old, new))
    return movable, missing, colliding


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true",
                    help="perform the migration (default is a dry run)")
    args = ap.parse_args()

    if not os.path.exists(DB_PATH):
        sys.exit(f"base introuvable : {DB_PATH}")

    mode = "ro" if not args.apply else "rw"
    conn = sqlite3.connect(f"file:{DB_PATH}?mode={mode}", uri=True, timeout=30)
    conn.row_factory = sqlite3.Row

    total = conn.execute("SELECT COUNT(*) FROM books").fetchone()[0]
    movable, missing, colliding = plan(conn)

    print("=" * 68)
    print("PLAN DE MIGRATION" + ("" if args.apply else "   (DRY-RUN, aucune ecriture)"))
    print("=" * 68)
    print(f"  livres en base            : {total}")
    print(f"  a migrer (cible presente) : {len(movable)}")
    print(f"  cible ABSENTE du disque   : {len(missing)}")
    print(f"  collision UNIQUE          : {len(colliding)}")

    for label, items in (("ABSENTS", missing), ("COLLISIONS", colliding)):
        if items:
            print(f"\n  --- {label} (max 10) ---")
            for _id, old, new in items[:10]:
                print(f"    id={_id}\n      {old}\n   -> {new}")

    covers_to_move = [(o, n) for _, o, n in movable
                      if os.path.exists(cover_for(o)) and not os.path.exists(cover_for(n))]
    print(f"\n  vignettes a deplacer      : {len(covers_to_move)}")

    if not movable:
        print("\nRien a migrer.")
        conn.close()
        return

    if not args.apply:
        print("\n  Exemple de transformation :")
        _id, old, new = movable[0]
        print(f"    {old}\n -> {new}")
        print("\nRelancer avec --apply pour executer.")
        conn.close()
        return

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    os.makedirs(LOG_DIR, exist_ok=True)

    # --- 1. Backup ------------------------------------------------------
    backup = os.path.join(ROOT, "data", f"bookhaven.db.bak-{stamp}")
    print(f"\n[1/5] sauvegarde de la base -> {os.path.basename(backup)}")
    src = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    dst = sqlite3.connect(backup)
    with dst:
        src.backup(dst)          # consistent snapshot even with WAL / live server
    src.close()
    dst.close()
    print(f"      {os.path.getsize(backup) / 1048576:.1f} Mo")

    # --- 2. Mapping log (rollback material) ------------------------------
    mapping = os.path.join(LOG_DIR, f"migration-paths-{stamp}.tsv")
    with open(mapping, "w", encoding="utf-8") as fh:
        fh.write("id\told_path\tnew_path\n")
        for _id, old, new in movable:
            fh.write(f"{_id}\t{old}\t{new}\n")
    print(f"[2/5] journal de correspondance -> {os.path.basename(mapping)}")

    # --- 3. Copy covers BEFORE touching the DB ---------------------------
    copied = 0
    for old, new in covers_to_move:
        try:
            shutil.copy2(cover_for(old), cover_for(new))
            copied += 1
        except OSError as e:
            print(f"      avertissement copie vignette : {e}")
    print(f"[3/5] vignettes copiees vers le nouveau hash : {copied}")

    # --- 4. Update paths in a single transaction -------------------------
    try:
        with conn:
            conn.executemany(
                "UPDATE books SET path = ? WHERE id = ?",
                [(new, _id) for _id, _old, new in movable],
            )
        print(f"[4/5] chemins mis a jour : {len(movable)} (transaction validee)")
    except sqlite3.Error as e:
        print(f"[4/5] ECHEC, transaction annulee : {e}")
        print(f"      la base est intacte ; sauvegarde : {backup}")
        conn.close()
        sys.exit(1)

    # --- 5. Drop the now-unused old covers -------------------------------
    removed = 0
    for old, new in covers_to_move:
        if os.path.exists(cover_for(new)):
            try:
                os.remove(cover_for(old))
                removed += 1
            except OSError:
                pass
    print(f"[5/5] anciennes vignettes supprimees : {removed}")

    # --- Verification ----------------------------------------------------
    left = conn.execute("SELECT COUNT(*) FROM books WHERE path LIKE '/mnt/%'").fetchone()[0]
    # Sample in Python rather than with a LIKE drive-letter pattern: '__:%'
    # needs two characters before the colon and silently matches nothing.
    sample = conn.execute(
        "SELECT path FROM books ORDER BY RANDOM() LIMIT 300"
    ).fetchall()
    ok = sum(1 for r in sample if os.path.exists(r["path"]))
    cov = conn.execute("SELECT COUNT(*) FROM books WHERE has_cover = 1").fetchone()[0]
    cov_ok = sum(
        1 for r in conn.execute(
            "SELECT path FROM books WHERE has_cover = 1 ORDER BY RANDOM() LIMIT 300")
        if os.path.exists(cover_for(r["path"]))
    )
    conn.close()

    print("\n" + "=" * 68)
    print("VERIFICATION")
    print("=" * 68)
    print(f"  chemins /mnt restants        : {left}")
    print(f"  echantillon present sur disque : {ok}/{len(sample)}")
    print(f"  livres has_cover=1           : {cov}")
    print(f"  vignettes retrouvees (ech.)  : {cov_ok}/300")
    print(f"\n  sauvegarde : {backup}")
    print(f"  journal    : {mapping}")
    print("\n  Etape suivante : mettre BOOKS_ROOT=H:\\Books dans .env, puis redemarrer.")


if __name__ == "__main__":
    main()
