"""Inventory item use cases.

Each public method corresponds to a discrete application operation (create,
retrieve, list, update, delete, restock, consume). The class depends only on
the ``InventoryItemRepository`` *contract*, so it is trivially unit-testable
with an in-memory fake repository.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from app.domain.entities.inventory_item import InventoryItem
from app.domain.repositories.inventory_item_repository import (
    InventoryItemNotFoundError,
    InventoryItemRepository,
)


class ConsumeExceedsStockError(Exception):
    """Raised when a consume request asks for more stock than available."""

    def __init__(self, sku: str, requested: int, available: int) -> None:
        self.sku = sku
        self.requested = requested
        self.available = available
        super().__init__(
            f"Cannot consume {requested} units of sku={sku!r}: "
            f"only {available} in stock."
        )


class SkuAlreadyExistsError(Exception):
    """Raised when creating an item whose SKU is already taken."""

    def __init__(self, sku: str) -> None:
        self.sku = sku
        super().__init__(f"SKU {sku!r} already exists.")


@dataclass(frozen=True)
class ListInventoryItemsFilter:
    """Value object carrying query parameters for listing items."""

    skip: int = 0
    limit: int = 50
    category: str | None = None
    low_stock_only: bool = False


class InventoryItemUseCases:
    """Application service orchestrating ``InventoryItem`` operations."""

    def __init__(self, repository: InventoryItemRepository) -> None:
        self._repo = repository

    # ------------------------------------------------------------------ #
    # Create                                                              #
    # ------------------------------------------------------------------ #
    async def create_item(
        self,
        *,
        sku: str,
        name: str,
        quantity: int,
        price: Decimal,
        description: str | None = None,
        category: str | None = None,
        low_stock_threshold: int = 10,
    ) -> InventoryItem:
        if quantity < 0:
            raise ValueError("Quantity must be non-negative.")
        if price < 0:
            raise ValueError("Price must be non-negative.")
        if await self._repo.get_by_sku(sku) is not None:
            raise SkuAlreadyExistsError(sku)

        item = InventoryItem(
            sku=sku,
            name=name,
            quantity=quantity,
            price=price,
            description=description,
            category=category,
            low_stock_threshold=low_stock_threshold,
        )
        return await self._repo.add(item)

    # ------------------------------------------------------------------ #
    # Read                                                                #
    # ------------------------------------------------------------------ #
    async def get_item(self, item_id: UUID) -> InventoryItem:
        return await self._repo.get_by_id(item_id)

    async def list_items(
        self, filter_params: ListInventoryItemsFilter | None = None
    ) -> list[InventoryItem]:
        params = filter_params or ListInventoryItemsFilter()
        return await self._repo.list(
            skip=params.skip,
            limit=params.limit,
            category=params.category,
            low_stock_only=params.low_stock_only,
        )

    async def count_items(self) -> int:
        return await self._repo.count()

    # ------------------------------------------------------------------ #
    # Update                                                              #
    # ------------------------------------------------------------------ #
    async def update_item(
        self,
        item_id: UUID,
        *,
        name: str | None = None,
        description: str | None = None,
        price: Decimal | None = None,
        category: str | None = None,
        low_stock_threshold: int | None = None,
    ) -> InventoryItem:
        item = await self._repo.get_by_id(item_id)
        if name is not None:
            item.name = name
        if description is not None:
            item.description = description
        if price is not None:
            if price < 0:
                raise ValueError("Price must be non-negative.")
            item.price = price
        if category is not None:
            item.category = category
        if low_stock_threshold is not None:
            if low_stock_threshold < 0:
                raise ValueError("Low-stock threshold must be non-negative.")
            item.low_stock_threshold = low_stock_threshold
        item.touch()
        return await self._repo.update(item)

    # ------------------------------------------------------------------ #
    # Delete                                                              #
    # ------------------------------------------------------------------ #
    async def delete_item(self, item_id: UUID) -> None:
        # Ensure the item exists so callers get a meaningful 404.
        await self._repo.get_by_id(item_id)
        await self._repo.delete(item_id)

    # ------------------------------------------------------------------ #
    # Domain operations                                                   #
    # ------------------------------------------------------------------ #
    async def restock_item(self, item_id: UUID, amount: int) -> InventoryItem:
        item = await self._repo.get_by_id(item_id)
        item.restock(amount)
        return await self._repo.update(item)

    async def consume_item(self, item_id: UUID, amount: int) -> InventoryItem:
        item = await self._repo.get_by_id(item_id)
        if amount > item.quantity:
            raise ConsumeExceedsStockError(item.sku, amount, item.quantity)
        item.consume(amount)
        return await self._repo.update(item)


__all__ = [
    "InventoryItemUseCases",
    "ListInventoryItemsFilter",
    "ConsumeExceedsStockError",
    "SkuAlreadyExistsError",
    "InventoryItemNotFoundError",
]
