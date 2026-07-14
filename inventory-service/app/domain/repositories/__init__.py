"""Domain repository interfaces.

A repository is an abstract contract describing *what* persistence
operations the application needs, without saying *how* they are performed.
The infrastructure layer provides concrete implementations.
"""

from app.domain.repositories.inventory_item_repository import (
    InventoryItemRepository,
    InventoryItemNotFoundError,
)

__all__ = ["InventoryItemRepository", "InventoryItemNotFoundError"]
