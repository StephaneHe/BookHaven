"""1.1 — SECRET_KEY must be a strong value at startup."""
import os
import sys
import pytest
from unittest.mock import patch


@pytest.fixture(autouse=True)
def isolate_config():
    sys.modules.pop("config", None)
    yield
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
