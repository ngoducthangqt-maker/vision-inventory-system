"""HTTP-level tests for the ``inventory-items`` router.

The repository dependency is overridden with the in-memory fake, so no
database is involved and the tests exercise routing, serialization and the
domain-exception -> status-code mapping.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from app.dependencies import get_inventory_item_repository
from app.main import create_app
from fastapi.testclient import TestClient

from .conftest import FakeInventoryItemRepository, make_item

PREFIX = "/api/v1/inventory-items"


@pytest.fixture
def repository() -> FakeInventoryItemRepository:
    return FakeInventoryItemRepository()


@pytest.fixture
def client(repository) -> TestClient:
    app = create_app()

    async def _override() -> FakeInventoryItemRepository:
        return repository

    app.dependency_overrides[get_inventory_item_repository] = _override
    # ``raise_server_exceptions`` stays on: lifespan is skipped by not using
    # the context-manager form, so no database connection is attempted.
    return TestClient(app)


def test_health_and_root(client):
    assert client.get("/health").json()["status"] == "ok"
    assert client.get("/").json()["docs"] == "/docs"


def test_create_returns_201_with_enriched_flags(client):
    response = client.post(
        PREFIX,
        json={"sku": "A-1", "name": "A", "quantity": 3, "price": "5.00", "low_stock_threshold": 5},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["sku"] == "A-1"
    assert body["is_low_stock"] is True
    assert body["is_in_stock"] is True


def test_create_duplicate_sku_returns_409(client, repository):
    existing = make_item(sku="DUP")
    repository.items[existing.id] = existing
    response = client.post(PREFIX, json={"sku": "DUP", "name": "A", "quantity": 1, "price": "1"})
    assert response.status_code == 409


def test_create_invalid_payload_returns_422(client):
    assert client.post(PREFIX, json={"name": "no sku"}).status_code == 422


def test_list_returns_pagination_metadata(client, repository):
    for i in range(3):
        item = make_item(sku=f"S-{i}")
        repository.items[item.id] = item
    body = client.get(PREFIX, params={"skip": 0, "limit": 2}).json()
    assert body["total"] == 3
    assert len(body["items"]) == 2
    assert (body["skip"], body["limit"]) == (0, 2)


def test_list_rejects_out_of_range_limit(client):
    assert client.get(PREFIX, params={"limit": 500}).status_code == 422


def test_list_filters_by_category_and_low_stock(client, repository):
    low = make_item(sku="LOW", quantity=1, category="a")
    high = make_item(sku="HIGH", quantity=99, category="b")
    for item in (low, high):
        repository.items[item.id] = item

    by_category = client.get(PREFIX, params={"category": "b"}).json()["items"]
    assert [i["sku"] for i in by_category] == ["HIGH"]

    low_only = client.get(PREFIX, params={"low_stock_only": True}).json()["items"]
    assert [i["sku"] for i in low_only] == ["LOW"]


def test_get_single_item(client, repository):
    item = make_item()
    repository.items[item.id] = item
    body = client.get(f"{PREFIX}/{item.id}").json()
    assert body["id"] == str(item.id)


def test_get_unknown_item_returns_404(client):
    assert client.get(f"{PREFIX}/{uuid4()}").status_code == 404


def test_get_malformed_uuid_returns_422(client):
    assert client.get(f"{PREFIX}/not-a-uuid").status_code == 422


def test_patch_updates_fields(client, repository):
    item = make_item(name="Old")
    repository.items[item.id] = item
    body = client.patch(f"{PREFIX}/{item.id}", json={"name": "New", "category": "c2"}).json()
    assert (body["name"], body["category"]) == ("New", "c2")


def test_patch_unknown_item_returns_404(client):
    assert client.patch(f"{PREFIX}/{uuid4()}", json={"name": "N"}).status_code == 404


def test_delete_returns_204(client, repository):
    item = make_item()
    repository.items[item.id] = item
    assert client.delete(f"{PREFIX}/{item.id}").status_code == 204
    assert repository.items == {}


def test_delete_unknown_item_returns_404(client):
    assert client.delete(f"{PREFIX}/{uuid4()}").status_code == 404


def test_restock_increases_quantity(client, repository):
    item = make_item(quantity=1)
    repository.items[item.id] = item
    body = client.post(f"{PREFIX}/{item.id}/restock", json={"amount": 9}).json()
    assert body["quantity"] == 10


def test_restock_unknown_item_returns_404(client):
    assert client.post(f"{PREFIX}/{uuid4()}/restock", json={"amount": 1}).status_code == 404


def test_consume_decreases_quantity(client, repository):
    item = make_item(quantity=10)
    repository.items[item.id] = item
    body = client.post(f"{PREFIX}/{item.id}/consume", json={"amount": 10}).json()
    assert body["quantity"] == 0
    assert body["is_in_stock"] is False


def test_consume_beyond_stock_returns_409(client, repository):
    item = make_item(quantity=2)
    repository.items[item.id] = item
    response = client.post(f"{PREFIX}/{item.id}/consume", json={"amount": 3})
    assert response.status_code == 409
    assert "only 2 in stock" in response.json()["detail"]


def test_consume_unknown_item_returns_404(client):
    assert client.post(f"{PREFIX}/{uuid4()}/consume", json={"amount": 1}).status_code == 404


def test_consume_zero_amount_returns_422(client, repository):
    item = make_item()
    repository.items[item.id] = item
    assert client.post(f"{PREFIX}/{item.id}/consume", json={"amount": 0}).status_code == 422
