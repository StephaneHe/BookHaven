"""2.5 — Global security headers on every response (after_request)."""
import os
import pytest

os.environ.setdefault("BOOKHAVEN_SECRET_KEY", "test-secret-key-32chars-minimum!")
os.environ.setdefault("BOOKHAVEN_TEST_MODE", "1")

import bookhaven  # noqa: E402


@pytest.fixture()
def client():
    bookhaven.app.config["TESTING"] = True
    with bookhaven.app.test_client() as c:
        yield c


def test_security_headers_on_index(client):
    resp = client.get("/")
    assert resp.headers.get("X-Content-Type-Options") == "nosniff"
    assert resp.headers.get("X-Frame-Options") == "SAMEORIGIN"
    assert resp.headers.get("Referrer-Policy")
    csp = resp.headers.get("Content-Security-Policy", "")
    assert "default-src 'self'" in csp
    assert "object-src 'none'" in csp


def test_security_headers_on_api(client):
    resp = client.get("/api/version")
    assert resp.headers.get("X-Content-Type-Options") == "nosniff"
    assert resp.headers.get("Content-Security-Policy")


def test_csp_allows_reader_needs(client):
    """epub.js/pdf.js need blob: workers/frames and inline scripts — CSP must
    not break the readers."""
    csp = client.get("/").headers.get("Content-Security-Policy", "")
    assert "'unsafe-inline'" in csp
    assert "blob:" in csp


def test_epub_resource_keeps_strict_csp(client, tmp_path):
    """The per-endpoint strict CSP (default-src 'none') must not be overwritten
    by the global one."""
    import zipfile
    from unittest.mock import MagicMock, patch
    epub = tmp_path / "b.epub"
    with zipfile.ZipFile(epub, "w") as z:
        z.writestr("pic.jpg", b"\xff\xd8\xff\xe0")
    mock_conn = MagicMock()
    mock_conn.execute.return_value.fetchone.return_value = {
        "path": str(epub), "format": "epub",
    }
    with patch.object(bookhaven.database, "get_db", return_value=mock_conn):
        resp = client.get("/api/books/1/epub-resource/pic.jpg")
    assert "default-src 'none'" in resp.headers.get("Content-Security-Policy", "")
