"""Tests for the inventory-service REST client.

``httpx.MockTransport`` is injected by patching the client factory, so the real
request/response handling of httpx is exercised without any network access.
"""

from __future__ import annotations

import json
from uuid import uuid4

import httpx
import pytest
from app.clients.inventory_client import (
    InventoryClient,
    InventoryClientError,
    ItemNotFoundError,
)


def build_client(handler, **kwargs) -> InventoryClient:
    """Return a client whose HTTP calls are served by ``handler``."""
    client = InventoryClient("http://inventory:8000/", **kwargs)
    transport = httpx.MockTransport(handler)
    client._client = lambda: httpx.Client(transport=transport)  # noqa: SLF001
    return client


def test_url_building_strips_trailing_slashes():
    client = InventoryClient("http://inventory:8000/", api_prefix="/api/v1/")
    assert client._url("/inventory-items") == "http://inventory:8000/api/v1/inventory-items"


def test_resolve_item_id_by_sku_matches_listing():
    wanted = uuid4()
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={"items": [{"id": str(uuid4()), "sku": "OTHER"}, {"id": str(wanted), "sku": "S-1"}]},
        )

    assert build_client(handler).resolve_item_id_by_sku("S-1") == wanted
    assert requests[0].url.params["limit"] == "200"


def test_resolve_item_id_by_sku_raises_when_absent():
    handler = lambda request: httpx.Response(200, json={"items": []})  # noqa: E731
    with pytest.raises(ItemNotFoundError, match="sku='S-1'"):
        build_client(handler).resolve_item_id_by_sku("S-1")


def test_resolve_item_id_by_sku_wraps_http_errors():
    handler = lambda request: httpx.Response(500, text="boom")  # noqa: E731
    with pytest.raises(InventoryClientError) as excinfo:
        build_client(handler).resolve_item_id_by_sku("S-1")
    assert excinfo.value.status_code == 500


def test_ensure_item_exists_accepts_200():
    handler = lambda request: httpx.Response(200, json={"id": str(uuid4())})  # noqa: E731
    build_client(handler).ensure_item_exists(uuid4())  # must not raise


def test_ensure_item_exists_raises_on_404():
    handler = lambda request: httpx.Response(404, json={"detail": "nope"})  # noqa: E731
    with pytest.raises(ItemNotFoundError):
        build_client(handler).ensure_item_exists(uuid4())


def test_ensure_item_exists_wraps_other_errors():
    handler = lambda request: httpx.Response(503, text="unavailable")  # noqa: E731
    with pytest.raises(InventoryClientError) as excinfo:
        build_client(handler).ensure_item_exists(uuid4())
    assert excinfo.value.status_code == 503


@pytest.mark.parametrize("action", ["restock", "consume"])
def test_restock_and_consume_post_the_amount(action):
    item_id = uuid4()
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"quantity": 11})

    client = build_client(handler)
    assert getattr(client, action)(item_id, 3) == {"quantity": 11}
    assert seen["url"] == f"http://inventory:8000/api/v1/inventory-items/{item_id}/{action}"
    assert seen["body"] == {"amount": 3}


@pytest.mark.parametrize("amount", [0, -2])
def test_report_rejects_non_positive_amounts(amount):
    handler = lambda request: httpx.Response(200, json={})  # noqa: E731
    with pytest.raises(ValueError, match="positive integer"):
        build_client(handler).restock(uuid4(), amount)


def test_report_raises_item_not_found_on_404():
    handler = lambda request: httpx.Response(404, json={"detail": "gone"})  # noqa: E731
    with pytest.raises(ItemNotFoundError, match="during consume"):
        build_client(handler).consume(uuid4(), 1)


def test_report_wraps_server_errors():
    handler = lambda request: httpx.Response(500, text="kaboom")  # noqa: E731
    with pytest.raises(InventoryClientError) as excinfo:
        build_client(handler).restock(uuid4(), 1)
    assert excinfo.value.status_code == 500


def test_report_tolerates_empty_body():
    item_id = uuid4()
    handler = lambda request: httpx.Response(204)  # noqa: E731
    assert build_client(handler).restock(item_id, 4) == {
        "item_id": str(item_id),
        "action": "restock",
        "amount": 4,
    }


def test_default_timeout_is_applied_to_created_clients():
    client = InventoryClient("http://inventory:8000", timeout_seconds=2.5)
    with client._client() as http_client:  # noqa: SLF001
        assert http_client.timeout.read == 2.5
