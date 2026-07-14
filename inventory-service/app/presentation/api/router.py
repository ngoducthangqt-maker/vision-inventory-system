"""Aggregates every v1 router into a single ``APIRouter``."""

from __future__ import annotations

from fastapi import APIRouter

from app.presentation.api.v1.inventory_items import router as inventory_items_router

api_v1_router = APIRouter()
api_v1_router.include_router(inventory_items_router)

__all__ = ["api_v1_router"]
