"""1.2 — Path traversal in upload/confirm  |  1.3 — Filename sanitization."""
import io
import os
import zipfile
import pytest
from unittest.mock import MagicMock, patch

# Must be set BEFORE importing app/config
os.environ.setdefault("BOOKHAVEN_SECRET_KEY", "test-secret-key-32chars-minimum!")
os.environ.setdefault("BOOKHAVEN_TEST_MODE", "1")

import bookhaven  # noqa: E402
import config     # noqa: E402


def _make_epub():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("mimetype", "application/epub+zip")
        z.writestr(
            "META-INF/container.xml",
            '<?xml version="1.0"?>'
            '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
            '<rootfiles><rootfile full-path="OEBPS/content.opf"'
            ' media-type="application/oebps-package+xml"/></rootfiles></container>',
        )
        z.writestr(
            "OEBPS/content.opf",
            '<?xml version="1.0"?>'
            '<package version="2.0" xmlns="http://www.idpf.org/2007/opf">'
            "<metadata>"
            '<dc:title xmlns:dc="http://purl.org/dc/elements/1.1/">Test</dc:title>'
            "</metadata><manifest/><spine/></package>",
        )
    buf.seek(0)
    return buf


@pytest.fixture()
def client(tmp_path):
    lib_path = str(tmp_path / "Books")
    os.makedirs(lib_path)
    bookhaven.app.config["TESTING"] = True
    with patch.object(config, "LIBRARY_PATHS", [lib_path]):
        with bookhaven.app.test_client() as c:
            yield c, lib_path


def _insert_pending(tmp_path, lib_path, uid):
    temp_file = tmp_path / f"{uid}.epub"
    temp_file.write_bytes(b"fake epub content")
    bookhaven._pending_uploads[uid] = {
        "temp_path": str(temp_file),
        "filename": "fake.epub",
        "ext": ".epub",
        "meta": {
            "title": "Test", "author": "", "genre": "", "series": "",
            "series_index": 0, "category": "Books", "page_count": 0,
            "description": "",
        },
        "dest_folder": lib_path,
    }


# ── 1.2 Path traversal ──────────────────────────────────────────────────────

def test_path_traversal_windows_absolute(client, tmp_path):
    c, lib_path = client
    _insert_pending(tmp_path, lib_path, "uid-win")
    resp = c.post("/api/upload/confirm", json={
        "upload_id": "uid-win",
        "dest_folder": r"C:\Windows\System32",
    })
    bookhaven._pending_uploads.pop("uid-win", None)
    assert resp.status_code == 400
    assert b"Invalid destination" in resp.data


def test_path_traversal_sibling_folder(client, tmp_path):
    """H:\\Books\\Books2 must not match LIBRARY_PATH H:\\Books\\Books (startswith bug)."""
    c, lib_path = client
    sibling = lib_path + "Evil"  # e.g. /tmp/xxx/BooksEvil — not in LIBRARY_PATHS
    _insert_pending(tmp_path, lib_path, "uid-sib")
    resp = c.post("/api/upload/confirm", json={
        "upload_id": "uid-sib",
        "dest_folder": sibling,
    })
    bookhaven._pending_uploads.pop("uid-sib", None)
    assert resp.status_code == 400


def test_path_traversal_dotdot(client, tmp_path):
    c, lib_path = client
    _insert_pending(tmp_path, lib_path, "uid-dot")
    resp = c.post("/api/upload/confirm", json={
        "upload_id": "uid-dot",
        "dest_folder": "../../etc",
    })
    bookhaven._pending_uploads.pop("uid-dot", None)
    assert resp.status_code == 400
    assert b"Invalid destination" in resp.data


def test_valid_dest_folder_allowed(client, tmp_path):
    c, lib_path = client
    _insert_pending(tmp_path, lib_path, "uid-ok")
    mock_conn = MagicMock()
    mock_conn.execute.return_value.fetchone.return_value = {"id": 1}
    with patch.object(bookhaven, "database") as mock_db, \
         patch.object(bookhaven.scanner, "_extract_cover", return_value=False):
        mock_db.get_db.return_value = mock_conn
        resp = c.post("/api/upload/confirm", json={
            "upload_id": "uid-ok",
            "dest_folder": lib_path,
        })
    assert resp.status_code == 200


# ── Filename sanitizer unit tests ───────────────────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    # Path traversal must be stripped
    ("../../evil.epub", "evil.epub"),
    ("..\\..\\evil.epub", "evil.epub"),
    (r"C:\Windows\System32\evil.epub", "evil.epub"),
    ("/etc/passwd.epub", "passwd.epub"),
    # Unicode titles must survive (regression: secure_filename destroyed these)
    ("\u4e00\u672c\u306e\u672c.epub", "\u4e00\u672c\u306e\u672c.epub"),
    ("\u0412\u043e\u0439\u043d\u0430 \u0438 \u043c\u0438\u0440.epub",
     "\u0412\u043e\u0439\u043d\u0430 \u0438 \u043c\u0438\u0440.epub"),
    ("Les Mis\u00e9rables.epub", "Les Mis\u00e9rables.epub"),
    ("L\u2019\u00c9tranger - Camus.epub", "L\u2019\u00c9tranger - Camus.epub"),
])
def test_safe_filename_cases(raw, expected):
    assert bookhaven._safe_filename(raw) == expected


@pytest.mark.parametrize("raw", ["..", ".", "", "   ", "/", "\\", "...", "<>:|?*"])
def test_safe_filename_rejects_degenerate(raw):
    assert bookhaven._safe_filename(raw) == ""


def test_safe_filename_strips_control_chars():
    assert "\x00" not in bookhaven._safe_filename("ev\x00il.epub")


def test_safe_filename_windows_reserved():
    assert bookhaven._safe_filename("CON.epub") != "CON.epub"


# ── 1.3 Filename sanitization ───────────────────────────────────────────────

def _analyze(c, lib_path, upload_name):
    fake_meta = {
        "title": "Evil", "author": "", "genre": "", "series": "",
        "series_index": 0, "collection_path": "",
    }
    with patch.object(bookhaven.scanner, "_extract_metadata", return_value=fake_meta), \
         patch.object(bookhaven, "_determine_placement",
                      return_value=("Books", lib_path, "auto", False)):
        resp = c.post(
            "/api/upload/analyze",
            data={"file": (_make_epub(), upload_name, "application/epub+zip")},
            content_type="multipart/form-data",
        )
    data = resp.get_json() if resp.status_code == 200 else None
    if data:
        pending = bookhaven._pending_uploads.pop(data.get("upload_id"), None)
        if pending:
            try:
                os.unlink(pending["temp_path"])
            except OSError:
                pass
    return resp, data


def test_malicious_filename_sanitized(client, tmp_path):
    c, lib_path = client
    resp, data = _analyze(c, lib_path, "../../evil.epub")
    assert resp.status_code == 200
    assert data["filename"] == "evil.epub"


def test_unicode_filename_accepted(client, tmp_path):
    """Regression: secure_filename() folded CJK titles to '' and 400'd them."""
    c, lib_path = client
    name = "一本の本.epub"
    resp, data = _analyze(c, lib_path, name)
    assert resp.status_code == 200, resp.data
    assert data["filename"] == name
