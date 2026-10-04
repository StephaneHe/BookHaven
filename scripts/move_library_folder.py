#!/usr/bin/env python3
"""Rename/move a folder of the BookHaven library without re-creating its books.

Same book ids, reading progress, Continue Reading, series, webtoon flag and
caches; only the stored paths change (see library_ops.move_folder).

    python scripts/move_library_folder.py "<old folder>" "<new folder>"           # dry run
    python scripts/move_library_folder.py "<old folder>" "<new folder>" --apply   # do it

--apply backs the database up to backup/ first. Run it while nothing reads the
folder (stop the watchdog + server, or at a quiet moment): if a file inside is
open, the move is refused and nothing changes.
"""
import argparse
import os
import sqlite3
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import config        # noqa: E402
import library_ops   # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("old")
    ap.add_argument("new")
    ap.add_argument("--apply", action="store_true", help="perform the move (default: dry run)")
    a = ap.parse_args()
    try:
        rep = library_ops.move_folder(a.old, a.new, dry_run=True)
        print(f"{rep['books']} book(s) under {rep['old']}, {rep['covers']} cached cover(s)")
        if not a.apply:
            print("dry run: nothing changed (add --apply)")
            return 0
        os.makedirs(os.path.join(ROOT, "backup"), exist_ok=True)
        dst = os.path.join(ROOT, "backup", time.strftime("bookhaven-before-move-%Y%m%d-%H%M%S.db"))
        src_conn, dst_conn = sqlite3.connect(config.DB_PATH), sqlite3.connect(dst)
        src_conn.backup(dst_conn)
        dst_conn.close()
        src_conn.close()
        print(f"database backed up to {dst}")
        rep = library_ops.move_folder(a.old, a.new)
        print(f"moved: {rep['books']} book(s) now under {rep['new']}, {rep['covers']} cover(s) renamed")
        return 0
    except library_ops.MoveError as e:
        print(f"REFUSED: {e}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
