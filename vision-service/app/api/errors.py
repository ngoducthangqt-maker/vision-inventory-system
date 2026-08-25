"""Reusable HTTP error translations for the vision API routes."""

from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, status


def job_not_found(job_id: UUID) -> HTTPException:
    """404 for an unknown detection job id."""
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Job {job_id} not found.",
    )


def item_not_found(detail: str) -> HTTPException:
    """404 for a target inventory item / SKU that does not exist upstream."""
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


def inventory_unreachable(exc: Exception) -> HTTPException:
    """502 when inventory-service cannot be reached."""
    return HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail=f"inventory-service unreachable: {exc}",
    )


__all__ = ["job_not_found", "item_not_found", "inventory_unreachable"]
