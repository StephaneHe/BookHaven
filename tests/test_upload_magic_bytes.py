"""2.8 — Uploads are validated by content (magic bytes), not just extension."""
import io
import os
import zipfile
import pytest
from unittest.mock import patch

os.environ.setdefault("BOOKHAVEN_SECRET_KEY", "test-secret-key-32chars-minimum!")
os.environ.setdefault("BOOKHAVEN_TEST_MODE", "1")
os.environ.setdefault("BOOKHAVEN_ENV", "development")

import bookhaven  # noqa: E402
import config     # noqa: E402


# ── Helper unit tests ───────────────────────────────────────────────────────

ZIP_HDR = b"PK\x03\x04" + b"\x00" * 64
PDF_HDR = b"%PDF-1.7\n" + b"\x00" * 64
RAR_HDR = b"Rar!\x1a\x07\x00" + b"\x00" * 64
MOBI_HDR = b"\x00" * 60 + b"BOOKMOBI" + b"\x00" * 8


@pytest.mark.parametrize("header,ext,ok", [
    (ZIP_HDR, ".epub", True),
    (ZIP_HDR, ".cbz", True),
    (PDF_HDR, ".pdf", True),
    (RAR_HDR, ".cbr", True),
    (MOBI_HDR, ".mobi", True),
    # Misnamed comics are tolerated both ways (matches _open_comic_archive)
    (RAR_HDR, ".cbz", True),
    (ZIP_HDR, ".cbr", True),
    # Content/extension mismatches must be refused
    (b"<html>evil</html>" + b"\x00" * 60, ".epub", False),
    (b"MZ\x90\x00" + b"\x00" * 64, ".pdf", False),
    (PDF_HDR, ".epub", False),
    (b"", ".epub", False),
])
def test_magic_validation(header, ext, ok):
    assert bookhaven._magic_bytes_ok(header, ext) is ok


# ── Endpoint test ───────────────────────────────────────────────────────────

@pytest.fixture()
def client(tmp_path):
    lib_path = str(tmp_path / "Books")
    os.makedirs(lib_path)
    bookhaven.app.config["TESTING"] = True
    with patch.object(config, "LIBRARY_PATHS", [lib_path]):
        with bookhaven.app.test_client() as c:
            yield c


def test_fake_epub_rejected(client):
    resp = client.post(
        "/api/upload/analyze",
        data={"file": (io.BytesIO(b"just some text, not a zip"), "fake.epub",
                       "application/epub+zip")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 400
    assert b"content" in resp.data.lower() or b"invalid" in resp.data.lower()


def test_real_zip_epub_accepted(client, tmp_path):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("mimetype", "application/epub+zip")
    buf.seek(0)
    fake_meta = {"title": "T", "author": "", "genre": "", "series": "",
                 "series_index": 0, "collection_path": ""}
    with patch.object(bookhaven.scanner, "_extract_metadata", return_value=fake_meta), \
         patch.object(bookhaven, "_determine_placement",
                      return_value=("Books", str(tmp_path / "Books"), "auto", False)):
        resp = client.post(
            "/api/upload/analyze",
            data={"file": (buf, "ok.epub", "application/epub+zip")},
            content_type="multipart/form-data",
        )
    assert resp.status_code == 200
    pending = bookhaven._pending_uploads.pop(resp.get_json()["upload_id"], None)
    if pending:
        try:
            os.unlink(pending["temp_path"])
        except OSError:
            pass
