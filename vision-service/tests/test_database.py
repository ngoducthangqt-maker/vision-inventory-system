"""Tests for the lazy sync engine / session factory helpers."""

from __future__ import annotations

import pytest
from app.core import database
from sqlalchemy import text


@pytest.fixture(autouse=True)
def sqlite_settings(monkeypatch, tmp_path):
    """Point the lazy engine at a throwaway SQLite file and reset the singletons.

    A file-backed URL is used because the pooling options passed by
    ``get_engine`` are unsupported by SQLite's in-memory pool.
    """
    monkeypatch.setattr(database, "_engine", None)
    monkeypatch.setattr(database, "_SessionLocal", None)

    class StubSettings:
        database_url = f"sqlite:///{tmp_path / 'vision.db'}"
        db_echo = False
        db_pool_size = 5
        db_max_overflow = 10

    monkeypatch.setattr(database, "get_settings", lambda: StubSettings())
    yield
    database.dispose_db()


def test_get_engine_is_cached():
    assert database.get_engine() is database.get_engine()


def test_get_session_factory_is_cached_and_bound_to_the_engine():
    factory = database.get_session_factory()
    assert factory is database.get_session_factory()
    assert factory.kw["bind"] is database.get_engine()


def test_module_getattr_exposes_engine_and_session_local():
    assert database.engine is database.get_engine()
    assert database.SessionLocal is database.get_session_factory()


def test_module_getattr_rejects_unknown_names():
    with pytest.raises(AttributeError, match="has no attribute 'nope'"):
        database.__getattr__("nope")


def test_init_db_creates_all_tables():
    import app.infrastructure.models  # noqa: F401 - registers the ORM metadata

    from tests.test_repository import (
        _compile_jsonb_sqlite,  # noqa: F401 - SQLite DDL for JSONB
    )

    database.init_db()
    with database.get_engine().connect() as connection:
        names = {
            row[0]
            for row in connection.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
        }
    assert {"detection_jobs", "detection_events"} <= names


def test_get_db_session_commits_and_closes():
    database.init_db()
    generator = database.get_db_session()
    session = next(generator)
    session.execute(text("SELECT 1"))
    with pytest.raises(StopIteration):
        next(generator)
    assert not session.in_transaction()


def test_get_db_session_rolls_back_on_error():
    generator = database.get_db_session()
    session = next(generator)
    with pytest.raises(RuntimeError):
        generator.throw(RuntimeError("boom"))
    assert not session.in_transaction()


def test_dispose_db_resets_the_singletons():
    first = database.get_engine()
    database.get_session_factory()
    database.dispose_db()
    assert database._engine is None  # noqa: SLF001
    assert database._SessionLocal is None  # noqa: SLF001
    assert database.get_engine() is not first


def test_dispose_db_without_an_engine_is_safe():
    database.dispose_db()
    database.dispose_db()
    assert database._engine is None  # noqa: SLF001
