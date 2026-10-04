"""Non-regression tests for user requirements (server side), one test per Rxx.

Every test runs against a TEMPORARY database (config.DB_PATH patched) through
the Flask test client; all global state (config flags, TEST_MODE, default-user
cache) is patched with monkeypatch so it is restored after each test.
"""
import importlib.util
import os
import struct
import zipfile
from io import BytesIO
from unittest.mock import MagicMock

import pytest

os.environ.setdefault("BOOKHAVEN_SECRET_KEY", "test-secret-key-32chars-minimum!")
os.environ.setdefault("BOOKHAVEN_TEST_MODE", "1")
os.environ.setdefault("BOOKHAVEN_ENV", "development")

import bookhaven  # noqa: E402
import config     # noqa: E402
import database   # noqa: E402
import scanner    # noqa: E402

from PIL import Image  # noqa: E402

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEST_USER = "test-user"   # session user set by the TEST_MODE bypass


# ── fixtures / helpers ───────────────────────────────────────────────────────

@pytest.fixture()
def db(tmp_path, monkeypatch):
    """Temporary initialised database; TEST_MODE bypass on, fresh default-user cache."""
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr(bookhaven, "TEST_MODE", True)
    monkeypatch.setattr(bookhaven, "_default_user_cache", {})
    monkeypatch.setattr(config, "LOGIN_REQUIRED", False)
    monkeypatch.setitem(bookhaven.app.config, "TESTING", True)
    database.init_db()
    return tmp_path


@pytest.fixture()
def client(db):
    with bookhaven.app.test_client() as c:
        yield c


def add_book(bid, **fields):
    row = {"id": bid, "path": f"/nonexistent/{bid}.cbz", "filename": f"book{bid}.cbz",
           "title": f"Book {bid}", "format": "cbz"}
    row.update(fields)
    cols = ", ".join(row)
    marks = ", ".join("?" for _ in row)
    conn = database.get_db()
    conn.execute(f"INSERT INTO books ({cols}) VALUES ({marks})", list(row.values()))
    conn.commit()
    conn.close()


def sql(query, params=()):
    conn = database.get_db()
    cur = conn.execute(query, params)
    rows = cur.fetchall()
    conn.commit()
    conn.close()
    return rows


def img_bytes(fmt, size=(20, 30), color=(200, 30, 30)):
    buf = BytesIO()
    Image.new("RGB", size, color).save(buf, fmt)
    return buf.getvalue()


def make_cbz(path):
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("p1.png", img_bytes("PNG"))
        zf.writestr("p2.jpg", img_bytes("JPEG"))
        zf.writestr("p3.webp", img_bytes("WEBP"))
    return str(path)


def no_test_mode(monkeypatch, login_required):
    monkeypatch.setattr(bookhaven, "TEST_MODE", False)
    monkeypatch.setattr(config, "LOGIN_REQUIRED", login_required)


# ── R01 version ──────────────────────────────────────────────────────────────

def test_R01_version_endpoint_and_footer(client):
    """/api/version returns __version__ and the index footer shows 'BookHaven v<version>'."""
    r = client.get("/api/version")
    assert r.status_code == 200
    assert r.get_json() == {"version": bookhaven.__version__}
    html = client.get("/").get_data(as_text=True)
    assert f"BookHaven v{bookhaven.__version__}" in html


# ── R03 /download ────────────────────────────────────────────────────────────

def test_R03_download_page_public_with_version_and_apk_link(db, monkeypatch):
    """/download needs no session even with login required, shows version and links the APK."""
    no_test_mode(monkeypatch, login_required=True)
    with bookhaven.app.test_client() as c:
        assert c.get("/api/books").status_code == 401        # login really is enforced
        r = c.get("/download")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert f"v{bookhaven.__version__}" in html
    assert 'href="/static/bookhaven-android.apk"' in html


# ── R04 passwordless default user ────────────────────────────────────────────

def _add_user(uid, name, created):
    sql("INSERT INTO users (id, name, created_at) VALUES (?, ?, ?)", (uid, name, created))


def test_R04_default_user_auto_selected_without_login(db, monkeypatch):
    """With login not required, /api/auth/me returns config.DEFAULT_USER and protected routes work."""
    no_test_mode(monkeypatch, login_required=False)
    _add_user("u-old", "older", "2020-01-01 00:00:00")
    _add_user("u-def", config.DEFAULT_USER, "2024-01-01 00:00:00")
    add_book(1)
    with bookhaven.app.test_client() as c:
        me = c.get("/api/auth/me")
        assert me.status_code == 200
        assert me.get_json()["user_id"] == "u-def"
        assert me.get_json()["user_name"] == config.DEFAULT_USER
        r = c.get("/api/books")
        assert r.status_code == 200 and r.get_json()["total"] == 1


def test_R04_falls_back_to_oldest_user(db, monkeypatch):
    """If DEFAULT_USER does not exist, the oldest user (created_at) is auto-selected."""
    no_test_mode(monkeypatch, login_required=False)
    monkeypatch.setattr(config, "DEFAULT_USER", "nobody-with-this-name")
    _add_user("u-new", "newer", "2024-01-01 00:00:00")
    _add_user("u-old", "older", "2020-01-01 00:00:00")
    with bookhaven.app.test_client() as c:
        data = c.get("/api/auth/me").get_json()
        assert data["user_id"] == "u-old" and data["user_name"] == "older"
        assert c.get("/api/enrichment/status").status_code == 200


# ── R05 login required ───────────────────────────────────────────────────────

def test_R05_protected_routes_401_without_session(db, monkeypatch):
    """With LOGIN_REQUIRED and no session, cover and enrichment status return 401."""
    no_test_mode(monkeypatch, login_required=True)
    _add_user("u-def", config.DEFAULT_USER, "2024-01-01 00:00:00")
    add_book(1)
    with bookhaven.app.test_client() as c:
        assert c.get("/api/books/1/cover").status_code == 401
        assert c.get("/api/enrichment/status").status_code == 401
        assert c.get("/api/auth/me").status_code == 401


# ── R24 / R25 cache headers ──────────────────────────────────────────────────

def test_R24_index_is_no_cache(client):
    """GET / is served with Cache-Control: no-cache."""
    r = client.get("/")
    assert r.status_code == 200
    assert "no-cache" in r.headers.get("Cache-Control", "")


def test_R25_cover_placeholder_is_no_cache(client):
    """A book without cover gets the SVG placeholder with Cache-Control: no-cache."""
    add_book(1, has_cover=0)
    r = client.get("/api/books/1/cover")
    assert r.status_code == 200
    assert r.mimetype == "image/svg+xml"
    assert "no-cache" in r.headers.get("Cache-Control", "")


# ── R26 comic page MIME ──────────────────────────────────────────────────────

def test_R26_comic_page_mime_including_webp(client, db):
    """comic-page serves png/jpeg/webp pages of a CBZ with their correct MIME types."""
    add_book(1, path=make_cbz(db / "c.cbz"), filename="c.cbz")
    pages = client.get("/api/books/1/comic-pages").get_json()["pages"]
    assert pages == ["p1.png", "p2.jpg", "p3.webp"]
    expected = ["image/png", "image/jpeg", "image/webp"]
    for n, mime in enumerate(expected):
        r = client.get(f"/api/books/1/comic-page/{n}")
        assert r.status_code == 200
        assert r.mimetype == mime
    assert Image.open(BytesIO(client.get("/api/books/1/comic-page/2").data)).format == "WEBP"
    assert client.get("/api/books/1/comic-page/3").status_code == 404


# ── R28 content_version ──────────────────────────────────────────────────────

def test_R28_content_version_present_and_changes(client, db):
    """content_version is exposed by comic-pages, book detail and list, and follows size/mtime."""
    add_book(1, path=make_cbz(db / "c.cbz"), filename="c.cbz", file_size=100,
             modified_at="2026-01-01 00:00:00")

    def versions():
        a = client.get("/api/books/1/comic-pages").get_json()["content_version"]
        b = client.get("/api/books/1").get_json()["content_version"]
        items = client.get("/api/books").get_json()["books"]
        assert items and all("content_version" in it for it in items)
        c = items[0]["content_version"]
        assert a == b == c
        return a

    v1 = versions()
    sql("UPDATE books SET file_size = 200 WHERE id = 1")
    v2 = versions()
    sql("UPDATE books SET modified_at = '2026-02-01 00:00:00' WHERE id = 1")
    v3 = versions()
    assert len({v1, v2, v3}) == 3


# ── R52 progress of unknown book ─────────────────────────────────────────────

def test_R52_progress_unknown_book_404(client):
    """PUT and GET progress for a book that does not exist return 404 (CHANGELOG 2.7.1)."""
    r = client.put("/api/books/999/progress", json={"progress": 10, "current_location": "x"})
    assert r.status_code == 404
    assert client.get("/api/books/999/progress").status_code == 404
    assert sql("SELECT COUNT(*) FROM reading_progress")[0][0] == 0


# ── R60 epub-resource OPF subfolder ──────────────────────────────────────────

def test_R60_epub_resource_resolves_via_opf_dir(client, db):
    """epub-resource finds an OPF-relative image under OEBPS/ via container.xml (200, image MIME)."""
    epub = db / "b.epub"
    png = img_bytes("PNG")
    with zipfile.ZipFile(epub, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip")
        zf.writestr("META-INF/container.xml",
                    '<?xml version="1.0"?><container version="1.0" '
                    'xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles>'
                    '<rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>'
                    '</rootfiles></container>')
        zf.writestr("OEBPS/content.opf", "<package/>")
        zf.writestr("OEBPS/Images/pic.png", png)
    add_book(1, path=str(epub), filename="b.epub", format="epub")
    r = client.get("/api/books/1/epub-resource/Images/pic.png")
    assert r.status_code == 200
    assert r.mimetype == "image/png"
    assert r.data == png
    assert client.get("/api/books/1/epub-resource/Images/missing.png").status_code == 404


# ── R70 formats ──────────────────────────────────────────────────────────────

def test_R70_pdf_and_cbz_served_with_correct_mime(client, db):
    """/file serves a PDF as application/pdf and a CBZ as application/zip."""
    import fitz
    pdf = db / "d.pdf"
    doc = fitz.open()
    doc.new_page().insert_text((72, 72), "hello")
    doc.save(str(pdf))
    doc.close()
    add_book(1, path=str(pdf), filename="d.pdf", format="pdf")
    add_book(2, path=make_cbz(db / "c.cbz"), filename="c.cbz", format="cbz")

    r = client.get("/api/books/1/file")
    assert r.status_code == 200 and r.mimetype == "application/pdf"
    assert r.data.startswith(b"%PDF")
    r = client.get("/api/books/2/file")
    assert r.status_code == 200 and r.mimetype == "application/zip"
    assert r.data.startswith(b"PK")


def _palmdb(records):
    """Minimal PalmDB container: 78-byte header + record table + records."""
    header = bytearray(78)
    header[0:8] = b"testbook"
    header[60:68] = b"BOOKMOBI"
    header[76:78] = struct.pack(">H", len(records))
    table_len = len(records) * 8 + 2
    off = 78 + table_len
    table = b""
    for i, rec in enumerate(records):
        table += struct.pack(">II", off, i)
        off += len(rec)
    return bytes(header) + table + b"\x00\x00" + b"".join(records)


def test_R70_mobi_cover_from_exth_201(tmp_path):
    """MOBI cover extraction follows EXTH record 201 (cover offset), not just the first image."""
    import media_worker
    first_image = img_bytes("PNG", color=(0, 0, 255))     # first image record: NOT the cover
    cover = img_bytes("JPEG", color=(0, 255, 0))          # first_img + 1 -> the cover
    exth_rec = struct.pack(">II", 201, 12) + struct.pack(">I", 1)
    exth = b"EXTH" + struct.pack(">II", 12 + len(exth_rec), 1) + exth_rec
    rec0 = b"\x00" * 16 + b"MOBI" + b"\x00" * 60 + exth
    path = tmp_path / "m.mobi"
    path.write_bytes(_palmdb([rec0, first_image, cover]))
    data, _pages = media_worker._extract_mobi_cover(str(path))
    assert data == cover


# ── R74 sorting ──────────────────────────────────────────────────────────────

def test_R74_sort_added_last_read_and_recent(client):
    """added_desc = added_at DESC, id DESC; last_read_desc = this user's reads first; recent accepted."""
    add_book(1, added_at="2020-01-01 00:00:00", modified_at="2026-01-03 00:00:00")
    add_book(2, added_at="2021-01-01 00:00:00", modified_at="2026-01-01 00:00:00")
    add_book(3, added_at="2021-01-01 00:00:00", modified_at="2026-01-04 00:00:00")
    add_book(4, added_at="2019-01-01 00:00:00", modified_at="2026-01-02 00:00:00")
    for uid, bid, ts in [(TEST_USER, 2, "2030-01-01 00:00:00"),
                         (TEST_USER, 3, "2030-01-02 00:00:00"),
                         ("someone-else", 1, "2031-01-01 00:00:00")]:
        sql("INSERT INTO reading_progress (user_id, book_id, progress, last_read) VALUES (?, ?, 10, ?)",
            (uid, bid, ts))

    def ids(sort):
        r = client.get(f"/api/books?sort={sort}")
        assert r.status_code == 200
        return [b["id"] for b in r.get_json()["books"]]

    assert ids("added_desc") == [3, 2, 1, 4]
    assert ids("last_read_desc") == [3, 2, 4, 1]      # never-read (by me) last, id DESC
    assert ids("recent") == [3, 1, 4, 2]              # modified_at DESC


# ── R75 filters ──────────────────────────────────────────────────────────────

def test_R75_filters_categories_genres_formats(client):
    """/api/filters lists distinct categories, individual de-duplicated genres, and formats."""
    add_book(1, category="Webcomics", genre="Fantasy, Action", format="cbz")
    add_book(2, category="Cuisine", genre="Action,Cuisine", format="pdf", filename="b2.pdf")
    add_book(3, category="Webcomics", genre="Fantasy", format="epub", filename="b3.epub")
    data = client.get("/api/filters").get_json()
    assert data["categories"] == ["Cuisine", "Webcomics"]
    assert data["genres"] == ["Action", "Cuisine", "Fantasy"]
    assert sorted(data["formats"]) == ["cbz", "epub", "pdf"]


# ── R76 series management ────────────────────────────────────────────────────

def test_R76_collection_ordered_by_series_index(client):
    """/api/collections/<series> lists the series books ordered by series_index."""
    add_book(1, series="Saga", series_index=3.0, title="A third")
    add_book(2, series="Saga", series_index=1.0, title="Z first")
    add_book(3, series="Saga", series_index=2.0, title="M second")
    add_book(4, series="Other", series_index=1.0)
    data = client.get("/api/collections/Saga").get_json()
    assert data["type"] == "books"
    assert [b["id"] for b in data["books"]] == [2, 3, 1]


def test_R76_remove_book_from_series(client):
    """DELETE /api/books/<id>/series clears that book's series only; the book is kept."""
    add_book(1, series="Saga", series_index=1.0)
    add_book(2, series="Saga", series_index=2.0)
    assert client.delete("/api/books/1/series").status_code == 200
    rows = {r["id"]: (r["series"], r["series_index"]) for r in sql("SELECT id, series, series_index FROM books")}
    assert rows == {1: ("", 0), 2: ("Saga", 2.0)}


def test_R76_delete_series_keeps_books(client):
    """DELETE /api/series clears the series on all its books, keeps them, and reports the count."""
    add_book(1, series="Saga")
    add_book(2, series="Saga")
    add_book(3, series="Other")
    assert client.delete("/api/series", json={}).status_code == 400
    r = client.delete("/api/series", json={"series": "Saga"})
    assert r.status_code == 200 and r.get_json()["affected"] == 2
    rows = {r["id"]: r["series"] for r in sql("SELECT id, series FROM books")}
    assert rows == {1: "", 2: "", 3: "Other"}


# ── R78 genre ────────────────────────────────────────────────────────────────

def test_R78_set_genre_locks_it(client):
    """PUT /api/books/<id>/genre stores the genre, locks it, and AI classification then refuses (409)."""
    add_book(1, genre="Autres")
    r = client.put("/api/books/1/genre", json={"genre": " Fantasy, Horreur "})
    assert r.status_code == 200 and r.get_json()["genre"] == "Fantasy, Horreur"
    row = sql("SELECT genre, genre_locked FROM books WHERE id = 1")[0]
    assert (row["genre"], row["genre_locked"]) == ("Fantasy, Horreur", 1)
    assert client.post("/api/books/1/classify-genre").status_code == 409


def test_R78_classify_genre_stores_at_most_three(client, monkeypatch):
    """classify-genre (Ollama mocked) stores at most 3 known genres, main one first."""
    import genre_ai
    resp = MagicMock()
    resp.json.return_value = {"response": "Fantasy, Horreur, Thriller, Romance, Drame."}
    resp.raise_for_status.return_value = None
    monkeypatch.setattr(genre_ai.requests, "post", lambda *a, **k: resp)
    add_book(1, title="Dracula", author="Stoker")
    r = client.post("/api/books/1/classify-genre")
    assert r.status_code == 200
    stored = sql("SELECT genre FROM books WHERE id = 1")[0]["genre"]
    assert stored == r.get_json()["genre"] == "Fantasy, Horreur, Thriller"
    assert len(stored.split(",")) <= 3


# ── R82 scanner safety ───────────────────────────────────────────────────────

def test_R82_scan_with_zero_files_deletes_nothing(db, monkeypatch):
    """scan_library finding 0 files while the DB has books aborts deletion (offline library)."""
    empty = db / "empty_lib"
    empty.mkdir()
    monkeypatch.setattr(config, "BOOKS_ROOT", str(db))
    monkeypatch.setattr(config, "LIBRARY_PATHS", [str(empty)])
    monkeypatch.setattr(config, "SCAN_EXCLUDE_FILE", str(db / "absent.txt"))
    monkeypatch.setattr(scanner, "assign_collections", lambda *a, **k: 0)
    add_book(1, path=str(empty / "gone1.cbz"))
    add_book(2, path=str(empty / "gone2.epub"), filename="gone2.epub", format="epub")
    result = scanner.scan_library()
    assert result["removed"] == 0
    assert "error" in result
    assert sql("SELECT COUNT(*) FROM books")[0][0] == 2


# ── R84 manhua ad filter ─────────────────────────────────────────────────────

def _load_adfilter():
    path = os.path.join(REPO_ROOT, "scripts", "manhua_adfilter.py")
    spec = importlib.util.spec_from_file_location("manhua_adfilter_under_test", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_R84_adfilter_flags_banners_never_plates(tmp_path):
    """728x90 and wide short banners are ads; a tall 800x3000 plate is never removed."""
    adf = _load_adfilter()

    def mk(name, w, h):
        p = tmp_path / name
        Image.new("RGB", (w, h), (255, 255, 255)).save(p, "PNG")
        return str(p)

    assert adf.is_ad_image(mk("iab.png", 728, 90))
    assert adf.is_ad_image(mk("strip.png", 900, 100))       # aspect 9, h <= 120
    assert adf.is_ad_image(mk("strip120.png", 360, 120))    # aspect exactly 3, h exactly 120
    assert not adf.is_ad_image(mk("plate.png", 800, 3000))
    assert not adf.is_ad_image(mk("wide_tall.png", 800, 200))   # wide but tall -> content
    assert not adf.is_ad_image(mk("short_narrow.png", 200, 100))  # short but aspect < 3
    assert not adf.is_ad_image(str(tmp_path / "missing.png"))


# ── R18 template safety ──────────────────────────────────────────────────────

def test_R18_template_epub_sandbox_and_esc_quotes():
    """index.html renders EPUBs with allowScriptedContent: false and esc() escapes both quote types."""
    with open(os.path.join(REPO_ROOT, "templates", "index.html"), encoding="utf-8") as f:
        html = f.read()
    assert "allowScriptedContent: false" in html
    assert "allowScriptedContent: true" not in html
    start = html.index("function esc(s)")
    body = html[start:html.index("}", start)]
    assert ".replace(/\"/g, '&quot;')" in body
    assert ".replace(/'/g, '&#39;')" in body
    assert ".replace(/</g, '&lt;')" in body
