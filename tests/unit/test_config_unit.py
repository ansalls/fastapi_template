import pytest
from app.config import Settings

pytestmark = pytest.mark.unit


def test_settings_normalizes_supported_algorithm():
    cfg = Settings(algorithm="hs512")
    assert cfg.algorithm == "HS512"


def test_settings_rejects_unsupported_algorithm():
    with pytest.raises(ValueError):
        Settings(algorithm="RS256")


def test_settings_oauth_frontend_callback_defaults_to_root_when_empty():
    cfg = Settings(oauth_frontend_callback_url="")
    assert cfg.oauth_frontend_callback_url == "/"


def test_settings_oauth_frontend_callback_rejects_fragment():
    with pytest.raises(ValueError):
        Settings(oauth_frontend_callback_url="https://app.example.com/callback#frag")


def test_settings_oauth_frontend_callback_rejects_invalid_absolute_scheme():
    with pytest.raises(ValueError):
        Settings(oauth_frontend_callback_url="ftp://app.example.com/callback")


def test_settings_oauth_frontend_callback_accepts_absolute_http_url():
    cfg = Settings(oauth_frontend_callback_url="https://app.example.com/callback")
    assert cfg.oauth_frontend_callback_url == "https://app.example.com/callback"


def test_settings_oauth_frontend_callback_rejects_relative_non_absolute_path():
    with pytest.raises(ValueError):
        Settings(oauth_frontend_callback_url="callback")


def test_settings_rejects_weak_secret_in_production():
    with pytest.raises(ValueError):
        Settings(environment="production", secret_key="replace-this-in-production")


def test_settings_accepts_strong_secret_in_production():
    cfg = Settings(environment="production", secret_key="a" * 32)
    assert cfg.secret_key == "a" * 32
