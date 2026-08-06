"""1.1 — SECRET_KEY must be a strong value at startup."""
import os
import sys
import pytest
from unittest.mock import patch


@pytest.fixture(autouse=True)
def isolate_config():
    """Re-import config in isolation, then put the ORIGINAL module object back.

    Leaving config popped from sys.modules is not enough: modules that already
    did `import config` (database.py, bookhaven.py) keep a reference to the old
    object, while a later `import config` builds a new one. A test that then
    monkeypatches config.DB_PATH patches the new object only -- database.py
    still reads the old one and writes to the real library database.
    """
    saved = sys.modules.get("config")
    sys.modules.pop("config", None)
    try:
        yield
    finally:
        if saved is not None:
            sys.modules["config"] = saved
        else:
            sys.modules.pop("config", None)


def test_missing_secret_key_raises():
    backup = os.environ.pop("BOOKHAVEN_SECRET_KEY", None)
    try:
        with patch("dotenv.load_dotenv"):
            with pytest.raises(RuntimeError, match="BOOKHAVEN_SECRET_KEY"):
                import config
    finally:
        if backup is not None:
            os.environ["BOOKHAVEN_SECRET_KEY"] = backup


def test_dev_secret_key_raises():
    backup = os.environ.get("BOOKHAVEN_SECRET_KEY")
    os.environ["BOOKHAVEN_SECRET_KEY"] = "bookhaven-dev-secret"
    try:
        with patch("dotenv.load_dotenv"):
            with pytest.raises(RuntimeError, match="BOOKHAVEN_SECRET_KEY"):
                import config
    finally:
        if backup is not None:
            os.environ["BOOKHAVEN_SECRET_KEY"] = backup
        elif "BOOKHAVEN_SECRET_KEY" in os.environ:
            del os.environ["BOOKHAVEN_SECRET_KEY"]


def test_short_secret_key_raises():
    backup = os.environ.get("BOOKHAVEN_SECRET_KEY")
    os.environ["BOOKHAVEN_SECRET_KEY"] = "a" * 31
    try:
        with patch("dotenv.load_dotenv"):
            with pytest.raises(RuntimeError, match="too short"):
                import config
    finally:
        if backup is not None:
            os.environ["BOOKHAVEN_SECRET_KEY"] = backup
        elif "BOOKHAVEN_SECRET_KEY" in os.environ:
            del os.environ["BOOKHAVEN_SECRET_KEY"]


def test_strong_secret_key_ok():
    backup = os.environ.get("BOOKHAVEN_SECRET_KEY")
    os.environ["BOOKHAVEN_SECRET_KEY"] = "test-secret-key-32chars-minimum!"
    try:
        with patch("dotenv.load_dotenv"):
            import config
            assert config.SECRET_KEY == "test-secret-key-32chars-minimum!"
    finally:
        if backup is not None:
            os.environ["BOOKHAVEN_SECRET_KEY"] = backup
        elif "BOOKHAVEN_SECRET_KEY" in os.environ:
            del os.environ["BOOKHAVEN_SECRET_KEY"]
