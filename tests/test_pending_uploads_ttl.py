"""3.14 — Pending uploads expire: abandoned analyze() calls no longer leak
memory entries and temp files forever."""
import io
import os
import time
import zipfile
import pytest
from unittest.mock import patch

os.environ.setdefault("BOOKHAVEN_SECRET_KEY", "test-secret-key-32chars-minimum!")
os.environ.setdefault("BOOKHAVEN_TEST_MODE", "1")
os.environ.setdefault("BOOKHAVEN_ENV", "development")

import bookhaven  # noqa: E402
import config     # noqa: E402


@pytest.fixture(autouse=True)
def clean_pending():
    bookhaven._pending_uploads.clear()
    yield
    bookhaven._pending_uploads.clear()


def _stale_entry(tmp_path, uid, age_seconds):
    temp_file = tmp_path / f"{uid}.epub"
    temp_file.write_bytes(b"x")
    bookhaven._pending_uploads[uid] = {
        "temp_path": str(temp_file),
        "filename": "x.epub", "ext": ".epub", "meta": {}, "dest_folder": "d",
        "created_at": time.time() - age_seconds,
    }
    return temp_file


def test_stale_entries_purged_with_temp_file(tmp_path):
    stale = _stale_entry(tmp_path, "old", age_seconds=7200)
    fresh = _stale_entry(tmp_path, "new", age_seconds=10)
    bookhaven._cleanup_pending_uploads(max_age=3600)
    assert "old" not in bookhaven._pending_uploads
    assert not stale.exists()
    assert "new" in bookhaven._pending_uploads
    assert fresh.exists()


def test_analyze_stamps_created_at_and_purges(tmp_path):
    _stale_entry(tmp_path, "old", age_seconds=7200)
    lib_path = str(tmp_path / "Books")
    os.makedirs(lib_path)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("mimetype", "application/epub+zip")
    buf.seek(0)
    fake_meta = {"title": "T", "author": "", "genre": "", "series": "",
                 "series_index": 0, "collection_path": ""}
    bookhaven.app.config["TESTING"] = True
    with patch.object(config, "LIBRARY_PATHS", [lib_path]), \
         patch.object(bookhaven.scanner, "_extract_metadata", return_value=fake_meta), \
         patch.object(bookhaven, "_determine_placement",
                      return_value=("Books", lib_path, "auto", False)):
        with bookhaven.app.test_client() as c:
            resp = c.post(
                "/api/upload/analyze",
                data={"file": (buf, "t.epub", "application/epub+zip")},
                content_type="multipart/form-data",
            )
    assert resp.status_code == 200
    uid = resp.get_json()["upload_id"]
    assert "old" not in bookhaven._pending_uploads
    entry = bookhaven._pending_uploads.pop(uid)
    assert entry["created_at"] == pytest.approx(time.time(), abs=30)
    os.unlink(entry["temp_path"])
