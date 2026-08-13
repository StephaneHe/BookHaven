"""3.10 — _pending_uploads is touched from waitress worker threads without a
lock: confirm checked membership, then popped later — a concurrent cancel in
between made the pop raise KeyError (500). And temp files in data/uploads were
never purged after a restart (pending entries only live in memory)."""
import os
import time
from unittest.mock import patch

import pytest

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


class _RacingLibraryPaths:
    """Iterated during confirm's dest_folder validation — removing the pending
    entry here simulates a concurrent cancel between check and pop."""

    def __init__(self, paths, upload_id):
        self._paths = paths
        self._uid = upload_id

    def __iter__(self):
        bookhaven._pending_uploads.pop(self._uid, None)
        return iter(self._paths)


def test_confirm_survives_concurrent_removal(tmp_path):
    uid = "race"
    temp_file = tmp_path / "race.epub"
    temp_file.write_bytes(b"x")
    lib = str(tmp_path / "Books")
    os.makedirs(lib)
    bookhaven._pending_uploads[uid] = {
        "temp_path": str(temp_file), "filename": "race.epub", "ext": ".epub",
        "meta": {}, "dest_folder": lib, "created_at": time.time(),
    }
    bookhaven.app.config["TESTING"] = True
    with patch.object(config, "LIBRARY_PATHS", _RacingLibraryPaths([lib], uid)):
        with bookhaven.app.test_client() as c:
            resp = c.post("/api/upload/confirm", json={"upload_id": uid})
    assert resp.status_code == 400  # graceful "expired", not a KeyError 500


def test_purge_orphan_uploads(tmp_path):
    (tmp_path / "a.epub").write_bytes(b"x")
    (tmp_path / "b.pdf").write_bytes(b"y")
    kept = tmp_path / "kept.epub"
    kept.write_bytes(b"z")
    bookhaven._pending_uploads["live"] = {
        "temp_path": str(kept), "filename": "kept.epub", "ext": ".epub",
        "meta": {}, "dest_folder": "d", "created_at": time.time(),
    }
    removed = bookhaven._purge_orphan_uploads(str(tmp_path))
    assert removed == 2
    assert sorted(os.listdir(tmp_path)) == ["kept.epub"]


def test_purge_orphan_uploads_missing_dir_is_noop(tmp_path):
    assert bookhaven._purge_orphan_uploads(str(tmp_path / "nope")) == 0
