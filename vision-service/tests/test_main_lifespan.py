"""Tests for the vision-service application lifespan."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import main


class DummyManager:
    def __init__(self) -> None:
        self.shutdown_calls = 0

    def shutdown(self) -> None:
        self.shutdown_calls += 1


@pytest.fixture
def calls(monkeypatch) -> dict:
    recorded: dict = {"init_db": 0, "dispose_db": 0, "manager": DummyManager()}

    def init_db() -> None:
        recorded["init_db"] += 1

    def dispose_db() -> None:
        recorded["dispose_db"] += 1

    monkeypatch.setattr(main, "init_db", init_db)
    monkeypatch.setattr(main, "dispose_db", dispose_db)
    monkeypatch.setattr(main, "get_job_manager", lambda: recorded["manager"])
    return recorded


def run_lifespan() -> None:
    with TestClient(main.create_app()) as client:
        assert client.get("/health").status_code == 200


def test_lifespan_initialises_db_and_shuts_the_manager_down(calls, monkeypatch):
    monkeypatch.setattr(main.settings, "environment", "development")
    run_lifespan()
    assert calls["init_db"] == 1
    assert calls["dispose_db"] == 1
    assert calls["manager"].shutdown_calls == 1


def test_lifespan_skips_db_initialisation_in_production(calls, monkeypatch):
    monkeypatch.setattr(main.settings, "environment", "production")
    run_lifespan()
    assert calls["init_db"] == 0
    assert calls["dispose_db"] == 1


def test_lifespan_tolerates_db_initialisation_failure(calls, monkeypatch):
    monkeypatch.setattr(main.settings, "environment", "development")

    def boom() -> None:
        raise RuntimeError("no postgres")

    monkeypatch.setattr(main, "init_db", boom)
    run_lifespan()
    assert calls["manager"].shutdown_calls == 1
