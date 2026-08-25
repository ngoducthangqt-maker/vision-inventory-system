"""Reusable HTTP error translations for the presentation layer.

Every route that resolves an item by id needs the same 404 (and the same
detail message), so the mapping from domain/use-case exceptions to
``HTTPException`` lives here instead of being repeated per route.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, status

from app.use_cases.inventory_item_use_cases import ConsumeExceedsStockError


def item_not_found(item_id: UUID) -> HTTPException:
    """404 for an unknown inventory item id."""
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Inventory item with id={item_id} not found.",
    )


def sku_conflict(sku: str) -> HTTPException:
    """409 for a SKU that is already taken."""
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=f"An item with sku={sku!r} already exists.",
    )


def insufficient_stock(exc: ConsumeExceedsStockError) -> HTTPException:
    """409 for a consume request exceeding the available stock."""
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=(
            f"Cannot consume {exc.requested} units of sku={exc.sku!r}: "
            f"only {exc.available} in stock."
        ),
    )


__all__ = ["item_not_found", "sku_conflict", "insufficient_stock"]
