"""SQLAlchemy/PostgreSQL implementation of ``InventoryItemRepository``.

This adapter translates between the ``InventoryItem`` domain entity and the
``InventoryItemModel`` ORM row. The use-case layer only ever sees the domain
entity, keeping the persistence technology fully hidden.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.inventory_item import InventoryItem
from app.domain.repositories.inventory_item_repository import (
    InventoryItemNotFoundError,
    InventoryItemRepository,
)
from app.infrastructure.models.inventory_item_model import InventoryItemModel


class DuplicateSkuError(Exception):
    """Raised when persisting an item whose SKU already exists."""

    def __init__(self, sku: str) -> None:
        self.sku = sku
        super().__init__(f"An inventory item with sku={sku!r} already exists.")


class SqlAlchemyInventoryItemRepository(InventoryItemRepository):
    """PostgreSQL-backed repository for ``InventoryItem`` aggregates."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ------------------------------------------------------------------ #
    # Mapping helpers                                                     #
    # ------------------------------------------------------------------ #
    @staticmethod
    def _to_entity(row: InventoryItemModel) -> InventoryItem:
        """Convert an ORM row into a fresh domain entity."""
        return InventoryItem(
            id=row.id,
            sku=row.sku,
            name=row.name,
            description=row.description,
            quantity=row.quantity,
            price=row.price,
            category=row.category,
            low_stock_threshold=row.low_stock_threshold,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    @staticmethod
    def _apply_to_model(item: InventoryItem, row: InventoryItemModel) -> None:
        """Copy mutable fields from the entity onto an existing ORM row."""
        row.sku = item.sku
        row.name = item.name
        row.description = item.description
        row.quantity = item.quantity
        row.price = item.price
        row.category = item.category
        row.low_stock_threshold = item.low_stock_threshold
        row.updated_at = item.updated_at

    # ------------------------------------------------------------------ #
    # Write operations                                                    #
    # ------------------------------------------------------------------ #
    async def add(self, item: InventoryItem) -> InventoryItem:
        row = InventoryItemModel(
            id=item.id,
            sku=item.sku,
            name=item.name,
            description=item.description,
            quantity=item.quantity,
            price=item.price,
            category=item.category,
            low_stock_threshold=item.low_stock_threshold,
            created_at=item.created_at,
            updated_at=item.updated_at,
        )
        self._session.add(row)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            raise DuplicateSkuError(item.sku) from exc
        await self._session.refresh(row)
        return self._to_entity(row)

    async def update(self, item: InventoryItem) -> InventoryItem:
        stmt = select(InventoryItemModel).where(InventoryItemModel.id == item.id)
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        if row is None:
            raise InventoryItemNotFoundError(item.id)
        self._apply_to_model(item, row)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            raise DuplicateSkuError(item.sku) from exc
        await self._session.refresh(row)
        return self._to_entity(row)

    async def delete(self, item_id: UUID) -> None:
        stmt = select(InventoryItemModel).where(InventoryItemModel.id == item_id)
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        if row is None:
            raise InventoryItemNotFoundError(item_id)
        await self._session.delete(row)
        await self._session.flush()

    # ------------------------------------------------------------------ #
    # Read operations                                                     #
    # ------------------------------------------------------------------ #
    async def get_by_id(self, item_id: UUID) -> InventoryItem:
        stmt = select(InventoryItemModel).where(InventoryItemModel.id == item_id)
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        if row is None:
            raise InventoryItemNotFoundError(item_id)
        return self._to_entity(row)

    async def get_by_sku(self, sku: str) -> InventoryItem | None:
        stmt = select(InventoryItemModel).where(InventoryItemModel.sku == sku)
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        return self._to_entity(row) if row else None

    async def list(
        self,
        *,
        skip: int = 0,
        limit: int = 50,
        category: str | None = None,
        low_stock_only: bool = False,
    ) -> list[InventoryItem]:
        stmt = select(InventoryItemModel).offset(skip).limit(limit)
        if category is not None:
            stmt = stmt.where(InventoryItemModel.category == category)
        if low_stock_only:
            stmt = stmt.where(
                InventoryItemModel.quantity <= InventoryItemModel.low_stock_threshold
            )
        stmt = stmt.order_by(InventoryItemModel.created_at.desc())
        result = await self._session.execute(stmt)
        rows = result.scalars().all()
        return [self._to_entity(r) for r in rows]

    async def count(self) -> int:
        stmt = select(func.count()).select_from(InventoryItemModel)
        result = await self._session.execute(stmt)
        return int(result.scalar_one())


__all__ = [
    "SqlAlchemyInventoryItemRepository",
    "DuplicateSkuError",
]
