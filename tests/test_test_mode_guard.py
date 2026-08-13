"""2.9 — BOOKHAVEN_TEST_MODE must refuse to activate outside a dev environment:
a stray env var in production would silently disable all auth."""
import os
import pytest

os.environ.setdefault("BOOKHAVEN_SECRET_KEY", "test-secret-key-32chars-minimum!")
os.environ.setdefault("BOOKHAVEN_TEST_MODE", "1")
os.environ.setdefault("BOOKHAVEN_ENV", "development")

import bookhaven  # noqa: E402


def test_disabled_when_env_var_absent():
    assert bookhaven._resolve_test_mode({}) is False
    assert bookhaven._resolve_test_mode({"BOOKHAVEN_TEST_MODE": "0"}) is False


def test_enabled_in_dev_environment():
    assert bookhaven._resolve_test_mode(
        {"BOOKHAVEN_TEST_MODE": "1", "BOOKHAVEN_ENV": "development"}) is True
    assert bookhaven._resolve_test_mode(
        {"BOOKHAVEN_TEST_MODE": "1", "BOOKHAVEN_ENV": "test"}) is True


def test_refuses_without_explicit_dev_env():
    with pytest.raises(RuntimeError, match="BOOKHAVEN_ENV"):
        bookhaven._resolve_test_mode({"BOOKHAVEN_TEST_MODE": "1"})


def test_refuses_in_production_env():
    with pytest.raises(RuntimeError):
        bookhaven._resolve_test_mode(
            {"BOOKHAVEN_TEST_MODE": "1", "BOOKHAVEN_ENV": "production"})
