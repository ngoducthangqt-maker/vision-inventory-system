"""Tests for ``app.core.config``."""

from __future__ import annotations

from app.core.config import Settings, get_settings


def _settings(**overrides) -> Settings:
    # ``_env_file=None`` keeps the test independent of any local .env file.
    return Settings(_env_file=None, **overrides)


def test_database_url_is_built_from_postgres_parts():
    settings = _settings(
        postgres_user="u",
        postgres_password="p",
        postgres_host="db",
        postgres_port=6543,
        postgres_db="mydb",
    )
    assert settings.database_url == "postgresql+asyncpg://u:p@db:6543/mydb"


def test_cors_origins_wildcard():
    assert _settings(cors_origins="*").cors_origins_list == ["*"]
    assert _settings(cors_origins="  *  ").cors_origins_list == ["*"]


def test_cors_origins_comma_separated_are_trimmed():
    settings = _settings(cors_origins="http://a.test, http://b.test ,,")
    assert settings.cors_origins_list == ["http://a.test", "http://b.test"]


def test_settings_read_from_environment(monkeypatch):
    monkeypatch.setenv("APP_NAME", "from-env")
    monkeypatch.setenv("POSTGRES_PORT", "1234")
    settings = _settings()
    assert settings.app_name == "from-env"
    assert settings.postgres_port == 1234


def test_get_settings_is_cached():
    assert get_settings() is get_settings()
