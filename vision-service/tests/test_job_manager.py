"""Tests for ``JobManager`` (registry + worker-thread lifecycle)."""

from __future__ import annotations

import threading
from uuid import uuid4

import pytest
from app.infrastructure.inmemory_repository import InMemoryJobRepository
from app.schemas.job_schema import JobCreateRequest, JobSourceType, JobStatus
from app.services import job_manager as job_manager_module
from app.services.job_manager import JobManager, JobNotFoundError, get_job_manager

from .conftest import FakeInventoryClient


@pytest.fixture
def started(monkeypatch) -> list:
    """Replace pipeline execution with a recording no-op."""
    launched: list = []

    class DummyPipeline:
        def __init__(self, *, job, inventory_client, settings, repository):
            self.job = job

        def run(self) -> None:
            launched.append(self.job)

    monkeypatch.setattr(job_manager_module, "DetectionPipeline", DummyPipeline)
    return launched


@pytest.fixture
def manager(settings) -> JobManager:
    return JobManager(settings, FakeInventoryClient(), InMemoryJobRepository())


def make_request(**overrides) -> JobCreateRequest:
    payload = {
        "source": "demo://cartons",
        "targets": [{"name": "carton", "class_names": ["carton"], "target_sku": "CARTON-001"}],
    }
    payload.update(overrides)
    return JobCreateRequest(**payload)


def test_create_job_applies_settings_defaults(manager, settings, started):
    job = manager.create_job(make_request(auto_start=False))
    assert job.model_path == settings.default_model_path
    assert job.frame_sample_interval == settings.default_frame_sample_interval
    assert job.report_interval_seconds == settings.default_report_interval_seconds
    assert job.status is JobStatus.pending
    assert started == []


def test_create_job_honours_request_overrides(manager, started):
    job = manager.create_job(
        make_request(
            auto_start=False,
            model_path="custom.pt",
            frame_sample_interval=3,
            report_interval_seconds=30.0,
            source_type="file",
        )
    )
    assert job.model_path == "custom.pt"
    assert job.frame_sample_interval == 3
    assert job.report_interval_seconds == 30.0
    assert job.source_type is JobSourceType.file


def test_create_job_persists_initial_row(manager, started):
    job = manager.create_job(make_request(auto_start=False))
    row = manager._repo.get_job(job.id)  # noqa: SLF001
    assert row.status == "pending"
    assert row.targets[0]["target_sku"] == "CARTON-001"


def test_create_job_survives_persistence_failure(settings, started, monkeypatch):
    repository = InMemoryJobRepository()
    monkeypatch.setattr(
        repository, "insert_job", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("db down"))
    )
    manager = JobManager(settings, FakeInventoryClient(), repository)
    assert manager.create_job(make_request(auto_start=False)) is not None


def test_create_job_without_repository(settings, started):
    manager = JobManager(settings, FakeInventoryClient(), None)
    job = manager.create_job(make_request(auto_start=False))
    assert manager.get_job(job.id) is job
    assert manager.list_events(job.id) == []


def test_auto_start_launches_a_worker_thread(manager, started):
    job = manager.create_job(make_request(auto_start=True))
    thread = manager._threads[job.id]  # noqa: SLF001
    thread.join(timeout=5.0)
    assert started == [job]
    assert thread.name == f"vision-job-{job.id}"
    assert thread.daemon is True


def test_get_job_raises_for_unknown_id(manager):
    with pytest.raises(JobNotFoundError) as excinfo:
        manager.get_job(uuid4())
    assert excinfo.value.job_id is not None


def test_list_jobs(manager, started):
    jobs = {manager.create_job(make_request(auto_start=False)).id for _ in range(2)}
    assert {j.id for j in manager.list_jobs()} == jobs


def test_stop_job_signals_the_job(manager, started):
    job = manager.create_job(make_request(auto_start=False))
    assert manager.stop_job(job.id).stop_requested is True


def test_stop_unknown_job_raises(manager):
    with pytest.raises(JobNotFoundError):
        manager.stop_job(uuid4())


def test_delete_job_removes_it_from_the_registry(manager, started):
    job = manager.create_job(make_request(auto_start=False))
    manager.delete_job(job.id)
    with pytest.raises(JobNotFoundError):
        manager.get_job(job.id)


def test_delete_job_joins_a_running_thread(manager, settings, monkeypatch):
    release = threading.Event()

    class BlockingPipeline:
        def __init__(self, *, job, inventory_client, settings, repository):
            self.job = job

        def run(self) -> None:
            release.wait(timeout=5.0)

    monkeypatch.setattr(job_manager_module, "DetectionPipeline", BlockingPipeline)
    job = manager.create_job(make_request(auto_start=True))
    release.set()
    manager.delete_job(job.id)
    assert manager._threads == {}  # noqa: SLF001


def test_delete_unknown_job_raises(manager):
    with pytest.raises(JobNotFoundError):
        manager.delete_job(uuid4())


def test_list_events_returns_persisted_rows(manager, started):
    job = manager.create_job(make_request(auto_start=False))
    manager._repo.insert_event(  # noqa: SLF001
        job_id=job.id,
        target_name="carton",
        delta=2,
        item_id=uuid4(),
        report_mode="restock",
        status="success",
        error=None,
    )
    assert [e.delta for e in manager.list_events(job.id)] == [2]


def test_list_events_for_forgotten_job_still_reads_history(manager, started):
    job_id = uuid4()
    manager._repo.insert_event(  # noqa: SLF001
        job_id=job_id,
        target_name="carton",
        delta=1,
        item_id=uuid4(),
        report_mode="restock",
        status="success",
        error=None,
    )
    assert len(manager.list_events(job_id)) == 1


def test_shutdown_stops_all_jobs(manager, started):
    jobs = [manager.create_job(make_request(auto_start=True)) for _ in range(2)]
    manager.shutdown()
    assert all(job.stop_requested for job in jobs)


# --------------------------------------------------------------------------- #
# Singleton accessor                                                           #
# --------------------------------------------------------------------------- #
@pytest.fixture
def reset_singleton():
    job_manager_module._job_manager = None  # noqa: SLF001
    yield
    job_manager_module._job_manager = None  # noqa: SLF001


def test_get_job_manager_uses_inmemory_repo_when_configured(monkeypatch, reset_singleton, settings):
    monkeypatch.setattr(settings, "repository_mode", "inmemory")
    monkeypatch.setattr(settings, "environment", "development")
    monkeypatch.setattr(job_manager_module, "get_settings", lambda: settings)

    manager = get_job_manager()
    assert isinstance(manager._repo, InMemoryJobRepository)  # noqa: SLF001
    assert get_job_manager() is manager


def test_get_job_manager_degrades_when_postgres_repo_fails(
    monkeypatch, reset_singleton, settings
):
    monkeypatch.setattr(settings, "repository_mode", "postgres")
    monkeypatch.setattr(job_manager_module, "get_settings", lambda: settings)
    monkeypatch.setattr(
        job_manager_module,
        "JobRepository",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("no postgres")),
    )
    assert get_job_manager()._repo is None  # noqa: SLF001
