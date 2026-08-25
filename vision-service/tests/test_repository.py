"""Tests for the sync ``JobRepository`` against in-memory SQLite.

``JSONB`` is Postgres-only, so a SQLite DDL compilation rule is registered to
let the ORM metadata be created in-memory.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from app.core.database import Base
from app.infrastructure.repository import JobRepository, _target_to_dict
from app.schemas.job_schema import JobReportMode
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker

from .conftest import make_target


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(type_, compiler, **kw) -> str:  # noqa: ANN001
    return "JSON"


@pytest.fixture
def repository() -> JobRepository:
    engine = create_engine("sqlite://", future=True)
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, class_=Session, expire_on_commit=False, autoflush=False)
    return JobRepository(factory)


def insert_job(repository: JobRepository, **overrides):
    job_id = overrides.pop("job_id", uuid4())
    kwargs = {
        "source": "rtsp://camera/stream",
        "source_type": "rtsp",
        "model_path": "yolo11n.pt",
        "targets": [make_target("carton", sku="CARTON-001")],
        "status": "pending",
        "counts": {"carton": 0},
        "last_reported_counts": {"carton": 0},
        "resolved_item_ids": {"carton": None},
        "created_at": datetime.now(timezone.utc),
    }
    kwargs.update(overrides)
    repository.insert_job(job_id=job_id, **kwargs)
    return job_id


def test_target_to_dict_serializes_uuid_and_enum():
    item_id = uuid4()
    target = make_target("pallet", item_id=item_id, report_mode=JobReportMode.consume)
    assert _target_to_dict(target) == {
        "name": "pallet",
        "class_names": ["pallet"],
        "target_item_id": str(item_id),
        "target_sku": None,
        "report_mode": "consume",
    }


def test_target_to_dict_accepts_plain_string_report_mode():
    class PlainTarget:
        name = "carton"
        class_names = ["carton"]
        target_item_id = None
        target_sku = "SKU-1"
        report_mode = "restock"

    assert _target_to_dict(PlainTarget())["report_mode"] == "restock"


def test_insert_and_get_job(repository):
    job_id = insert_job(repository)
    row = repository.get_job(job_id)
    assert row is not None
    assert row.source == "rtsp://camera/stream"
    assert row.frames_processed == 0
    assert row.targets[0]["target_sku"] == "CARTON-001"


def test_get_unknown_job_returns_none(repository):
    assert repository.get_job(uuid4()) is None


def test_list_jobs_is_newest_first(repository):
    now = datetime.now(timezone.utc)
    older = insert_job(repository, created_at=now - timedelta(minutes=5))
    newer = insert_job(repository, created_at=now)
    assert [row.id for row in repository.list_jobs()] == [newer, older]


def test_update_job_status_sets_only_provided_fields(repository):
    job_id = insert_job(repository)
    started = datetime.now(timezone.utc)
    repository.update_job_status(job_id, status="running", started_at=started)
    row = repository.get_job(job_id)
    assert row.status == "running"
    assert row.error is None
    assert row.stopped_at is None

    stopped = started + timedelta(seconds=2)
    repository.update_job_status(job_id, status="error", error="boom", stopped_at=stopped)
    row = repository.get_job(job_id)
    assert (row.status, row.error) == ("error", "boom")
    assert row.stopped_at is not None


def test_update_job_status_for_unknown_job_is_a_noop(repository):
    repository.update_job_status(uuid4(), status="running")
    assert repository.list_jobs() == []


def test_update_job_progress(repository):
    job_id = insert_job(repository)
    item_id = uuid4()
    reported_at = datetime.now(timezone.utc)
    repository.update_job_progress(
        job_id,
        counts={"carton": 7},
        last_reported_counts={"carton": 4},
        resolved_item_ids={"carton": str(item_id)},
        frames_processed=42,
        last_report_at=reported_at,
    )
    row = repository.get_job(job_id)
    assert row.counts == {"carton": 7}
    assert row.last_reported_counts == {"carton": 4}
    assert row.resolved_item_ids == {"carton": str(item_id)}
    assert row.frames_processed == 42
    assert row.last_report_at is not None


def test_update_job_progress_without_report_time_keeps_it_null(repository):
    job_id = insert_job(repository)
    repository.update_job_progress(
        job_id,
        counts={},
        last_reported_counts={},
        resolved_item_ids={},
        frames_processed=1,
    )
    assert repository.get_job(job_id).last_report_at is None


def test_insert_and_list_events_scoped_to_job(repository):
    job_id = insert_job(repository)
    other_job_id = insert_job(repository)
    item_id = uuid4()
    repository.insert_event(
        job_id=job_id,
        target_name="carton",
        delta=3,
        item_id=item_id,
        report_mode="restock",
        status="success",
        error=None,
    )
    repository.insert_event(
        job_id=other_job_id,
        target_name="pallet",
        delta=1,
        item_id=item_id,
        report_mode="consume",
        status="failed",
        error="upstream 500",
    )

    events = repository.list_events(job_id)
    assert len(events) == 1
    assert (events[0].target_name, events[0].delta, events[0].status) == ("carton", 3, "success")
    assert events[0].error is None
    assert events[0].item_id == item_id

    other = repository.list_events(other_job_id)
    assert (other[0].report_mode, other[0].error) == ("consume", "upstream 500")


def test_list_events_for_unknown_job_is_empty(repository):
    assert repository.list_events(uuid4()) == []


def test_default_session_factory_is_resolved_from_database_module(monkeypatch):
    sentinel = object()
    monkeypatch.setattr("app.core.database.get_session_factory", lambda: sentinel)
    assert JobRepository()._session_factory is sentinel  # noqa: SLF001
