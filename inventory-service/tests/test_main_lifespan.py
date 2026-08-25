"""Tests for the application lifespan hooks in ``app.main``."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import main


@pytest.fixture
def spies(monkeypatch):
    calls: list[str] = []

    async def _init_db() -> None:
        calls.append("init_db")

    async def _dispose_db() -> None:
        calls.append("dispose_db")

    monkeypatch.setattr(main, "init_db", _init_db)
    monkeypatch.setattr(main, "dispose_db", _dispose_db)
    return calls


def test_lifespan_initialises_and_disposes_db(spies, monkeypatch):
    monkeypatch.setattr(main.settings, "environment", "development")
    with TestClient(main.create_app()) as client:
        assert client.get("/health").status_code == 200
    assert spies == ["init_db", "dispose_db"]


def test_lifespan_skips_init_db_in_production(spies, monkeypatch):
    monkeypatch.setattr(main.settings, "environment", "production")
    with TestClient(main.create_app()):
        pass
    assert spies == ["dispose_db"]


def test_lifespan_tolerates_db_failures(monkeypatch):
    async def _boom() -> None:
        raise RuntimeError("no database")

    monkeypatch.setattr(main.settings, "environment", "development")
    monkeypatch.setattr(main, "init_db", _boom)
    monkeypatch.setattr(main, "dispose_db", _boom)
    with TestClient(main.create_app()) as client:
        assert client.get("/health").status_code == 200
