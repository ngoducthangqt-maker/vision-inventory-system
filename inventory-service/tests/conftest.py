"""Shared fixtures for the inventory-service test suite.

Nothing here talks to PostgreSQL: the repository contract is satisfied either
by an in-memory fake (``FakeInventoryItemRepository``) or by the real
SQLAlchemy adapter running against an in-memory SQLite database.
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from decimal import Decimal
from uuid import UUID

import pytest

# The real settings default to Postgres; the DSN is only used when a session is
# actually opened, but pinning it keeps import-time engine creation predictable.
os.environ.setdefault("ENVIRONMENT", "test")

from app.domain.entities.inventory_item import InventoryItem  # noqa: E402
from app.domain.repositories.inventory_item_repository import (  # noqa: E402
    InventoryItemNotFoundError,
    InventoryItemRepository,
)


class FakeInventoryItemRepository(InventoryItemRepository):
    """Dict-backed implementation of the repository contract."""

    def __init__(self) -> None:
        self.items: dict[UUID, InventoryItem] = {}
        self.updated: list[UUID] = []

    async def add(self, item: InventoryItem) -> InventoryItem:
        self.items[item.id] = item
        return item

    async def get_by_id(self, item_id: UUID) -> InventoryItem:
        if item_id not in self.items:
            raise InventoryItemNotFoundError(item_id)
        return self.items[item_id]

    async def get_by_sku(self, sku: str) -> InventoryItem | None:
        return next((i for i in self.items.values() if i.sku == sku), None)

    async def list(
        self,
        *,
        skip: int = 0,
        limit: int = 50,
        category: str | None = None,
        low_stock_only: bool = False,
    ) -> list[InventoryItem]:
        items = list(self.items.values())
        if category is not None:
            items = [i for i in items if i.category == category]
        if low_stock_only:
            items = [i for i in items if i.is_low_stock()]
        return items[skip : skip + limit]

    async def update(self, item: InventoryItem) -> InventoryItem:
        self.updated.append(item.id)
        self.items[item.id] = item
        return item

    async def delete(self, item_id: UUID) -> None:
        self.items.pop(item_id, None)

    async def count(self) -> int:
        return len(self.items)


def make_item(
    *,
    sku: str = "WIDGET-001",
    name: str = "Widget",
    quantity: int = 100,
    price: str = "9.99",
    category: str | None = "gadgets",
    low_stock_threshold: int = 10,
) -> InventoryItem:
    """Build a domain entity with sensible defaults."""
    return InventoryItem(
        sku=sku,
        name=name,
        quantity=quantity,
        price=Decimal(price),
        category=category,
        low_stock_threshold=low_stock_threshold,
    )


@pytest.fixture
def fake_repository() -> FakeInventoryItemRepository:
    return FakeInventoryItemRepository()


@pytest.fixture
async def sqlite_session() -> AsyncGenerator[object, None]:
    """Yield an ``AsyncSession`` bound to a fresh in-memory SQLite database."""
    import app.infrastructure.models.inventory_item_model  # noqa: F401  (register table)
    from app.core.database import Base
    from sqlalchemy.ext.asyncio import (
        AsyncSession,
        async_sessionmaker,
        create_async_engine,
    )

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()
