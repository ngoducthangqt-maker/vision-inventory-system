"""Synchronous REST client for the ``inventory-service``.

A *synchronous* client (``httpx.Client``) is used intentionally: detection
runs in a dedicated worker thread where blocking I/O is fine and avoids the
complexity of bridging an async event loop. Each public method creates a
short-lived client, which keeps the code thread-safe across multiple jobs.

Endpoints used (inventory-service v1):
    GET    /api/v1/inventory-items          -> resolve SKU -> item id
    POST   /api/v1/inventory-items/{id}/restock  {"amount": N}
    POST   /api/v1/inventory-items/{id}/consume  {"amount": N}
    GET    /api/v1/inventory-items/{id}      -> existence check
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import httpx


class InventoryClientError(Exception):
    """Base error for inventory-service communication failures."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        self.status_code = status_code
        super().__init__(message)


class ItemNotFoundError(InventoryClientError):
    """Raised when the referenced inventory item does not exist."""


class InventoryClient:
    """Minimal REST client for inventory-service."""

    def __init__(
        self,
        base_url: str,
        *,
        api_prefix: str = "/api/v1",
        timeout_seconds: float = 10.0,
        api_key: str = "",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_prefix = api_prefix.rstrip("/")
        self.timeout = timeout_seconds
        self.api_key = api_key

    # ------------------------------------------------------------------ #
    # URL helpers                                                         #
    # ------------------------------------------------------------------ #
    def _url(self, path: str) -> str:
        return f"{self.base_url}{self.api_prefix}{path}"

    def _client(self) -> httpx.Client:
        headers = {"X-API-Key": self.api_key} if self.api_key else None
        return httpx.Client(timeout=self.timeout, headers=headers)

    # ------------------------------------------------------------------ #
    # Public API                                                          #
    # ------------------------------------------------------------------ #
    def resolve_item_id_by_sku(self, sku: str) -> UUID:
        """Resolve a SKU to its inventory item UUID by listing items.

        The inventory-service has no ``GET by SKU`` endpoint, so we fetch the
        list (with a generous limit) and match on ``sku``.
        """
        with self._client() as client:
            response = client.get(self._url("/inventory-items"), params={"limit": 200})
        if response.status_code >= 400:
            raise InventoryClientError(
                f"Failed to list inventory items: {response.status_code} {response.text}",
                status_code=response.status_code,
            )
        payload = response.json()
        items: list[dict[str, Any]] = payload.get("items", [])
        for item in items:
            if item.get("sku") == sku:
                return UUID(str(item["id"]))
        raise ItemNotFoundError(f"No inventory item with sku={sku!r}.")

    def ensure_item_exists(self, item_id: UUID) -> None:
        """Verify that ``item_id`` exists in inventory-service."""
        with self._client() as client:
            response = client.get(self._url(f"/inventory-items/{item_id}"))
        if response.status_code == 404:
            raise ItemNotFoundError(f"Inventory item with id={item_id} not found.")
        if response.status_code >= 400:
            raise InventoryClientError(
                f"Failed to fetch inventory item {item_id}: "
                f"{response.status_code} {response.text}",
                status_code=response.status_code,
            )

    def restock(self, item_id: UUID, amount: int) -> dict[str, Any]:
        """POST a restock of ``amount`` units to inventory-service."""
        return self._post_amount(item_id, "restock", amount)

    def consume(self, item_id: UUID, amount: int) -> dict[str, Any]:
        """POST a consume of ``amount`` units to inventory-service."""
        return self._post_amount(item_id, "consume", amount)

    # ------------------------------------------------------------------ #
    # Internals                                                           #
    # ------------------------------------------------------------------ #
    def _post_amount(self, item_id: UUID, action: str, amount: int) -> dict[str, Any]:
        if amount <= 0:
            raise ValueError("amount must be a positive integer.")
        with self._client() as client:
            response = client.post(
                self._url(f"/inventory-items/{item_id}/{action}"),
                json={"amount": amount},
            )
        if response.status_code == 404:
            raise ItemNotFoundError(
                f"Inventory item with id={item_id} not found during {action}."
            )
        if response.status_code >= 400:
            raise InventoryClientError(
                f"inventory-service {action} failed for item {item_id}: "
                f"{response.status_code} {response.text}",
                status_code=response.status_code,
            )
        try:
            return response.json()
        except ValueError:
            # 204 No Content or empty body
            return {"item_id": str(item_id), "action": action, "amount": amount}


__all__ = ["InventoryClient", "InventoryClientError", "ItemNotFoundError"]
