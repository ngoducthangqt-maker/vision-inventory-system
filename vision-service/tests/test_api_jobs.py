"""HTTP-level tests for the ``jobs`` router.

The ``JobManager`` dependency is overridden with a manager wired to fakes, so
no worker thread, YOLO model or database is involved.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from app.clients.inventory_client import InventoryClientError, ItemNotFoundError
from app.infrastructure.inmemory_repository import InMemoryJobRepository
from app.main import create_app
from app.schemas.job_schema import JobStatus
from app.services import job_manager as job_manager_module
from app.services.job_manager import JobManager, get_job_manager
from fastapi.testclient import TestClient

from .conftest import FakeInventoryClient

PREFIX = "/api/v1/jobs"


@pytest.fixture(autouse=True)
def no_pipeline(monkeypatch) -> None:
    """Replace the pipeline so auto-started jobs do nothing."""

    class DummyPipeline:
        def __init__(self, *, job, inventory_client, settings, repository):
            pass

        def run(self) -> None:
            pass

    monkeypatch.setattr(job_manager_module, "DetectionPipeline", DummyPipeline)


@pytest.fixture
def fake_client() -> FakeInventoryClient:
    return FakeInventoryClient(sku_map={"CARTON-001": uuid4()})


@pytest.fixture
def manager(settings, fake_client) -> JobManager:
    return JobManager(settings, fake_client, InMemoryJobRepository())


@pytest.fixture
def client(manager) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_job_manager] = lambda: manager
    return TestClient(app)


def payload(**overrides):
    data = {
        "source": "demo://cartons",
        "targets": [{"name": "carton", "class_names": ["carton"], "target_sku": "CARTON-001"}],
        "auto_start": False,
    }
    data.update(overrides)
    return data


def test_health_and_root(client):
    assert client.get("/health").json()["status"] == "ok"
    assert client.get("/").json()["docs"] == "/docs"


def test_create_job_returns_201_with_target_state(client):
    body = client.post(PREFIX, json=payload()).json()
    assert body["status"] == JobStatus.pending.value
    assert body["source_type"] == "auto"
    assert body["total_count"] == 0
    target = body["targets"][0]
    assert (target["name"], target["target_sku"], target["current_count"]) == (
        "carton",
        "CARTON-001",
        0,
    )


def test_create_job_prechecks_item_ids_when_auto_starting(client, fake_client):
    item_id = uuid4()
    targets = [{"name": "carton", "class_names": ["carton"], "target_item_id": str(item_id)}]
    response = client.post(PREFIX, json=payload(targets=targets, auto_start=True))
    assert response.status_code == 201
    assert fake_client.ensured == [item_id]


def test_create_job_returns_404_when_item_is_missing(client, fake_client):
    fake_client.raise_on_ensure = ItemNotFoundError("item gone")
    targets = [{"name": "carton", "class_names": ["carton"], "target_item_id": str(uuid4())}]
    response = client.post(PREFIX, json=payload(targets=targets, auto_start=True))
    assert response.status_code == 404
    assert response.json()["detail"] == "item gone"


def test_create_job_returns_502_when_inventory_is_unreachable(client, fake_client):
    fake_client.raise_on_ensure = InventoryClientError("connection refused")
    targets = [{"name": "carton", "class_names": ["carton"], "target_item_id": str(uuid4())}]
    response = client.post(PREFIX, json=payload(targets=targets, auto_start=True))
    assert response.status_code == 502
    assert "unreachable" in response.json()["detail"]


def test_create_job_returns_500_when_dependencies_are_missing(client, manager, monkeypatch):
    monkeypatch.setattr(
        manager,
        "create_job",
        lambda request: (_ for _ in ()).throw(RuntimeError("ultralytics not installed")),
    )
    response = client.post(PREFIX, json=payload())
    assert response.status_code == 500
    assert response.json()["detail"] == "ultralytics not installed"


def test_create_job_rejects_invalid_payload(client):
    targets = [{"name": "carton", "class_names": ["carton"]}]  # no destination
    assert client.post(PREFIX, json=payload(targets=targets)).status_code == 422


def test_list_jobs(client):
    created = [client.post(PREFIX, json=payload()).json()["id"] for _ in range(2)]
    body = client.get(PREFIX).json()
    assert body["total"] == 2
    assert {job["id"] for job in body["jobs"]} == set(created)


def test_list_jobs_filters_by_status(client, manager):
    running_id = client.post(PREFIX, json=payload()).json()["id"]
    client.post(PREFIX, json=payload())
    manager.get_job(UUID(running_id)).status = JobStatus.running

    body = client.get(PREFIX, params={"status": "running"}).json()
    assert [job["id"] for job in body["jobs"]] == [running_id]
    assert client.get(PREFIX, params={"status": "error"}).json()["total"] == 0


def test_list_jobs_rejects_unknown_status(client):
    assert client.get(PREFIX, params={"status": "paused"}).status_code == 422


def test_get_job(client):
    job_id = client.post(PREFIX, json=payload()).json()["id"]
    assert client.get(f"{PREFIX}/{job_id}").json()["id"] == job_id


def test_get_unknown_job_returns_404(client):
    assert client.get(f"{PREFIX}/{uuid4()}").status_code == 404


def test_list_events(client, manager):
    job_id = client.post(PREFIX, json=payload()).json()["id"]
    item_id = uuid4()
    manager._repo.insert_event(  # noqa: SLF001
        job_id=UUID(job_id),
        target_name="carton",
        delta=3,
        item_id=item_id,
        report_mode="restock",
        status="failed",
        error="upstream 500",
    )
    body = client.get(f"{PREFIX}/{job_id}/events").json()
    assert body["total"] == 1
    event = body["events"][0]
    assert (event["delta"], event["status"], event["report_mode"]) == (3, "failed", "restock")
    assert event["item_id"] == str(item_id)


def test_list_events_for_unknown_job_returns_404(client):
    assert client.get(f"{PREFIX}/{uuid4()}/events").status_code == 404


def test_stop_job(client, manager):
    job_id = client.post(PREFIX, json=payload()).json()["id"]
    body = client.post(f"{PREFIX}/{job_id}/stop").json()
    assert body["id"] == job_id
    assert body["total_count"] == 0
    assert manager.get_job(UUID(job_id)).stop_requested is True


def test_stop_unknown_job_returns_404(client):
    assert client.post(f"{PREFIX}/{uuid4()}/stop").status_code == 404


def test_delete_job_returns_204(client):
    job_id = client.post(PREFIX, json=payload()).json()["id"]
    assert client.delete(f"{PREFIX}/{job_id}").status_code == 204
    assert client.get(f"{PREFIX}/{job_id}").status_code == 404


def test_delete_unknown_job_returns_404(client):
    assert client.delete(f"{PREFIX}/{uuid4()}").status_code == 404
