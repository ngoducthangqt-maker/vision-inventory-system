"""Concrete repository implementations."""

from app.infrastructure.repositories.inventory_item_repository_impl import (
    SqlAlchemyInventoryItemRepository,
)

__all__ = ["SqlAlchemyInventoryItemRepository"]
