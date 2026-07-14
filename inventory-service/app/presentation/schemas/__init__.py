"""Pydantic schemas (request/response DTOs) for the inventory resource."""

from app.presentation.schemas.inventory_item_schema import (
    ConsumeRequest,
    InventoryItemCreate,
    InventoryItemResponse,
    InventoryItemUpdate,
    InventoryItemsListResponse,
    RestockRequest,
)

__all__ = [
    "InventoryItemCreate",
    "InventoryItemUpdate",
    "InventoryItemResponse",
    "InventoryItemsListResponse",
    "RestockRequest",
    "ConsumeRequest",
]
