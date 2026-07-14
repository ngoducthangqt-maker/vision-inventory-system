"""Run inventory-service without Postgres (in-memory repository).

Boots the REAL inventory-service FastAPI app on port 8000 with the database
repository overridden by an in-memory async fake, so the service is fully
functional (CRUD + restock/consume) for local development and demos without
spinning up Postgres. Data is lost on restart.

Usage::

    cd inventory-service
    python scripts/run_inmemory.py
    # -> http://localhost:8000/docs
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from uuid import UUID, uuid4

# Make inventory-service importable (app/ lives in the repo root, not scripts/).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Skip the dev-mode init_db() (which would try to connect to Postgres) — the
# repository is overridden in-memory below, so no DB is needed at all.
os.environ.setdefault("ENVIRONMENT", "production")

import uvicorn
from fastapi import FastAPI

from app.domain.entities.inventory_item import InventoryItem
from app.domain.repositories.inventory_item_repository import (
    InventoryItemNotFoundError,
    InventoryItemRepository,
)
from app.dependencies import get_inventory_item_repository
from app.main import create_app


class InMemoryInventoryRepository(InventoryItemRepository):
    """Async in-memory implementation of the inventory repository contract."""

    def __init__(self) -> None:
        self._db: dict[UUID, InventoryItem] = {}

    async def add(self, item: InventoryItem) -> InventoryItem:
        self._db[item.id] = item
        return item

    async def get_by_id(self, item_id: UUID) -> InventoryItem:
        if item_id not in self._db:
            raise InventoryItemNotFoundError(item_id)
        return self._db[item_id]

    async def get_by_sku(self, sku: str) -> InventoryItem | None:
        return next((i for i in self._db.values() if i.sku == sku), None)

    async def list(self, *, skip: int = 0, limit: int = 50, category: str | None = None, low_stock_only: bool = False) -> list[InventoryItem]:
        items = list(self._db.values())
        if category is not None:
            items = [i for i in items if i.category == category]
        if low_stock_only:
            items = [i for i in items if i.is_low_stock()]
        return items[skip : skip + limit]

    async def update(self, item: InventoryItem) -> InventoryItem:
        self._db[item.id] = item
        return item

    async def delete(self, item_id: UUID) -> None:
        self._db.pop(item_id, None)

    async def count(self) -> int:
        return len(self._db)


# Single shared instance so all requests see the same data.
_SHARED_REPO = InMemoryInventoryRepository()


async def _override_repo() -> InMemoryInventoryRepository:
    return _SHARED_REPO


app: FastAPI = create_app()
app.dependency_overrides[get_inventory_item_repository] = _override_repo


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")
