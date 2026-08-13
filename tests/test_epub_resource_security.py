"""2.1 — Stored XSS via /api/epub-resource: HTML inside an EPUB zip must never
be served as executable text/html on the app origin."""
import os
import zipfile
import pytest
from unittest.mock import MagicMock, patch

# Must be set BEFORE importing app/config
os.environ.setdefault("BOOKHAVEN_SECRET_KEY", "test-secret-key-32chars-minimum!")
os.environ.setdefault("BOOKHAVEN_TEST_MODE", "1")

import bookhaven  # noqa: E402


@pytest.fixture()
def evil_epub(tmp_path):
    """EPUB containing an attacker-controlled HTML page plus normal resources."""
    epub = tmp_path / "evil.epub"
    with zipfile.ZipFile(epub, "w") as z:
        z.writestr("mimetype", "application/epub+zip")
        z.writestr(
            "META-INF/container.xml",
            '<?xml version="1.0"?><container><rootfiles>'
            '<rootfile full-path="content.opf"/></rootfiles></container>',
        )
        z.writestr("content.opf", "<package/>")
        z.writestr("evil.html", "<html><script>alert(document.cookie)</script></html>")
        z.writestr("evil.xhtml", "<html><script>alert(1)</script></html>")
        z.writestr("pic.jpg", b"\xff\xd8\xff\xe0fakejpeg")
        z.writestr("style.css", "body { color: red; }")
        z.writestr("img.svg", '<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>')
    return str(epub)


@pytest.fixture()
def client(evil_epub):
    bookhaven.app.config["TESTING"] = True
    mock_conn = MagicMock()
    mock_conn.execute.return_value.fetchone.return_value = {
        "path": evil_epub, "format": "epub",
    }
    with patch.object(bookhaven.database, "get_db", return_value=mock_conn):
        with bookhaven.app.test_client() as c:
            yield c


def test_html_entry_not_served_as_html(client):
    resp = client.get("/api/books/1/epub-resource/evil.html")
    assert resp.status_code == 200
    assert not resp.content_type.startswith("text/html")
    assert "attachment" in resp.headers.get("Content-Disposition", "")
    assert resp.headers.get("X-Content-Type-Options") == "nosniff"


def test_xhtml_entry_not_served_as_xhtml(client):
    resp = client.get("/api/books/1/epub-resource/evil.xhtml")
    assert resp.status_code == 200
    assert "xhtml" not in resp.content_type
    assert not resp.content_type.startswith("text/html")
    assert "attachment" in resp.headers.get("Content-Disposition", "")


def test_image_keeps_real_mime(client):
    resp = client.get("/api/books/1/epub-resource/pic.jpg")
    assert resp.status_code == 200
    assert resp.content_type.startswith("image/jpeg")
    assert resp.headers.get("X-Content-Type-Options") == "nosniff"


def test_css_keeps_real_mime(client):
    resp = client.get("/api/books/1/epub-resource/style.css")
    assert resp.status_code == 200
    assert resp.content_type.startswith("text/css")


def test_svg_script_neutralized_by_csp(client):
    """SVG must stay usable in <img> but scripts must be blocked on navigation."""
    resp = client.get("/api/books/1/epub-resource/img.svg")
    assert resp.status_code == 200
    csp = resp.headers.get("Content-Security-Policy", "")
    assert "default-src 'none'" in csp
