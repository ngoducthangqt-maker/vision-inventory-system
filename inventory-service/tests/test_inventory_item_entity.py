"""Unit tests for the ``InventoryItem`` domain entity."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

import pytest
from app.domain.entities.inventory_item import InventoryItem

from .conftest import make_item


def test_defaults_are_generated():
    item = InventoryItem(sku="A-1", name="A", quantity=1, price=Decimal("1.00"))
    assert isinstance(item.id, UUID)
    assert item.description is None
    assert item.category is None
    assert item.low_stock_threshold == 10
    assert item.created_at.tzinfo is timezone.utc
    assert item.updated_at.tzinfo is timezone.utc


@pytest.mark.parametrize(
    ("quantity", "threshold", "expected"),
    [(0, 10, True), (10, 10, True), (11, 10, False), (0, 0, True), (1, 0, False)],
)
def test_is_low_stock(quantity, threshold, expected):
    item = make_item(quantity=quantity, low_stock_threshold=threshold)
    assert item.is_low_stock() is expected


@pytest.mark.parametrize(("quantity", "expected"), [(0, False), (1, True), (500, True)])
def test_is_in_stock(quantity, expected):
    assert make_item(quantity=quantity).is_in_stock() is expected


def test_restock_increases_quantity_and_touches():
    item = make_item(quantity=5)
    before = item.updated_at
    item.restock(7)
    assert item.quantity == 12
    assert item.updated_at >= before


def test_restock_zero_is_allowed():
    item = make_item(quantity=5)
    item.restock(0)
    assert item.quantity == 5


def test_restock_rejects_negative_amount():
    item = make_item(quantity=5)
    with pytest.raises(ValueError, match="non-negative"):
        item.restock(-1)
    assert item.quantity == 5


def test_consume_decreases_quantity():
    item = make_item(quantity=5)
    item.consume(2)
    assert item.quantity == 3


def test_consume_entire_stock_is_allowed():
    item = make_item(quantity=5)
    item.consume(5)
    assert item.quantity == 0
    assert item.is_in_stock() is False


def test_consume_rejects_negative_amount():
    item = make_item(quantity=5)
    with pytest.raises(ValueError, match="non-negative"):
        item.consume(-3)
    assert item.quantity == 5


def test_consume_rejects_amount_above_stock():
    item = make_item(quantity=2)
    with pytest.raises(ValueError, match="only 2 in stock"):
        item.consume(3)
    assert item.quantity == 2


def test_touch_refreshes_updated_at_only():
    item = make_item()
    stale = datetime(2000, 1, 1, tzinfo=timezone.utc)
    item.updated_at = stale
    created = item.created_at
    item.touch()
    assert item.updated_at > stale
    assert item.created_at == created
