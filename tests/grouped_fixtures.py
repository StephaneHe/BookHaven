"""Deterministic fixture library for /api/books/grouped tests.

Everything here is seeded and inserted in a fixed order, so row ids are stable
across runs. The parity tests compare whole JSON payloads (including list
order), which only works if the data -- and therefore the ids -- are identical
from one run to the next.

Contents deliberately cover every branch of the grouped endpoint:
  * top-level collections of depth 1..3 with 2..15 books
  * single-book collections without children (rendered as books, not folders)
  * standalone books (collection_path = '')
  * multi-format groups covering every FORMAT_PRIORITY pair plus an unknown one
  * case-sensitive base-filename pairs (Dune.epub vs dune.pdf => 2 groups)
  * accented titles and titles that tie on title.lower()
  * empty authors and authors containing a comma
"""
import random

FORMATS = ["epub", "cbz", "cbr", "pdf", "mobi", "txt"]
CATEGORIES = ["Books", "Comics", "Education", "Magazines"]
GENRES = ["Science-Fiction", "Fantasy", "Policier", "Histoire", ""]
AUTHORS = ["Zola", "Hugo", "Doe, John", "", "Eric Ambler", "Asimov",
           "Ursula K. Le Guin", "Ecrivain, Anne-Marie"]

_INSERT = """
INSERT INTO books (path, filename, title, author, genre, series, series_index,
                   category, format, file_size, has_cover, page_count,
                   description, collection_path)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


class _Inserter:
    def __init__(self, conn):
        self.conn = conn
        self.n = 0

    def add(self, folder, filename, title, author="", genre="", category="Books",
            fmt=None, has_cover=0, collection_path="", series="", description=""):
        self.n += 1
        if fmt is None:
            fmt = filename.rsplit(".", 1)[-1].lower()
        path = f"H:/Books/{folder}/{filename}" if folder else f"H:/Books/{filename}"
        # path is UNIQUE; disambiguate identical names living in the same folder
        self.conn.execute(_INSERT, (
            f"{path}#{self.n}", filename, title, author, genre, series,
            float(self.n % 7), category, fmt, 1000 + self.n, has_cover,
            self.n % 300, description, collection_path,
        ))


def populate(conn, seed=20260814, n_standalone=200, n_collections=30):
    """Fill an initialised books table with the deterministic fixture set."""
    rng = random.Random(seed)
    ins = _Inserter(conn)

    # -- 1. Multi-format standalone groups: every unordered pair of formats,
    #       variants living in sibling folders (grouping ignores the folder).
    pair_id = 0
    for i, fa in enumerate(FORMATS):
        for fb in FORMATS[i + 1:]:
            pair_id += 1
            base = f"Multi{pair_id:02d} Volume"
            # inserted worst-format first so a naive "first row wins" is caught
            ins.add(f"{fb.upper()}", f"{base}.{fb}", f"{base} ({fb})",
                    author=AUTHORS[pair_id % len(AUTHORS)],
                    genre=GENRES[pair_id % len(GENRES)],
                    category=CATEGORIES[pair_id % len(CATEGORIES)],
                    has_cover=pair_id % 2)
            ins.add(f"{fa.upper()}", f"{base}.{fa}", f"{base} ({fa})",
                    author=AUTHORS[(pair_id + 1) % len(AUTHORS)],
                    genre=GENRES[(pair_id + 2) % len(GENRES)],
                    category=CATEGORIES[(pair_id + 1) % len(CATEGORIES)],
                    has_cover=(pair_id + 1) % 2)

    # a three-variant group, and one with an unknown extension left attached
    ins.add("PDF", "Triple Play.pdf", "Triple Play (pdf)", author="Hugo", has_cover=1)
    ins.add("EPUB", "Triple Play.epub", "Triple Play (epub)", author="Zola")
    ins.add("MOBI", "Triple Play.mobi", "Triple Play (mobi)", author="")
    ins.add("TXT", "Notes.txt", "Notes", author="Zola", fmt="txt")
    ins.add("TXT", "Notes.txt.epub", "Notes epub", author="Zola")

    # -- 2. Case sensitivity: base filename keeps its case => two groups.
    ins.add("A", "Dune.epub", "Dune", author="Herbert", has_cover=1)
    ins.add("B", "dune.pdf", "dune lowercase", author="Herbert")

    # -- 3. Accents + title.lower() ties.
    ins.add("FR", "Ecole.epub", "\u00c9cole buissonni\u00e8re", author="Zola", has_cover=1)
    ins.add("FR", "elan.epub", "\u00e9lan vital", author="Hugo")
    ins.add("FR", "zebre.pdf", "Z\u00e8bre", author="")
    ins.add("FR", "zebra.pdf", "zebra", author="Doe, John")
    ins.add("TIE", "tie-a.epub", "Tie Title", author="Alpha", has_cover=1)
    ins.add("TIE", "tie-b.epub", "TIE TITLE", author="Beta")
    ins.add("TIE", "tie-c.pdf", "tie title", author="")

    # -- 4. Collections of depth 1..3.
    for c in range(n_collections):
        top = f"Collection {c:02d}"
        depth = 1 + (c % 3)
        n_books = 2 + (c % 14)
        for b in range(n_books):
            if depth == 1:
                cp = top
            elif depth == 2:
                cp = f"{top}/Saison {b % 3 + 1}"
            else:
                cp = f"{top}/Saison {b % 2 + 1}/Tome {b % 3 + 1}"
            fmt = FORMATS[(c + b) % len(FORMATS)]
            ins.add(cp, f"C{c:02d}B{b:02d}.{fmt}", f"{top} - Episode {b:02d}",
                    author=AUTHORS[(c + b) % len(AUTHORS)],
                    genre=GENRES[(c + b) % len(GENRES)],
                    category=CATEGORIES[(c + b) % len(CATEGORIES)],
                    has_cover=(c + b) % 3 == 0,
                    collection_path=cp)

    # a collection whose books are multi-format variants at the same level
    for fmt in ("pdf", "epub", "cbz"):
        ins.add("Variants Inside", f"Inside Story.{fmt}", f"Inside Story ({fmt})",
                author="Zola", collection_path="Variants Inside", has_cover=1)
    ins.add("Variants Inside", "Other Inside.pdf", "Other Inside",
            author="", collection_path="Variants Inside")

    # a collection with only empty-string authors, and one with many authors
    for b in range(3):
        ins.add("Anonymes", f"Anon{b}.epub", f"Anonyme {b}", author="",
                collection_path="Anonymes")
    for b, a in enumerate(AUTHORS):
        ins.add("Many Authors", f"Many{b}.epub", f"Many Authors {b}", author=a,
                collection_path="Many Authors", has_cover=b % 2)

    # risk #10: same base filename, one standalone and one in a collection
    ins.add("Split", "Split Base.epub", "Split Base standalone", author="Zola")
    ins.add("Split Coll", "Split Base.pdf", "Split Base in collection",
            author="Zola", collection_path="Split Coll Extra")
    ins.add("Split Coll", "Split Other.pdf", "Split Other",
            author="Hugo", collection_path="Split Coll Extra")

    # -- 5. Single-book collections without children -> rendered as books.
    for s in range(8):
        fmt = FORMATS[s % len(FORMATS)]
        ins.add(f"Solo {s}", f"Solo{s}.{fmt}", f"Solo Collection {s}",
                author=AUTHORS[s % len(AUTHORS)],
                genre=GENRES[s % len(GENRES)],
                category=CATEGORIES[s % len(CATEGORIES)],
                has_cover=s % 2, collection_path=f"Solo {s}")

    # -- 6. Bulk standalone books.
    for i in range(n_standalone):
        fmt = FORMATS[rng.randrange(len(FORMATS))]
        ins.add("Bulk", f"Bulk {i:04d}.{fmt}", f"Bulk Book {i:04d}",
                author=AUTHORS[rng.randrange(len(AUTHORS))],
                genre=GENRES[rng.randrange(len(GENRES))],
                category=CATEGORIES[rng.randrange(len(CATEGORIES))],
                has_cover=rng.randrange(2),
                description="d" * 200)

    # risk #10, the real one: a variant inside a MULTI-book collection never
    # joins a standalone of the same base (they come from different queries).
    # Appended last so the ids above stay stable.
    ins.add("Bulk", "Inside Story.mobi", "Inside Story standalone", author="Zola")

    conn.commit()
    return ins.n


def populate_large(conn, seed=99, n_books=10000, n_collections=300):
    """Bigger, cheaper dataset for the row-count budget test (step 8)."""
    rng = random.Random(seed)
    ins = _Inserter(conn)
    in_collections = n_books * 2 // 3
    per_collection = max(1, in_collections // n_collections)
    for c in range(n_collections):
        top = f"Coll {c:04d}"
        for b in range(per_collection):
            cp = top if b % 2 else f"{top}/Sub {b % 4}"
            fmt = FORMATS[(c + b) % len(FORMATS)]
            ins.add(cp, f"L{c:04d}_{b:03d}.{fmt}", f"Large {c:04d} {b:03d}",
                    author=AUTHORS[(c + b) % len(AUTHORS)],
                    category=CATEGORIES[c % len(CATEGORIES)],
                    has_cover=(c + b) % 3 == 0, collection_path=cp,
                    description="x" * 500)
    while ins.n < n_books:
        i = ins.n
        fmt = FORMATS[rng.randrange(len(FORMATS))]
        ins.add("Bulk", f"Large Bulk {i:05d}.{fmt}", f"Large Bulk {i:05d}",
                author=AUTHORS[rng.randrange(len(AUTHORS))],
                category=CATEGORIES[rng.randrange(len(CATEGORIES))],
                has_cover=rng.randrange(2), description="x" * 500)
    conn.commit()
    return ins.n
