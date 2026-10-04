"""R98 (server side): comic pages are cacheable so readers can pre-cache the next
chapters, the book detail lists the upcoming chapters, and archive listings are
cached instead of re-read on every page request.
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


def _cbz(path, n=3):
    with zipfile.ZipFile(path, "w") as z:
        for i in range(n):
            buf = io.BytesIO()
            Image.new("RGB", (40, 240), (10 * i, 50, 90)).save(buf, "PNG")
            z.writestr(f"p_{i}.png", buf.getvalue())


@pytest.fixture()
def client(tmp_path):
    db_path = str(tmp_path / "t.db")
    bookhaven.app.config["TESTING"] = True
    bookhaven._page_list_cache.clear()
    with patch.object(config, "DB_PATH", db_path):
        database.init_db()
        conn = database.get_db()
        for n in range(1, 9):                       # series of 8 chapters, one file each
            p = tmp_path / f"ch{n}.cbz"
            _cbz(p)
            conn.execute("INSERT INTO books (id, path, filename, title, format, series, series_index, "
                         "file_size, modified_at) VALUES (?, ?, ?, ?, 'cbz', 'Saga', ?, ?, '2026-10-04 10:00:00')",
                         (n, str(p), p.name, f"Chapitre {n}", float(n), p.stat().st_size))
        conn.commit()
        conn.close()
        with bookhaven.app.test_client() as c:
            yield c


def _version(client, bid):
    return client.get(f"/api/books/{bid}/comic-pages").get_json()["content_version"]


def test_R98_versioned_page_is_immutable_and_has_etag(client):
    v = _version(client, 1)
    r = client.get(f"/api/books/1/comic-page/0?v={v}")
    assert r.status_code == 200 and r.mimetype == "image/png"
    assert "immutable" in r.headers["Cache-Control"] and "max-age=31536000" in r.headers["Cache-Control"]
    assert r.headers.get("ETag")


def test_R98_unversioned_or_stale_version_revalidates(client):
    for url in ("/api/books/1/comic-page/0", "/api/books/1/comic-page/0?v=old"):
        r = client.get(url)
        assert r.status_code == 200
        assert "no-cache" in r.headers["Cache-Control"] and "immutable" not in r.headers["Cache-Control"]


def test_R98_if_none_match_returns_304_without_body(client):
    etag = client.get("/api/books/1/comic-page/1").headers["ETag"]
    r = client.get("/api/books/1/comic-page/1", headers={"If-None-Match": etag})
    assert r.status_code == 304 and r.data == b"" and r.headers["ETag"] == etag
    other = client.get("/api/books/1/comic-page/2").headers["ETag"]
    assert other != etag                            # one ETag per page


def test_R98_version_change_changes_etag(client):
    e1 = client.get("/api/books/2/comic-page/0").headers["ETag"]
    conn = database.get_db()
    conn.execute("UPDATE books SET modified_at = '2026-10-05 10:00:00' WHERE id = 2")
    conn.commit()
    conn.close()
    assert client.get("/api/books/2/comic-page/0").headers["ETag"] != e1


def test_R98_book_detail_lists_upcoming_chapters_up_to_five(client):
    d = client.get("/api/books/2").get_json()
    assert [b["id"] for b in d["series_following"]] == [3, 4, 5, 6, 7]
    assert set(d["series_following"][0]) == {"id", "title", "format", "file_size"}
    assert d["series_following"][0]["file_size"] > 0
    assert [b["id"] for b in client.get("/api/books/7").get_json()["series_following"]] == [8]
    assert client.get("/api/books/8").get_json()["series_following"] == []


def test_R98_archive_listing_cached_between_page_requests(client, monkeypatch):
    calls = []
    real = bookhaven._list_comic_pages
    monkeypatch.setattr(bookhaven, "_list_comic_pages", lambda p, f: calls.append(p) or real(p, f))
    for i in range(3):
        assert client.get(f"/api/books/3/comic-page/{i}").status_code == 200
    client.get("/api/books/3/comic-pages")
    assert len(calls) == 1
    # a rewritten archive (new mtime) is listed again
    path = calls[0]
    st = os.stat(path)
    os.utime(path, (st.st_atime, st.st_mtime + 10))
    client.get("/api/books/3/comic-page/0")
    assert len(calls) == 2
