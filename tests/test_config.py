import pytest
from pydantic import ValidationError

from app.core.config import Settings


def settings(**values) -> Settings:
    return Settings(_env_file=None, **values)


def test_dev_allows_the_default_key():
    assert settings(secret_key="change-me", session_https_only=False).secret_key == "change-me"


@pytest.mark.parametrize("https_only", [False, True])
def test_empty_key_is_refused(https_only):
    with pytest.raises(ValidationError, match="SECRET_KEY is empty"):
        settings(secret_key="", session_https_only=https_only)


@pytest.mark.parametrize("key", ["change-me", "x" * 31])
def test_production_refuses_default_or_short_key(key):
    with pytest.raises(ValidationError, match="at least 32"):
        settings(secret_key=key, session_https_only=True)


def test_production_accepts_a_generated_key():
    key = "k" * 43  # the length of secrets.token_urlsafe(32)
    assert settings(secret_key=key, session_https_only=True).secret_key == key
