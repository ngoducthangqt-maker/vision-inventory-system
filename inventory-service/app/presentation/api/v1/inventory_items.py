"""HTTP routes for the ``inventory-items`` resource.

The router only depends on ``InventoryItemUseCases`` (injected via FastAPI's
``Depends``). It maps domain/infrastructure exceptions to appropriate HTTP
status codes, keeping the use-case layer HTTP-agnostic.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import Response

from app.dependencies import get_inventory_item_use_cases
from app.domain.repositories.inventory_item_repository import (
    InventoryItemNotFoundError,
)
from app.infrastructure.repositories.inventory_item_repository_impl import (
    DuplicateSkuError,
)
from app.presentation.schemas.inventory_item_schema import (
    ConsumeRequest,
    InventoryItemCreate,
    InventoryItemResponse,
    InventoryItemUpdate,
    InventoryItemsListResponse,
    RestockRequest,
)
from app.use_cases.inventory_item_use_cases import (
    ConsumeExceedsStockError,
    InventoryItemUseCases,
    ListInventoryItemsFilter,
    SkuAlreadyExistsError,
)

router = APIRouter(prefix="/inventory-items", tags=["inventory-items"])


def _to_response(entity) -> InventoryItemResponse:  # type: ignore[no-untyped-def]
    """Convert a domain entity into the enriched API response DTO."""
    data = {
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
    return InventoryItemResponse.model_validate(data)


# --------------------------------------------------------------------------- #
# Create                                                                       #
# --------------------------------------------------------------------------- #
@router.post(
    "",
    response_model=InventoryItemResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        409: {"description": "An item with the given SKU already exists."},
        422: {"description": "Validation error."},
    },
    summary="Create a new inventory item",
)
async def create_inventory_item(
    payload: InventoryItemCreate,
    use_cases: InventoryItemUseCases = Depends(get_inventory_item_use_cases),
) -> InventoryItemResponse:
    try:
        entity = await use_cases.create_item(
            sku=payload.sku,
            name=payload.name,
            quantity=payload.quantity,
            price=payload.price,
            description=payload.description,
            category=payload.category,
            low_stock_threshold=payload.low_stock_threshold,
        )
    except (DuplicateSkuError, SkuAlreadyExistsError):
        from fastapi import HTTPException

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"An item with sku={payload.sku!r} already exists.",
        ) from None
    return _to_response(entity)


# --------------------------------------------------------------------------- #
# Read (list + count)                                                          #
# --------------------------------------------------------------------------- #
@router.get(
    "",
    response_model=InventoryItemsListResponse,
    summary="List inventory items",
)
async def list_inventory_items(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    category: str | None = Query(default=None),
    low_stock_only: bool = Query(default=False),
    use_cases: InventoryItemUseCases = Depends(get_inventory_item_use_cases),
) -> InventoryItemsListResponse:
    filter_params = ListInventoryItemsFilter(
        skip=skip, limit=limit, category=category, low_stock_only=low_stock_only
    )
    items = await use_cases.list_items(filter_params)
    total = await use_cases.count_items()
    return InventoryItemsListResponse(
        items=[_to_response(i) for i in items],
        total=total,
        skip=skip,
        limit=limit,
    )


# --------------------------------------------------------------------------- #
# Read (single)                                                                #
# --------------------------------------------------------------------------- #
@router.get(
    "/{item_id}",
    response_model=InventoryItemResponse,
    responses={404: {"description": "Item not found."}},
    summary="Retrieve a single inventory item by id",
)
async def get_inventory_item(
    item_id: UUID,
    use_cases: InventoryItemUseCases = Depends(get_inventory_item_use_cases),
) -> InventoryItemResponse:
    try:
        entity = await use_cases.get_item(item_id)
    except InventoryItemNotFoundError:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Inventory item with id={item_id} not found.",
        ) from None
    return _to_response(entity)


# --------------------------------------------------------------------------- #
# Update                                                                       #
# --------------------------------------------------------------------------- #
@router.patch(
    "/{item_id}",
    response_model=InventoryItemResponse,
    responses={404: {"description": "Item not found."}},
    summary="Partially update an inventory item",
)
async def update_inventory_item(
    item_id: UUID,
    payload: InventoryItemUpdate,
    use_cases: InventoryItemUseCases = Depends(get_inventory_item_use_cases),
) -> InventoryItemResponse:
    try:
        entity = await use_cases.update_item(
            item_id,
            name=payload.name,
            description=payload.description,
            price=payload.price,
            category=payload.category,
            low_stock_threshold=payload.low_stock_threshold,
        )
    except InventoryItemNotFoundError:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Inventory item with id={item_id} not found.",
        ) from None
    return _to_response(entity)


# --------------------------------------------------------------------------- #
# Delete                                                                       #
# --------------------------------------------------------------------------- #
@router.delete(
    "/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={404: {"description": "Item not found."}},
    summary="Delete an inventory item",
)
async def delete_inventory_item(
    item_id: UUID,
    use_cases: InventoryItemUseCases = Depends(get_inventory_item_use_cases),
) -> Response:
    try:
        await use_cases.delete_item(item_id)
    except InventoryItemNotFoundError:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Inventory item with id={item_id} not found.",
        ) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --------------------------------------------------------------------------- #
# Domain operations: restock / consume                                         #
# --------------------------------------------------------------------------- #
@router.post(
    "/{item_id}/restock",
    response_model=InventoryItemResponse,
    responses={404: {"description": "Item not found."}},
    summary="Restock an inventory item",
)
async def restock_inventory_item(
    item_id: UUID,
    payload: RestockRequest,
    use_cases: InventoryItemUseCases = Depends(get_inventory_item_use_cases),
) -> InventoryItemResponse:
    try:
        entity = await use_cases.restock_item(item_id, payload.amount)
    except InventoryItemNotFoundError:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Inventory item with id={item_id} not found.",
        ) from None
    return _to_response(entity)


@router.post(
    "/{item_id}/consume",
    response_model=InventoryItemResponse,
    responses={
        404: {"description": "Item not found."},
        409: {"description": "Not enough stock to consume."},
    },
    summary="Consume stock from an inventory item",
)
async def consume_inventory_item(
    item_id: UUID,
    payload: ConsumeRequest,
    use_cases: InventoryItemUseCases = Depends(get_inventory_item_use_cases),
) -> InventoryItemResponse:
    try:
        entity = await use_cases.consume_item(item_id, payload.amount)
    except InventoryItemNotFoundError:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Inventory item with id={item_id} not found.",
        ) from None
    except ConsumeExceedsStockError as exc:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Cannot consume {exc.requested} units of sku={exc.sku!r}: "
                f"only {exc.available} in stock."
            ),
        ) from None
    return _to_response(entity)


__all__ = ["router"]
