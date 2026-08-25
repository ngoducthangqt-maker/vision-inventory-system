"""Tests for the presentation-layer Pydantic schemas."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from app.presentation.schemas.inventory_item_schema import (
    ConsumeRequest,
    InventoryItemCreate,
    InventoryItemResponse,
    InventoryItemsListResponse,
    InventoryItemUpdate,
    RestockRequest,
)
from pydantic import ValidationError


def test_create_applies_defaults():
    payload = InventoryItemCreate(sku="A-1", name="A")
    assert (payload.quantity, payload.price, payload.low_stock_threshold) == (
        0,
        Decimal("0.00"),
        10,
    )
    assert payload.description is None and payload.category is None


@pytest.mark.parametrize(
    "kwargs",
    [
        {"sku": "", "name": "A"},
        {"sku": "A-1", "name": ""},
        {"sku": "A-1", "name": "A", "quantity": -1},
        {"sku": "A-1", "name": "A", "price": "-0.01"},
        {"sku": "A-1", "name": "A", "low_stock_threshold": -1},
        {"sku": "x" * 65, "name": "A"},
    ],
)
def test_create_rejects_invalid_payloads(kwargs):
    with pytest.raises(ValidationError):
        InventoryItemCreate(**kwargs)


def test_update_allows_empty_payload():
    payload = InventoryItemUpdate()
    assert payload.model_dump(exclude_unset=True) == {}


@pytest.mark.parametrize("kwargs", [{"name": ""}, {"price": "-1"}, {"low_stock_threshold": -1}])
def test_update_rejects_invalid_values(kwargs):
    with pytest.raises(ValidationError):
        InventoryItemUpdate(**kwargs)


def _response_payload(**overrides):
    now = datetime.now(timezone.utc)
    data = {
        "id": uuid4(),
        "sku": "A-1",
        "name": "A",
        "quantity": 5,
        "price": "1.50",
        "created_at": now,
        "updated_at": now,
    }
    data.update(overrides)
    return data


def test_response_normalizes_price_from_float_and_string():
    assert InventoryItemResponse(**_response_payload(price=2.5)).price == Decimal("2.5")
    assert InventoryItemResponse(**_response_payload(price="3.75")).price == Decimal("3.75")


def test_response_price_none_defaults_to_zero():
    assert InventoryItemResponse(**_response_payload(price=None)).price == Decimal("0.00")


def test_response_stock_flags_default():
    response = InventoryItemResponse(**_response_payload())
    assert (response.is_low_stock, response.is_in_stock) == (False, True)


def test_list_response_shape():
    response = InventoryItemsListResponse(
        items=[InventoryItemResponse(**_response_payload())], total=1, skip=0, limit=50
    )
    assert response.total == 1 and len(response.items) == 1


@pytest.mark.parametrize("model", [RestockRequest, ConsumeRequest])
def test_amount_must_be_at_least_one(model):
    assert model(amount=1).amount == 1
    for invalid in (0, -5):
        with pytest.raises(ValidationError):
            model(amount=invalid)
