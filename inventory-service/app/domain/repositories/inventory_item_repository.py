"""Abstract repository contract for ``InventoryItem`` aggregates.

The use-case layer depends on this interface, never on a concrete
SQLAlchemy/PostgreSQL implementation. This is what keeps the business
logic decoupled from the database technology (the "dependency rule" of
Clean Architecture).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Protocol
from uuid import UUID

from app.domain.entities.inventory_item import InventoryItem


class InventoryItemNotFoundError(Exception):
    """Raised when an inventory item cannot be located by its identifier."""

    def __init__(self, item_id: UUID) -> None:
        self.item_id = item_id
        super().__init__(f"Inventory item with id={item_id} not found.")


class InventoryItemRepository(Protocol):
    """Protocol-based repository contract.

    Using ``Protocol`` keeps the interface lightweight (structural typing)
    while still allowing an ``ABC``-style contract for documentation. Any
    object implementing these methods satisfies the contract.
    """

    @abstractmethod
    async def add(self, item: InventoryItem) -> InventoryItem:
        """Persist a brand-new inventory item."""

    @abstractmethod
    async def get_by_id(self, item_id: UUID) -> InventoryItem:
        """Return the item with ``item_id`` or raise ``InventoryItemNotFoundError``."""

    @abstractmethod
    async def get_by_sku(self, sku: str) -> InventoryItem | None:
        """Return the item matching ``sku`` or ``None`` if it does not exist."""

    @abstractmethod
    async def list(
        self,
        *,
        skip: int = 0,
        limit: int = 50,
        category: str | None = None,
        low_stock_only: bool = False,
    ) -> list[InventoryItem]:
        """Return a filtered, paginated collection of inventory items."""

    @abstractmethod
    async def update(self, item: InventoryItem) -> InventoryItem:
        """Persist changes to an already-stored inventory item."""

    @abstractmethod
    async def delete(self, item_id: UUID) -> None:
        """Remove an inventory item. No-op (idempotent) if it does not exist."""

    @abstractmethod
    async def count(self) -> int:
        """Return the total number of stored inventory items."""


# Keep a classic ABC alias for code that prefers nominal typing / isinstance.
_AbstractRepository = ABC  # noqa: N816 (intentional alias for readability)


class AbstractInventoryItemRepository(InventoryItemRepository, ABC):
    """Convenience ABC base for concrete repositories that want nominal typing."""

    pass


__all__ = [
    "InventoryItemRepository",
    "AbstractInventoryItemRepository",
    "InventoryItemNotFoundError",
]
