"""Tests for the SQLAlchemy repository adapter (against in-memory SQLite)."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
from app.domain.repositories.inventory_item_repository import InventoryItemNotFoundError
from app.infrastructure.repositories.inventory_item_repository_impl import (
    DuplicateSkuError,
    SqlAlchemyInventoryItemRepository,
)

from .conftest import make_item


@pytest.fixture
def repository(sqlite_session) -> SqlAlchemyInventoryItemRepository:
    return SqlAlchemyInventoryItemRepository(sqlite_session)


async def test_add_then_get_by_id_roundtrip(repository):
    item = make_item(sku="RT-1", quantity=7, price="12.34")
    stored = await repository.add(item)
    fetched = await repository.get_by_id(stored.id)
    assert (fetched.sku, fetched.quantity, fetched.price) == ("RT-1", 7, Decimal("12.34"))
    assert fetched is not stored  # a fresh entity is mapped from the row


async def test_add_duplicate_sku_raises(repository):
    await repository.add(make_item(sku="DUP"))
    with pytest.raises(DuplicateSkuError) as excinfo:
        await repository.add(make_item(sku="DUP"))
    assert excinfo.value.sku == "DUP"


async def test_get_by_id_raises_for_unknown_id(repository):
    with pytest.raises(InventoryItemNotFoundError):
        await repository.get_by_id(uuid4())


async def test_get_by_sku(repository):
    await repository.add(make_item(sku="FIND-ME"))
    assert (await repository.get_by_sku("FIND-ME")).sku == "FIND-ME"
    assert await repository.get_by_sku("MISSING") is None


async def test_update_persists_changes(repository):
    stored = await repository.add(make_item(sku="UPD", quantity=1))
    stored.name = "Renamed"
    stored.restock(4)
    updated = await repository.update(stored)
    assert (updated.name, updated.quantity) == ("Renamed", 5)
    assert (await repository.get_by_id(stored.id)).quantity == 5


async def test_update_raises_for_unknown_id(repository):
    with pytest.raises(InventoryItemNotFoundError):
        await repository.update(make_item(sku="GHOST"))


async def test_update_to_taken_sku_raises_duplicate(repository):
    await repository.add(make_item(sku="TAKEN"))
    other = await repository.add(make_item(sku="OTHER"))
    other.sku = "TAKEN"
    with pytest.raises(DuplicateSkuError):
        await repository.update(other)


async def test_delete_removes_row_and_is_idempotent(repository):
    stored = await repository.add(make_item(sku="DEL"))
    await repository.delete(stored.id)
    with pytest.raises(InventoryItemNotFoundError):
        await repository.get_by_id(stored.id)
    await repository.delete(stored.id)  # no-op, must not raise


async def test_count(repository):
    assert await repository.count() == 0
    await repository.add(make_item(sku="C-1"))
    await repository.add(make_item(sku="C-2"))
    assert await repository.count() == 2


async def test_list_filters_by_category(repository):
    await repository.add(make_item(sku="G-1", category="gadgets"))
    await repository.add(make_item(sku="T-1", category="tools"))
    assert [i.sku for i in await repository.list(category="tools")] == ["T-1"]


async def test_list_filters_low_stock_only(repository):
    await repository.add(make_item(sku="LOW", quantity=2, low_stock_threshold=5))
    await repository.add(make_item(sku="HIGH", quantity=50, low_stock_threshold=5))
    assert [i.sku for i in await repository.list(low_stock_only=True)] == ["LOW"]


async def test_list_paginates(repository):
    for i in range(5):
        await repository.add(make_item(sku=f"P-{i}"))
    page = await repository.list(skip=1, limit=2)
    assert len(page) == 2
    assert await repository.count() == 5
