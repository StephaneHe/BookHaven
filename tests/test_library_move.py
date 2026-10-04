"""R101: renaming/moving a series folder keeps the books -- same ids, reading
progress, series, webtoon flag and covers -- and a later scan neither creates
duplicates nor reports the old paths as missing.

Temporary library + database; the real scanner indexes it first.
"""
import io
import os
import zipfile
from unittest.mock import patch

import pytest
from PIL import Image

os.environ.setdefault("BOOKHAVEN_SECRET_KEY", "test-secret-key-32chars-minimum!")
os.environ.setdefault("BOOKHAVEN_TEST_MODE", "1")
os.environ.setdefault("BOOKHAVEN_ENV", "development")

import bookhaven      # noqa: E402
import config         # noqa: E402
import database       # noqa: E402
import library_ops    # noqa: E402
import scanner        # noqa: E402

OLD = "Saga - Ragnarok"
NEW = "Saga Ragnarok (Scanlated) (Void)"


def _cbz(path, shade):
    with zipfile.ZipFile(path, "w") as z:
        for i in range(3):
            buf = io.BytesIO()
            Image.new("RGB", (60, 360), (shade, 30 * i, 90)).save(buf, "PNG")
            z.writestr(f"p_{i}.png", buf.getvalue())


@pytest.fixture()
def lib(tmp_path, monkeypatch):
    root = tmp_path / "Books"
    comics = root / "Comics"
    (comics / OLD).mkdir(parents=True)
    (comics / "Other").mkdir()
    for n in (1, 2, 3):
        _cbz(comics / OLD / f"Saga Ragnarok {n:03d}.cbz", 40 * n)
    _cbz(comics / "Other" / "Other 001.cbz", 200)
    covers = tmp_path / "covers"
    covers.mkdir()
    monkeypatch.setattr(config, "BOOKS_ROOT", str(root))
    monkeypatch.setattr(config, "LIBRARY_PATHS", [str(comics)])
    monkeypatch.setattr(config, "COVER_CACHE_DIR", str(covers))
    monkeypatch.setattr(config, "SCAN_EXCLUDE_FILE", str(tmp_path / "none.txt"))
    monkeypatch.setattr(scanner, "classify_genre", lambda *a, **k: "Fantasy")
    bookhaven.app.config["TESTING"] = True
    with patch.object(config, "DB_PATH", str(tmp_path / "lib.db")):
        database.init_db()
        res = scanner.scan_library()
        assert res["new"] == 4
        conn = database.get_db()
        conn.execute("UPDATE books SET series = 'Saga', reading_mode = 'webtoon' WHERE path LIKE ?",
                     (f"%{OLD}%",))
        conn.commit()
        conn.close()
        yield comics


def _rows():
    conn = database.get_db()
    try:
        return {r["id"]: dict(r) for r in conn.execute("SELECT * FROM books")}
    finally:
        conn.close()


def _progress():
    conn = database.get_db()
    try:
        return sorted(tuple(r) for r in conn.execute(
            "SELECT user_id, book_id, current_location, progress, last_read FROM reading_progress"))
    finally:
        conn.close()


def _add_progress(book_ids):
    conn = database.get_db()
    for i, bid in enumerate(book_ids):
        conn.execute("INSERT INTO reading_progress (user_id, book_id, progress, current_location, last_read) "
                     "VALUES ('u1', ?, ?, ?, '2026-10-04 12:00:00')", (bid, 100 if i == 0 else 40, f"{i}.5000"))
    conn.commit()
    conn.close()


def test_R101_rename_keeps_ids_progress_series_covers_and_rescan_is_clean(lib):
    before = _rows()
    saga = sorted(b for b, r in before.items() if OLD in r["path"])
    assert len(saga) == 3
    _add_progress(saga)
    progress_before = _progress()
    covers_before = {b: scanner.get_cover_path(before[b]["path"]) for b in saga}
    assert all(covers_before.values())

    rep = library_ops.move_folder(str(lib / OLD), str(lib / NEW))
    assert rep["books"] == 3 and sorted(rep["ids"]) == saga and rep["covers"] == 3

    after = _rows()
    assert sorted(after) == sorted(before)                                   # same ids, nothing added/removed
    for b in saga:
        a, o = after[b], before[b]
        assert a["path"] == o["path"].replace(OLD, NEW) and os.path.isfile(a["path"])
        for col in ("title", "series", "series_index", "reading_mode", "genre", "category",
                    "file_size", "modified_at", "has_cover", "filename"):
            assert a[col] == o[col], (b, col)                                 # content_version unchanged too
        assert scanner.get_cover_path(a["path"])                              # cover follows the book
        assert not os.path.exists(covers_before[b])                           # old cover cleaned up
    other = next(b for b in before if b not in saga)
    assert after[other] == before[other]                                      # other folders untouched
    assert _progress() == progress_before                                     # reading progress intact
    assert not (lib / OLD).exists()

    # a later scan: no duplicates, nothing reported missing/moved
    res = scanner.scan_library()
    assert (res["new"], res["removed"], res["moved"]) == (0, 0, 0)
    assert sorted(_rows()) == sorted(before)
    assert _progress() == progress_before

    # the reader still gets the book through the API
    with bookhaven.app.test_client() as c:
        d = c.get(f"/api/books/{saga[1]}").get_json()
        assert NEW in d["path"] and d["webtoon"] is True
        pages = c.get(f"/api/books/{saga[1]}/comic-pages").get_json()
        assert pages["total"] == 3
        assert c.get(f"/api/books/{saga[1]}/comic-page/0").status_code == 200
        assert c.get(f"/api/books/{saga[1]}/cover").mimetype == "image/jpeg"


def test_R101_dry_run_changes_nothing(lib):
    before = _rows()
    rep = library_ops.move_folder(str(lib / OLD), str(lib / NEW), dry_run=True)
    assert rep["books"] == 3 and rep["dry_run"]
    assert (lib / OLD).exists() and not (lib / NEW).exists()
    assert _rows() == before


@pytest.mark.skipif(os.name != "nt", reason="Windows refuses to rename a folder holding an open file")
def test_R101_open_file_refuses_the_move_and_changes_nothing(lib):
    before = _rows()
    held = open(lib / OLD / "Saga Ragnarok 002.cbz", "rb")                    # a reader has it open
    try:
        with pytest.raises(library_ops.MoveError, match="open"):
            library_ops.move_folder(str(lib / OLD), str(lib / NEW))
    finally:
        held.close()
    assert (lib / OLD).exists() and not (lib / NEW).exists()
    assert _rows() == before


def test_R101_database_failure_rolls_everything_back(lib, monkeypatch):
    before = _rows()
    covers = sorted(os.listdir(config.COVER_CACHE_DIR))

    class Boom:
        def __enter__(self):
            raise RuntimeError("db down")

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(database, "writing", lambda: Boom())
    with pytest.raises(RuntimeError):
        library_ops.move_folder(str(lib / OLD), str(lib / NEW))
    assert (lib / OLD).exists() and not (lib / NEW).exists()
    assert sorted(os.listdir(config.COVER_CACHE_DIR)) == covers               # no stray cover copies
    assert _rows() == before


def test_R101_unsafe_moves_are_refused(lib, tmp_path):
    with pytest.raises(library_ops.MoveError, match="already exists"):
        library_ops.move_folder(str(lib / OLD), str(lib / "Other"))
    with pytest.raises(library_ops.MoveError, match="inside the library"):
        library_ops.move_folder(str(lib / OLD), str(tmp_path / "elsewhere"))
    with pytest.raises(library_ops.MoveError, match="not found"):
        library_ops.move_folder(str(lib / "Missing"), str(lib / NEW))
