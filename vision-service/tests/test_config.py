"""Tests for ``app.config``."""

from __future__ import annotations

import pytest
from app.config import Settings, get_settings
from pydantic import ValidationError


def _settings(**overrides) -> Settings:
    return Settings(_env_file=None, **overrides)


def test_database_url_uses_psycopg2_driver():
    settings = _settings(
        postgres_user="u",
        postgres_password="p",
        postgres_host="db",
        postgres_port=6543,
        postgres_db="vision",
    )
    assert settings.database_url == "postgresql+psycopg2://u:p@db:6543/vision"


def test_carton_class_names_are_lower_cased_and_trimmed():
    settings = _settings(default_carton_class_names=" Carton , BOX ,, cardboard Box ")
    assert settings.carton_class_names_list == ["carton", "box", "cardboard box"]


def test_cors_origins_wildcard_and_list():
    assert _settings(cors_origins=" * ").cors_origins_list == ["*"]
    assert _settings(cors_origins="http://a.test ,http://b.test").cors_origins_list == [
        "http://a.test",
        "http://b.test",
    ]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"confidence_threshold": -0.1},
        {"confidence_threshold": 1.1},
        {"default_frame_sample_interval": 0},
        {"default_report_interval_seconds": 0.5},
    ],
)
def test_out_of_range_values_are_rejected(kwargs):
    with pytest.raises(ValidationError):
        _settings(**kwargs)


def test_settings_read_from_environment(monkeypatch):
    monkeypatch.setenv("REPOSITORY_MODE", "inmemory")
    monkeypatch.setenv("CONFIDENCE_THRESHOLD", "0.75")
    settings = _settings()
    assert settings.repository_mode == "inmemory"
    assert settings.confidence_threshold == 0.75


def test_get_settings_is_cached():
    assert get_settings() is get_settings()
