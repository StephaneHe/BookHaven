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


# ── 1.3 Filename sanitization ───────────────────────────────────────────────

def test_malicious_filename_sanitized(client, tmp_path):
    c, lib_path = client
    fake_meta = {
        "title": "Evil", "author": "", "genre": "", "series": "",
        "series_index": 0, "collection_path": "",
    }
    with patch.object(bookhaven.scanner, "_extract_metadata", return_value=fake_meta), \
         patch.object(bookhaven, "_determine_placement",
                      return_value=("Books", lib_path, "auto", False)):
        resp = c.post(
            "/api/upload/analyze",
            data={"file": (_make_epub(), "../../evil.epub", "application/epub+zip")},
            content_type="multipart/form-data",
        )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["filename"] == "evil.epub"
    # cleanup temp file
    uid = data.get("upload_id")
    if uid:
        pending = bookhaven._pending_uploads.pop(uid, None)
        if pending:
            try:
                os.unlink(pending["temp_path"])
            except OSError:
                pass
