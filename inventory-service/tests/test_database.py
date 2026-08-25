"""Tests for the async engine / session helpers.

The module-level engine points at Postgres, so it is swapped for an in-memory
SQLite engine for the duration of each test.
"""

from __future__ import annotations

import pytest
from app.core import database
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


@pytest.fixture
async def sqlite_engine(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
    )
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "AsyncSessionLocal", session_factory)
    yield engine
    await engine.dispose()


async def test_get_db_session_yields_a_usable_session(sqlite_engine):
    generator = database.get_db_session()
    session = await generator.__anext__()
    assert (await session.execute(text("SELECT 1"))).scalar_one() == 1
    with pytest.raises(StopAsyncIteration):
        await generator.__anext__()
    assert not session.in_transaction()


async def test_get_db_session_rolls_back_and_reraises(sqlite_engine):
    generator = database.get_db_session()
    session = await generator.__anext__()
    await session.execute(text("SELECT 1"))
    with pytest.raises(RuntimeError, match="boom"):
        await generator.athrow(RuntimeError("boom"))
    assert not session.in_transaction()


async def test_init_db_creates_the_inventory_table(sqlite_engine):
    import app.infrastructure.models.inventory_item_model  # noqa: F401 - registers metadata

    await database.init_db()
    async with sqlite_engine.connect() as connection:
        result = await connection.execute(
            text("SELECT name FROM sqlite_master WHERE type='table'")
        )
        assert "inventory_items" in {row[0] for row in result}


async def test_dispose_db_disposes_the_engine(monkeypatch):
    disposed = []

    class StubEngine:
        async def dispose(self) -> None:
            disposed.append(True)

    monkeypatch.setattr(database, "engine", StubEngine())
    await database.dispose_db()
    assert disposed == [True]
