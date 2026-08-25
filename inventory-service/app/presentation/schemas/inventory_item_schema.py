"""Pydantic v2 schemas for the ``inventory_item`` resource.

These DTOs live in the presentation layer and are intentionally distinct from
the domain entity so that internal representation and the public API can
evolve independently.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.entities.inventory_item import InventoryItem


class InventoryItemBase(BaseModel):
    """Shared fields for create/update payloads."""

    sku: str = Field(..., min_length=1, max_length=64, examples=["WIDGET-001"])
    name: str = Field(..., min_length=1, max_length=255, examples=["Widget"])
    description: str | None = Field(default=None, examples=["A handy widget"])
    quantity: int = Field(default=0, ge=0, examples=[100])
    price: Decimal = Field(default=Decimal("0.00"), ge=0, examples=["9.99"])
    category: str | None = Field(default=None, max_length=128, examples=["gadgets"])
    low_stock_threshold: int = Field(default=10, ge=0, examples=[10])


class InventoryItemCreate(InventoryItemBase):
    """Payload accepted by ``POST /inventory-items``."""

    pass


class InventoryItemUpdate(BaseModel):
    """Payload accepted by ``PATCH /inventory-items/{id}``.

    All fields are optional; only provided fields are applied.
    """

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    price: Decimal | None = Field(default=None, ge=0)
    category: str | None = Field(default=None, max_length=128)
    low_stock_threshold: int | None = Field(default=None, ge=0)


class InventoryItemResponse(InventoryItemBase):
    """Response shape for a single inventory item."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    updated_at: datetime
    is_low_stock: bool = Field(
        default=False, description="True when quantity <= low_stock_threshold."
    )
    is_in_stock: bool = Field(default=True, description="True when quantity > 0.")

    @field_validator("price", mode="before")
    @classmethod
    def _normalize_price(cls, value: object) -> Decimal:
        if value is None:
            return Decimal("0.00")
        return Decimal(str(value))

    @classmethod
    def from_entity(cls, entity: InventoryItem) -> InventoryItemResponse:
        """Build the enriched response DTO from a domain entity."""
        return cls.model_validate(
            {
                "id": entity.id,
                "sku": entity.sku,
                "name": entity.name,
                "description": entity.description,
                "quantity": entity.quantity,
                "price": entity.price,
                "category": entity.category,
                "low_stock_threshold": entity.low_stock_threshold,
                "created_at": entity.created_at,
                "updated_at": entity.updated_at,
                "is_low_stock": entity.is_low_stock(),
                "is_in_stock": entity.is_in_stock(),
            }
        )


class InventoryItemsListResponse(BaseModel):
    """Paginated collection response."""

    items: list[InventoryItemResponse]
    total: int
    skip: int
    limit: int


class RestockRequest(BaseModel):
    """Payload for the restock endpoint."""

    amount: int = Field(..., ge=1, examples=[25])


class ConsumeRequest(BaseModel):
    """Payload for the consume endpoint."""

    amount: int = Field(..., ge=1, examples=[5])
