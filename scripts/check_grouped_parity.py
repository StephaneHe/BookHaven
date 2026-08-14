"""Compare /api/books/grouped against its pre-2.3.0 implementation, on the
REAL library database, read-only.

The pytest suite proves parity on synthetic fixtures. This script proves it on
the actual data -- 9 500-odd books whose titles, authors and folder names are
far messier than anything a generator produces.

    python scripts\\check_grouped_parity.py [--db PATH] [--verbose]

The database is opened through a file: URI in mode=ro, so this cannot write to
the production library even by accident. Exit code 0 means every combination
matched (after the deliberate divergences documented in the 2.3.0 CHANGELOG
entry), 1 means at least one real difference.
"""
import argparse
import os
import sqlite3
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

os.environ.setdefault("BOOKHAVEN_SECRET_KEY", "parity-check-secret-key-32-chars-min!")

import bookhaven                                       # noqa: E402
import config                                          # noqa: E402
from grouped_compare import diff_payloads              # noqa: E402
from legacy_grouped import legacy_books_grouped_payload  # noqa: E402


def open_readonly(path):
    uri = "file:" + path.replace("\\", "/").replace("?", "%3f").replace("#", "%23")
    conn = sqlite3.connect(uri + "?mode=ro", uri=True, timeout=15)
    conn.row_factory = sqlite3.Row
    return conn


def build_cases(conn):
    """~20 realistic combinations, prefixes taken from the real data."""
    total = conn.execute("SELECT COUNT(*) FROM books").fetchone()[0]
    last_page = max(1, (total // 50))
    tops = [r[0] for r in conn.execute(
        "SELECT DISTINCT CASE WHEN instr(collection_path, '/') > 0"
        " THEN substr(collection_path, 1, instr(collection_path, '/') - 1)"
        " ELSE collection_path END AS top"
        " FROM books WHERE collection_path <> '' ORDER BY top LIMIT 6").fetchall()]
    deep = [r[0] for r in conn.execute(
        "SELECT DISTINCT collection_path FROM books"
        " WHERE collection_path LIKE '%/%' ORDER BY collection_path LIMIT 3").fetchall()]
    categories = [r[0] for r in conn.execute(
        "SELECT DISTINCT category FROM books WHERE category <> ''"
        " ORDER BY category LIMIT 3").fetchall()]

    cases = [
        {"page": 1, "per_page": 50},
        {"page": 2, "per_page": 50},
        {"page": 64, "per_page": 50},
        {"page": last_page, "per_page": 50},
        {"page": 1, "per_page": 1},
        {"page": 1, "per_page": 200},
        {"page": 3, "per_page": 7},
        {"page": 99999, "per_page": 50},
        {"fmt": "epub", "per_page": 50},
        {"fmt": "pdf", "page": 2, "per_page": 50},
        {"search": "tome", "per_page": 50},
        {"search": "l'", "per_page": 50},
        {"author": "a", "per_page": 50},
        {"genre": "Science", "per_page": 50},
    ]
    cases += [{"category": c, "per_page": 50} for c in categories]
    cases += [{"prefix": p, "per_page": 50} for p in tops]
    cases += [{"prefix": p, "per_page": 50} for p in deep]
    cases += [
        {"prefix": tops[0], "fmt": "pdf", "per_page": 50} if tops else {},
        {"prefix": "definitely/not/a/real/collection", "per_page": 50},
    ]
    return [c for c in cases if c], total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=config.DB_PATH)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    conn = open_readonly(args.db)
    cases, total = build_cases(conn)
    print(f"database : {args.db} (read-only)")
    print(f"books    : {total}")
    print(f"cases    : {len(cases)}\n")

    identical = 0
    failures = []
    for case in cases:
        started = time.perf_counter()
        new = bookhaven._books_grouped_payload(conn, **case)
        t_new = time.perf_counter() - started
        started = time.perf_counter()
        old = legacy_books_grouped_payload(conn, **case)
        t_old = time.perf_counter() - started

        diffs = diff_payloads(new, old)
        status = "OK  " if not diffs else "DIFF"
        if not diffs:
            identical += 1
        else:
            failures.append((case, diffs))
        print(f"{status} {str(case):58} items={new['total']:5}"
              f"  new={t_new * 1000:7.1f}ms  old={t_old * 1000:7.1f}ms"
              f"  x{(t_old / t_new if t_new else 0):.1f}")
        if diffs and args.verbose:
            for d in diffs[:5]:
                print(f"       {d}")

    conn.close()
    print(f"\n{identical}/{len(cases)} identical")
    if failures:
        print("\nDifferences (beyond the documented ones):")
        for case, diffs in failures:
            print(f"  {case}")
            for d in diffs[:5]:
                print(f"    {d}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
