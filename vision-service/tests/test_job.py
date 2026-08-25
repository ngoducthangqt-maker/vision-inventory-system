"""Tests for the ``DetectionJob`` runtime state object."""

from __future__ import annotations

import pytest
from app.schemas.job_schema import JobStatus
from app.services.job import DetectionJob

from .conftest import make_job, make_target


def test_initial_state():
    job = make_job(targets=[make_target("carton"), make_target("pallet")])
    assert job.status is JobStatus.pending
    assert job.counts == {"carton": 0, "pallet": 0}
    assert job.last_reported_counts == {"carton": 0, "pallet": 0}
    assert job.resolved_item_ids == {"carton": None, "pallet": None}
    assert job.frames_processed == 0
    assert (job.started_at, job.last_report_at, job.stopped_at, job.error) == (
        None,
        None,
        None,
        None,
    )


def test_requires_at_least_one_target():
    with pytest.raises(ValueError, match="at least one counting target"):
        DetectionJob(
            source="rtsp://x",
            source_type="rtsp",
            targets=[],
            model_path="m.pt",
            frame_sample_interval=1,
            report_interval_seconds=1.0,
        )


def test_targets_are_copied_from_the_caller_list():
    targets = [make_target("carton")]
    job = make_job(targets=targets)
    targets.append(make_target("pallet"))
    assert [t.name for t in job.targets] == ["carton"]


def test_totals_sum_per_target_counters():
    job = make_job(targets=[make_target("carton"), make_target("pallet")])
    job.counts["carton"] = 5
    job.counts["pallet"] = 2
    job.last_reported_counts["carton"] = 3
    assert job.total_count == 7
    assert job.total_last_reported == 3


def test_stop_signalling():
    job = make_job()
    assert job.stop_requested is False
    job.request_stop()
    assert job.stop_requested is True


def test_target_named():
    carton = make_target("carton")
    job = make_job(targets=[carton, make_target("pallet")])
    assert job.target_named("carton").name == "carton"
    assert job.target_named("missing") is None


def test_ids_are_unique_per_job():
    assert make_job().id != make_job().id
