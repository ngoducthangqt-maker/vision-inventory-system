"""Tests for the ``X-API-Key`` dependency guarding the /api/v1 routes."""

from __future__ import annotations

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.core.security import require_api_key


def _client(monkeypatch: pytest.MonkeyPatch, **env: str) -> TestClient:
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    monkeypatch.setattr("app.core.security.get_settings", lambda: Settings())

    app = FastAPI()

    @app.get("/api/v1/ping", dependencies=[Depends(require_api_key)])
    async def ping() -> dict[str, bool]:
        return {"ok": True}

    return TestClient(app)


def test_valid_key_is_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client(monkeypatch, API_KEY="s3cret")
    assert client.get("/api/v1/ping", headers={"X-API-Key": "s3cret"}).status_code == 200


@pytest.mark.parametrize("headers", [{}, {"X-API-Key": "wrong"}])
def test_missing_or_wrong_key_is_rejected(
    monkeypatch: pytest.MonkeyPatch, headers: dict[str, str]
) -> None:
    client = _client(monkeypatch, API_KEY="s3cret")
    assert client.get("/api/v1/ping", headers=headers).status_code == 401


def test_unset_key_stays_open_in_development(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client(monkeypatch, API_KEY="", ENVIRONMENT="development")
    assert client.get("/api/v1/ping").status_code == 200


def test_unset_key_fails_closed_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client(monkeypatch, API_KEY="", ENVIRONMENT="production")
    assert client.get("/api/v1/ping").status_code == 503


def test_production_wildcard_cors_is_dropped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", "*")
    monkeypatch.setenv("ENVIRONMENT", "production")
    assert Settings().cors_origins_list == []
    monkeypatch.setenv("ENVIRONMENT", "development")
    assert Settings().cors_origins_list == ["*"]


def test_docs_are_disabled_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    assert Settings().docs_enabled is False
    monkeypatch.setenv("ENABLE_DOCS", "true")
    assert Settings().docs_enabled is True
