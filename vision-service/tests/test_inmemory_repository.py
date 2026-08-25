"""Tests for the in-memory job repository and target serialization."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from app.infrastructure.inmemory_repository import InMemoryJobRepository
from app.infrastructure.repository import _target_to_dict
from app.schemas.job_schema import JobReportMode

from .conftest import make_target


def insert(repo: InMemoryJobRepository, **overrides):
    job_id = overrides.pop("job_id", uuid4())
    kwargs = {
        "job_id": job_id,
        "source": "rtsp://cam/stream",
        "source_type": "rtsp",
        "model_path": "yolo11n.pt",
        "targets": [make_target("carton")],
        "status": "pending",
        "counts": {"carton": 0},
        "last_reported_counts": {"carton": 0},
        "resolved_item_ids": {"carton": None},
        "created_at": datetime.now(timezone.utc),
    }
    kwargs.update(overrides)
    repo.insert_job(**kwargs)
    return job_id


def test_target_to_dict_serializes_uuid_and_enum():
    item_id = uuid4()
    target = make_target("carton", item_id=item_id, report_mode=JobReportMode.consume)
    assert _target_to_dict(target) == {
        "name": "carton",
        "class_names": ["carton"],
        "target_item_id": str(item_id),
        "target_sku": None,
        "report_mode": "consume",
    }


def test_target_to_dict_handles_plain_string_report_mode():
    class PlainTarget:
        name = "pallet"
        class_names = ["pallet"]
        target_item_id = None
        target_sku = "PALLET-001"
        report_mode = "restock"

    assert _target_to_dict(PlainTarget())["report_mode"] == "restock"


def test_insert_and_get_job():
    repo = InMemoryJobRepository()
    job_id = insert(repo)
    row = repo.get_job(job_id)
    assert row.id == job_id
    assert row.status == "pending"
    assert row.frames_processed == 0
    assert row.targets[0]["name"] == "carton"
    assert (row.started_at, row.stopped_at, row.error) == (None, None, None)


def test_get_unknown_job_returns_none():
    assert InMemoryJobRepository().get_job(uuid4()) is None


def test_insert_job_copies_mutable_counters():
    repo = InMemoryJobRepository()
    counts = {"carton": 1}
    job_id = insert(repo, counts=counts)
    counts["carton"] = 99
    assert repo.get_job(job_id).counts == {"carton": 1}


def test_list_jobs():
    repo = InMemoryJobRepository()
    ids = {insert(repo), insert(repo)}
    assert {row.id for row in repo.list_jobs()} == ids


def test_update_job_status_applies_only_given_fields():
    repo = InMemoryJobRepository()
    job_id = insert(repo)
    started = datetime.now(timezone.utc)
    repo.update_job_status(job_id, status="running", started_at=started)
    row = repo.get_job(job_id)
    assert (row.status, row.started_at, row.error) == ("running", started, None)

    stopped = datetime.now(timezone.utc)
    repo.update_job_status(job_id, status="error", error="boom", stopped_at=stopped)
    row = repo.get_job(job_id)
    assert (row.status, row.error, row.stopped_at) == ("error", "boom", stopped)
    assert row.started_at == started


def test_update_job_status_for_unknown_job_is_a_noop():
    InMemoryJobRepository().update_job_status(uuid4(), status="running")


def test_update_job_progress():
    repo = InMemoryJobRepository()
    job_id = insert(repo)
    reported_at = datetime.now(timezone.utc)
    repo.update_job_progress(
        job_id,
        counts={"carton": 4},
        last_reported_counts={"carton": 3},
        resolved_item_ids={"carton": "abc"},
        frames_processed=12,
        last_report_at=reported_at,
    )
    row = repo.get_job(job_id)
    assert row.counts == {"carton": 4}
    assert row.last_reported_counts == {"carton": 3}
    assert row.resolved_item_ids == {"carton": "abc"}
    assert row.frames_processed == 12
    assert row.last_report_at == reported_at


def test_update_job_progress_for_unknown_job_is_a_noop():
    InMemoryJobRepository().update_job_progress(
        uuid4(),
        counts={},
        last_reported_counts={},
        resolved_item_ids={},
        frames_processed=1,
    )


def test_events_are_scoped_per_job():
    repo = InMemoryJobRepository()
    job_a, job_b = insert(repo), insert(repo)
    item_id = uuid4()
    repo.insert_event(
        job_id=job_a,
        target_name="carton",
        delta=2,
        item_id=item_id,
        report_mode="restock",
        status="success",
        error=None,
    )
    repo.insert_event(
        job_id=job_b,
        target_name="pallet",
        delta=1,
        item_id=item_id,
        report_mode="consume",
        status="failed",
        error="upstream 500",
    )

    events_a = repo.list_events(job_a)
    assert [(e.target_name, e.delta, e.status) for e in events_a] == [("carton", 2, "success")]
    assert events_a[0].error is None
    assert events_a[0].created_at is not None

    events_b = repo.list_events(job_b)
    assert events_b[0].error == "upstream 500"
    assert repo.list_events(uuid4()) == []
