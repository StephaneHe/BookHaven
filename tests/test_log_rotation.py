"""3.16 — bookhaven.log must rotate (it had already grown to 42 MB).

Note: under pytest the root logger already carries pytest's own handlers, so
basicConfig may not attach ours; the assertions therefore target the module's
file handler directly and any bookhaven.log handler that did get attached.
"""
import logging
import os
from logging.handlers import RotatingFileHandler

os.environ.setdefault("BOOKHAVEN_SECRET_KEY", "test-secret-key-32chars-minimum!")
os.environ.setdefault("BOOKHAVEN_TEST_MODE", "1")
os.environ.setdefault("BOOKHAVEN_ENV", "development")

import bookhaven  # noqa: E402  (configures logging at import)


def test_file_handler_is_rotating():
    h = bookhaven._log_file_handler
    assert isinstance(h, RotatingFileHandler)
    assert h.maxBytes == 5 * 1024 * 1024
    assert h.backupCount == 3
    assert h.baseFilename.endswith("bookhaven.log")


def test_no_unbounded_bookhaven_log_handler_on_root():
    for h in logging.getLogger().handlers:
        if isinstance(h, logging.FileHandler) and \
                h.baseFilename.endswith("bookhaven.log"):
            assert isinstance(h, RotatingFileHandler), (
                "plain FileHandler on bookhaven.log — log grows without bound")
