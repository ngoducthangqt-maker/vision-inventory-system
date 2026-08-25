"""Unit tests for ``InventoryItemUseCases`` against a fake repository."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
from app.domain.repositories.inventory_item_repository import InventoryItemNotFoundError
from app.use_cases.inventory_item_use_cases import (
    ConsumeExceedsStockError,
    InventoryItemUseCases,
    ListInventoryItemsFilter,
    SkuAlreadyExistsError,
)

from .conftest import make_item


@pytest.fixture
def use_cases(fake_repository) -> InventoryItemUseCases:
    return InventoryItemUseCases(fake_repository)


# --------------------------------------------------------------------------- #
# Create                                                                       #
# --------------------------------------------------------------------------- #
async def test_create_item_persists_entity(use_cases, fake_repository):
    item = await use_cases.create_item(
        sku="A-1", name="A", quantity=3, price=Decimal("2.50"), category="c"
    )
    assert fake_repository.items[item.id] is item
    assert (item.sku, item.quantity, item.price, item.category) == ("A-1", 3, Decimal("2.50"), "c")


async def test_create_item_rejects_negative_quantity(use_cases):
    with pytest.raises(ValueError, match="Quantity"):
        await use_cases.create_item(sku="A-1", name="A", quantity=-1, price=Decimal(1))


async def test_create_item_rejects_negative_price(use_cases):
    with pytest.raises(ValueError, match="Price"):
        await use_cases.create_item(sku="A-1", name="A", quantity=1, price=Decimal(-1))


async def test_create_item_rejects_duplicate_sku(use_cases, fake_repository):
    existing = make_item(sku="DUP")
    fake_repository.items[existing.id] = existing
    with pytest.raises(SkuAlreadyExistsError) as excinfo:
        await use_cases.create_item(sku="DUP", name="A", quantity=1, price=Decimal(1))
    assert excinfo.value.sku == "DUP"


# --------------------------------------------------------------------------- #
# Read                                                                         #
# --------------------------------------------------------------------------- #
async def test_get_item_returns_entity(use_cases, fake_repository):
    item = make_item()
    fake_repository.items[item.id] = item
    assert await use_cases.get_item(item.id) is item


async def test_get_item_raises_for_unknown_id(use_cases):
    with pytest.raises(InventoryItemNotFoundError):
        await use_cases.get_item(uuid4())


async def test_list_items_uses_default_filter(use_cases, fake_repository):
    for i in range(3):
        item = make_item(sku=f"S-{i}")
        fake_repository.items[item.id] = item
    assert len(await use_cases.list_items()) == 3


async def test_list_items_applies_filter(use_cases, fake_repository):
    low = make_item(sku="LOW", quantity=1, category="a")
    high = make_item(sku="HIGH", quantity=99, category="b")
    for item in (low, high):
        fake_repository.items[item.id] = item

    by_category = await use_cases.list_items(ListInventoryItemsFilter(category="b"))
    assert [i.sku for i in by_category] == ["HIGH"]

    low_only = await use_cases.list_items(ListInventoryItemsFilter(low_stock_only=True))
    assert [i.sku for i in low_only] == ["LOW"]

    paginated = await use_cases.list_items(ListInventoryItemsFilter(skip=1, limit=1))
    assert len(paginated) == 1


async def test_count_items(use_cases, fake_repository):
    assert await use_cases.count_items() == 0
    item = make_item()
    fake_repository.items[item.id] = item
    assert await use_cases.count_items() == 1


# --------------------------------------------------------------------------- #
# Update                                                                       #
# --------------------------------------------------------------------------- #
async def test_update_item_applies_only_given_fields(use_cases, fake_repository):
    item = make_item(name="Old", category="old-cat")
    fake_repository.items[item.id] = item

    updated = await use_cases.update_item(item.id, name="New")
    assert updated.name == "New"
    assert updated.category == "old-cat"
    assert fake_repository.updated == [item.id]


async def test_update_item_applies_all_fields(use_cases, fake_repository):
    item = make_item()
    fake_repository.items[item.id] = item
    updated = await use_cases.update_item(
        item.id,
        name="N",
        description="D",
        price=Decimal("42.00"),
        category="C",
        low_stock_threshold=3,
    )
    assert (updated.name, updated.description, updated.price) == ("N", "D", Decimal("42.00"))
    assert (updated.category, updated.low_stock_threshold) == ("C", 3)


async def test_update_item_rejects_negative_price(use_cases, fake_repository):
    item = make_item()
    fake_repository.items[item.id] = item
    with pytest.raises(ValueError, match="Price"):
        await use_cases.update_item(item.id, price=Decimal("-0.01"))


async def test_update_item_rejects_negative_threshold(use_cases, fake_repository):
    item = make_item()
    fake_repository.items[item.id] = item
    with pytest.raises(ValueError, match="threshold"):
        await use_cases.update_item(item.id, low_stock_threshold=-1)


async def test_update_item_raises_for_unknown_id(use_cases):
    with pytest.raises(InventoryItemNotFoundError):
        await use_cases.update_item(uuid4(), name="N")


# --------------------------------------------------------------------------- #
# Delete                                                                       #
# --------------------------------------------------------------------------- #
async def test_delete_item(use_cases, fake_repository):
    item = make_item()
    fake_repository.items[item.id] = item
    await use_cases.delete_item(item.id)
    assert fake_repository.items == {}


async def test_delete_item_raises_for_unknown_id(use_cases):
    with pytest.raises(InventoryItemNotFoundError):
        await use_cases.delete_item(uuid4())


# --------------------------------------------------------------------------- #
# Restock / consume                                                            #
# --------------------------------------------------------------------------- #
async def test_restock_item(use_cases, fake_repository):
    item = make_item(quantity=4)
    fake_repository.items[item.id] = item
    updated = await use_cases.restock_item(item.id, 6)
    assert updated.quantity == 10
    assert fake_repository.updated == [item.id]


async def test_consume_item(use_cases, fake_repository):
    item = make_item(quantity=4)
    fake_repository.items[item.id] = item
    updated = await use_cases.consume_item(item.id, 4)
    assert updated.quantity == 0


async def test_consume_item_beyond_stock_raises_domain_error(use_cases, fake_repository):
    item = make_item(sku="S-1", quantity=2)
    fake_repository.items[item.id] = item
    with pytest.raises(ConsumeExceedsStockError) as excinfo:
        await use_cases.consume_item(item.id, 5)
    assert (excinfo.value.sku, excinfo.value.requested, excinfo.value.available) == ("S-1", 5, 2)
    assert item.quantity == 2
    assert fake_repository.updated == []


async def test_restock_item_raises_for_unknown_id(use_cases):
    with pytest.raises(InventoryItemNotFoundError):
        await use_cases.restock_item(uuid4(), 1)


def test_list_filter_defaults():
    params = ListInventoryItemsFilter()
    assert (params.skip, params.limit, params.category, params.low_stock_only) == (0, 50, None, False)
