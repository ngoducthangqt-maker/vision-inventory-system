"""Seed the inventory-service with sample carton & pallet items.

Usage::

    # Against a locally running inventory-service (default)
    python scripts/seed_items.py

    # Against a custom URL
    INVENTORY_SERVICE_URL=http://inventory-service:8000 python scripts/seed_items.py

Seeded items (idempotent — re-running won't fail on duplicate SKUs because the
script checks existence first via GET /inventory-items):

    SKU          NAME              QUANTITY  PRICE   LOW_STOCK_THRESHOLD
    CARTON-001   Cardboard Carton     0      1.50    10
    PALLET-001   Wooden Pallet        0      45.00   2

These SKUs are the default targets used by vision-service demo jobs, so after
seeding you can immediately create a vision job pointing at CARTON-001 and
PALLET-001.
"""

from __future__ import annotations

import os
import sys

import httpx

DEFAULT_URL = os.environ.get("INVENTORY_SERVICE_URL", "http://localhost:8000")
API_PREFIX = "/api/v1"
API_KEY = os.environ.get("API_KEY", "")

SEED_ITEMS = [
    {
        "sku": "CARTON-001",
        "name": "Cardboard Carton",
        "description": "Standard corrugated cardboard carton.",
        "quantity": 0,
        "price": "1.50",
        "category": "packaging",
        "low_stock_threshold": 10,
    },
    {
        "sku": "PALLET-001",
        "name": "Wooden Pallet",
        "description": "Standard 120x80cm wooden pallet.",
        "quantity": 0,
        "price": "45.00",
        "category": "logistics",
        "low_stock_threshold": 2,
    },
]


def _list_skus(client: httpx.Client) -> set[str]:
    response = client.get(f"{API_PREFIX}/inventory-items", params={"limit": 200})
    response.raise_for_status()
    return {it.get("sku", "") for it in response.json().get("items", [])}


def _create_item(client: httpx.Client, item: dict) -> None:
    response = client.post(f"{API_PREFIX}/inventory-items", json=item)
    if response.status_code == 409:
        print(f"  [skip] {item['sku']} already exists.")
        return
    response.raise_for_status()
    created = response.json()
    print(f"  [ok]   created {created['sku']} (id={created['id']})")


def main() -> int:
    print(f"Seeding inventory-service at {DEFAULT_URL} ...")
    headers = {"X-API-Key": API_KEY} if API_KEY else None
    with httpx.Client(base_url=DEFAULT_URL, timeout=10.0, headers=headers) as client:
        # Health check first.
        try:
            health = client.get("/health")
            health.raise_for_status()
        except httpx.HTTPError as exc:
            print(f"ERROR: cannot reach inventory-service at {DEFAULT_URL}: {exc}", file=sys.stderr)
            return 1

        existing = _list_skus(client)
        for item in SEED_ITEMS:
            if item["sku"] in existing:
                print(f"  [skip] {item['sku']} already exists.")
                continue
            _create_item(client, item)

    print("\nDone. Seeded SKUs:")
    for item in SEED_ITEMS:
        print(f"  - {item['sku']:12s} ({item['name']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
