"""SSRF guard on the metadata/cover fetchers.

_fetch_json / _fetch_image receive URLs taken from Open Library / Google Books
responses, i.e. from a remote source we do not control. urllib.request.urlopen
also speaks file:// and ftp://, and would happily reach private/loopback hosts
(LAN services, cloud metadata endpoints). _is_safe_url must reject all of that
BEFORE any network call, so the fetchers return None without hitting urlopen.
"""
import os
from unittest.mock import patch

os.environ.setdefault("BOOKHAVEN_SECRET_KEY", "test-secret-key-32chars-minimum!")

import media_worker  # noqa: E402


# --- _is_safe_url: schemes and non-global hosts are rejected ----------------

def test_rejects_file_scheme():
    assert media_worker._is_safe_url("file:///etc/passwd") is False


def test_rejects_ftp_scheme():
    assert media_worker._is_safe_url("ftp://example.com/x.jpg") is False


def test_rejects_empty_and_garbage():
    assert media_worker._is_safe_url("") is False
    assert media_worker._is_safe_url("not a url") is False
    assert media_worker._is_safe_url("http://") is False


def test_rejects_loopback_and_private_literals():
    for url in (
        "http://127.0.0.1/x",
        "http://localhost/x",
        "http://10.0.0.5/x",
        "http://192.168.1.10:8097/x",
        "http://169.254.169.254/latest/meta-data/",  # cloud metadata
        "http://[::1]/x",
    ):
        assert media_worker._is_safe_url(url) is False, url


def test_accepts_public_https_host():
    # Pin DNS resolution to a public address so the test is offline-stable.
    public = [(None, None, None, None, ("140.82.112.3", 443))]
    with patch("media_worker.socket.getaddrinfo", return_value=public):
        assert media_worker._is_safe_url("https://covers.openlibrary.org/x.jpg") is True


def test_rejects_public_name_resolving_to_private_ip():
    # DNS-rebinding-style: a public hostname must still be blocked if it
    # resolves to a private address.
    private = [(None, None, None, None, ("10.1.2.3", 80))]
    with patch("media_worker.socket.getaddrinfo", return_value=private):
        assert media_worker._is_safe_url("http://evil.example.com/x") is False


# --- fetchers short-circuit before urlopen ----------------------------------

def test_fetch_json_blocks_file_without_urlopen():
    with patch("media_worker.urllib.request.urlopen") as m:
        assert media_worker._fetch_json("file:///etc/passwd") is None
        m.assert_not_called()


def test_fetch_image_blocks_private_without_urlopen():
    with patch("media_worker.urllib.request.urlopen") as m:
        assert media_worker._fetch_image("http://169.254.169.254/x") is None
        m.assert_not_called()
