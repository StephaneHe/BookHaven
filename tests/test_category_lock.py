"""R104: a category chosen by hand (category_locked = 1) survives every scan, even
though the scanner derives categories from the library folder (Comics\\...).

Temporary library + database; the real scanner indexes and re-scans it.
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

import bookhaven  # noqa: E402
import config     # noqa: E402
import database   # noqa: E402
import scanner    # noqa: E402


def _cbz(path, plates):
    with zipfile.ZipFile(path, "w") as z:
        for i in range(plates):
            buf = io.BytesIO()
            Image.new("RGB", (60, 360), (40 * i % 256, 80, 120)).save(buf, "PNG")
            z.writestr(f"p_{i}.png", buf.getvalue())


@pytest.fixture()
def lib(tmp_path, monkeypatch):
    comics = tmp_path / "Books" / "Comics"
    (comics / "Saga").mkdir(parents=True)
    _cbz(comics / "Saga" / "Saga 001.cbz", 2)
    _cbz(comics / "Saga" / "Saga 002.cbz", 2)
    _cbz(comics / "Batman 001.cbz", 2)
    monkeypatch.setattr(config, "BOOKS_ROOT", str(tmp_path / "Books"))
    monkeypatch.setattr(config, "LIBRARY_PATHS", [str(comics)])
    monkeypatch.setattr(config, "COVER_CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(config, "SCAN_EXCLUDE_FILE", str(tmp_path / "none.txt"))
    monkeypatch.setattr(scanner, "classify_genre", lambda *a, **k: "")     # no genre -> rows get updated
    bookhaven.app.config["TESTING"] = True
    with patch.object(config, "DB_PATH", str(tmp_path / "lib.db")):
        database.init_db()
        assert scanner.scan_library()["new"] == 3
        yield comics


def _cat():
    conn = database.get_db()
    try:
        return {os.path.basename(r["path"]): (r["id"], r["category"]) for r in conn.execute("SELECT * FROM books")}
    finally:
        conn.close()


def test_R104_locked_category_survives_rescan_of_changed_files(lib):
    assert {v[1] for v in _cat().values()} == {"Comics"}                  # derived from the folder
    conn = database.get_db()
    conn.execute("UPDATE books SET category = 'Webcomics', category_locked = 1 WHERE path LIKE ?",
                 (f"%{os.sep}Saga{os.sep}%",))
    conn.execute("UPDATE books SET category = 'Webcomics' WHERE filename = 'Batman 001.cbz'")  # NOT locked
    conn.commit()
    conn.close()
    before = _cat()

    # files replaced (new size) -> the scan re-reads and UPDATEs every row
    for f in ("Saga/Saga 001.cbz", "Saga/Saga 002.cbz", "Batman 001.cbz"):
        _cbz(lib / f, 3)
    res = scanner.scan_library()
    assert res["updated"] == 3 and res["new"] == 0 and res["removed"] == 0
    after = _cat()
    assert after["Saga 001.cbz"] == before["Saga 001.cbz"] == (after["Saga 001.cbz"][0], "Webcomics")
    assert after["Saga 002.cbz"][1] == "Webcomics"
    assert after["Batman 001.cbz"][1] == "Comics"                          # unlocked: back to its folder

    with bookhaven.app.test_client() as c:
        web = {b["filename"] for b in c.get("/api/books?category=Webcomics").get_json()["books"]}
        com = {b["filename"] for b in c.get("/api/books?category=Comics").get_json()["books"]}
    assert web == {"Saga 001.cbz", "Saga 002.cbz"} and com == {"Batman 001.cbz"}


def test_R104_init_db_adds_category_locked(tmp_path):
    with patch.object(config, "DB_PATH", str(tmp_path / "x.db")):
        database.init_db()
        database.init_db()
        conn = database.get_db()
        cols = {r[1]: r for r in conn.execute("PRAGMA table_info(books)")}
        conn.close()
    assert "category_locked" in cols and str(cols["category_locked"][4]) == "0"
