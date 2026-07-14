"""FastAPI dependency-injection wiring.

This is the *composition root*: the only place that knows which concrete
implementations back which interfaces. Swapping the database for an
in-memory fake (for tests) means changing a single function here.
"""

from __future__ import annotations

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.domain.repositories.inventory_item_repository import InventoryItemRepository
from app.infrastructure.repositories.inventory_item_repository_impl import (
    SqlAlchemyInventoryItemRepository,
)
from app.use_cases.inventory_item_use_cases import InventoryItemUseCases


async def get_inventory_item_repository(
    session: AsyncSession = Depends(get_db_session),
) -> InventoryItemRepository:
    """Provide the concrete SQLAlchemy repository bound to the request session."""
    return SqlAlchemyInventoryItemRepository(session)


async def get_inventory_item_use_cases(
    repository: InventoryItemRepository = Depends(get_inventory_item_repository),
) -> InventoryItemUseCases:
    """Provide the use-case service bound to a repository implementation."""
    return InventoryItemUseCases(repository)


__all__ = [
    "get_inventory_item_repository",
    "get_inventory_item_use_cases",
]
