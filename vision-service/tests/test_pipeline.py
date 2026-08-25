"""Tests for the ``DetectionPipeline`` worker loop.

The detector and video source are replaced by fakes, so the counting,
delta-reporting and persistence logic runs without YOLO, OpenCV or Postgres.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from app.clients.inventory_client import InventoryClientError, ItemNotFoundError
from app.core.detector import Detection
from app.core.source import VideoSourceError
from app.infrastructure.inmemory_repository import InMemoryJobRepository
from app.schemas.job_schema import JobReportMode, JobStatus
from app.services import pipeline as pipeline_module
from app.services.pipeline import DetectionPipeline

from .conftest import (
    FakeDetector,
    FakeInventoryClient,
    FakeSource,
    make_job,
    make_target,
)


def build_pipeline(
    job,
    settings,
    *,
    client: FakeInventoryClient | None = None,
    frames: list[list[Detection]] | None = None,
    repository: InMemoryJobRepository | None = None,
    monkeypatch=None,
) -> tuple[DetectionPipeline, FakeInventoryClient, FakeSource]:
    client = client or FakeInventoryClient()
    frames = frames if frames is not None else []
    source = FakeSource(len(frames))
    pipeline = DetectionPipeline(job, client, settings, repository)
    pipeline._detector = FakeDetector(frames)  # noqa: SLF001
    pipeline._source = source  # noqa: SLF001
    if monkeypatch is not None:
        # Skip detector/source construction (which would import ultralytics/cv2)
        # while keeping the rest of ``run()`` intact.
        monkeypatch.setattr(
            DetectionPipeline,
            "_start",
            lambda self: setattr(self._job, "status", JobStatus.running),
        )
    return pipeline, client, source


# --------------------------------------------------------------------------- #
# Setup / target resolution                                                    #
# --------------------------------------------------------------------------- #
def test_build_class_map_lower_cases_and_trims(settings):
    job = make_job(
        targets=[
            make_target("carton", class_names=[" Carton ", "BOX", ""]),
            make_target("pallet", class_names=["Pallet"]),
        ]
    )
    pipeline, _, _ = build_pipeline(job, settings)
    pipeline._build_class_map()  # noqa: SLF001
    assert pipeline._class_to_target == {  # noqa: SLF001
        "carton": "carton",
        "box": "carton",
        "pallet": "pallet",
    }


def test_resolve_targets_uses_item_id_and_sku(settings):
    item_id, sku_id = uuid4(), uuid4()
    job = make_job(
        targets=[
            make_target("carton", item_id=item_id),
            make_target("pallet", sku="PALLET-001"),
        ]
    )
    client = FakeInventoryClient(sku_map={"PALLET-001": sku_id})
    pipeline, _, _ = build_pipeline(job, settings, client=client)
    pipeline._resolve_targets()  # noqa: SLF001
    assert job.resolved_item_ids == {"carton": item_id, "pallet": sku_id}
    assert client.ensured == [item_id]


# --------------------------------------------------------------------------- #
# Counting                                                                     #
# --------------------------------------------------------------------------- #
def test_counts_unique_track_ids_per_category(settings, monkeypatch):
    frames = [
        [Detection("carton", 1, 0.9, [])],
        [Detection("carton", 1, 0.9, []), Detection("carton", 2, 0.8, [])],
        [Detection("pallet", 10, 0.9, []), Detection("carton", 2, 0.8, [])],
    ]
    job = make_job(
        targets=[make_target("carton"), make_target("pallet")], report_interval_seconds=1000.0
    )
    pipeline, client, source = build_pipeline(
        job, settings, frames=frames, monkeypatch=monkeypatch
    )
    pipeline.run()

    assert job.counts == {"carton": 2, "pallet": 1}
    assert job.frames_processed == 3
    assert job.status is JobStatus.stopped
    assert source.released is True
    # The final flush reports both categories once.
    assert sorted(amount for _, amount in client.restocks) == [1, 2]


def test_detections_without_track_id_or_unknown_class_are_ignored(settings, monkeypatch):
    frames = [
        [
            Detection("carton", None, 0.9, []),
            Detection("person", 5, 0.9, []),
            Detection("carton", 1, 0.9, []),
        ]
    ]
    job = make_job(targets=[make_target("carton")])
    pipeline, _, _ = build_pipeline(job, settings, frames=frames, monkeypatch=monkeypatch)
    pipeline.run()
    assert job.counts == {"carton": 1}


def test_frame_sample_interval_skips_frames(settings, monkeypatch):
    frames = [
        [Detection("carton", 1, 0.9, [])],
        [Detection("carton", 2, 0.9, [])],
        [Detection("carton", 3, 0.9, [])],
        [Detection("carton", 4, 0.9, [])],
    ]
    job = make_job(targets=[make_target("carton")], frame_sample_interval=2)
    pipeline, _, _ = build_pipeline(job, settings, frames=frames, monkeypatch=monkeypatch)
    pipeline.run()
    # Only frames 2 and 4 (1-based) are analysed.
    assert job.counts == {"carton": 2}
    assert job.frames_processed == 4


def test_stop_request_ends_the_loop_immediately(settings, monkeypatch):
    job = make_job(targets=[make_target("carton")])
    frames = [[Detection("carton", 1, 0.9, [])]]
    pipeline, _, _ = build_pipeline(job, settings, frames=frames, monkeypatch=monkeypatch)
    job.request_stop()
    pipeline.run()
    assert job.frames_processed == 0
    assert job.status is JobStatus.stopped


def test_periodic_report_is_triggered_by_the_interval(settings, monkeypatch):
    frames = [[Detection("carton", i, 0.9, [])] for i in range(1, 4)]
    job = make_job(targets=[make_target("carton")], report_interval_seconds=1.0)
    pipeline, client, _ = build_pipeline(job, settings, frames=frames, monkeypatch=monkeypatch)

    ticks = iter([0.0, 5.0, 5.0, 5.0, 5.0])
    monkeypatch.setattr(pipeline_module.time, "monotonic", lambda: next(ticks, 5.0))
    pipeline.run()

    # First report fires mid-loop, the rest is flushed at the end.
    assert [amount for _, amount in client.restocks] == [1, 2]


# --------------------------------------------------------------------------- #
# Reporting                                                                    #
# --------------------------------------------------------------------------- #
def test_consume_mode_calls_consume(settings, monkeypatch):
    frames = [[Detection("pallet", 1, 0.9, [])]]
    job = make_job(targets=[make_target("pallet", report_mode=JobReportMode.consume)])
    pipeline, client, _ = build_pipeline(job, settings, frames=frames, monkeypatch=monkeypatch)
    pipeline.run()
    assert [amount for _, amount in client.consumes] == [1]
    assert client.restocks == []


def test_no_report_when_delta_is_zero(settings, monkeypatch):
    job = make_job(targets=[make_target("carton")])
    pipeline, client, _ = build_pipeline(job, settings, frames=[], monkeypatch=monkeypatch)
    pipeline.run()
    assert client.restocks == []
    assert job.last_report_at is None


def test_unresolved_target_is_skipped(settings):
    job = make_job(targets=[make_target("carton")])
    pipeline, client, _ = build_pipeline(job, settings)
    job.counts["carton"] = 3
    job.resolved_item_ids["carton"] = None
    pipeline._report_deltas()  # noqa: SLF001
    assert client.restocks == []
    assert job.last_reported_counts["carton"] == 0


def test_failed_upstream_report_is_recorded_but_not_committed(settings):
    item_id = uuid4()
    job = make_job(targets=[make_target("carton", item_id=item_id)])
    repository = InMemoryJobRepository()
    client = FakeInventoryClient()
    client.raise_on_report = InventoryClientError("upstream down", status_code=500)
    pipeline, _, _ = build_pipeline(job, settings, client=client, repository=repository)

    job.counts["carton"] = 2
    job.resolved_item_ids["carton"] = item_id
    pipeline._report_deltas()  # noqa: SLF001

    assert job.last_reported_counts["carton"] == 0
    assert job.last_report_at is None
    events = repository.list_events(job.id)
    assert [(e.status, e.delta) for e in events] == [("failed", 2)]
    assert "upstream down" in events[0].error


def test_successful_report_persists_event_and_progress(settings):
    item_id = uuid4()
    job = make_job(targets=[make_target("carton", item_id=item_id)])
    repository = InMemoryJobRepository()
    repository.insert_job(
        job_id=job.id,
        source=job.source,
        source_type=job.source_type.value,
        model_path=job.model_path,
        targets=job.targets,
        status=job.status.value,
        counts=dict(job.counts),
        last_reported_counts=dict(job.last_reported_counts),
        resolved_item_ids={"carton": None},
        created_at=job.created_at,
    )
    pipeline, client, _ = build_pipeline(job, settings, repository=repository)

    job.counts["carton"] = 4
    job.resolved_item_ids["carton"] = item_id
    pipeline._report_deltas()  # noqa: SLF001

    assert client.restocks == [(item_id, 4)]
    assert job.last_reported_counts["carton"] == 4
    assert job.last_report_at is not None
    row = repository.get_job(job.id)
    assert row.counts == {"carton": 4}
    assert [(e.status, e.delta) for e in repository.list_events(job.id)] == [("success", 4)]


# --------------------------------------------------------------------------- #
# Error handling                                                                #
# --------------------------------------------------------------------------- #
def test_missing_inventory_item_marks_job_as_error(settings, monkeypatch):
    job = make_job(targets=[make_target("carton")])
    client = FakeInventoryClient()
    client.raise_on_ensure = ItemNotFoundError("item gone")
    pipeline, _, _ = build_pipeline(job, settings, client=client, monkeypatch=monkeypatch)
    pipeline.run()
    assert job.status is JobStatus.error
    assert job.error == "item gone"
    assert job.stopped_at is not None


def test_video_source_error_marks_job_as_error(settings, monkeypatch):
    job = make_job(targets=[make_target("carton")])
    pipeline, _, _ = build_pipeline(job, settings, monkeypatch=monkeypatch)
    monkeypatch.setattr(
        DetectionPipeline,
        "_process_loop",
        lambda self: (_ for _ in ()).throw(VideoSourceError("stream lost")),
    )
    pipeline.run()
    assert job.status is JobStatus.error
    assert job.error == "stream lost"


def test_unexpected_error_is_captured_with_its_type(settings, monkeypatch):
    job = make_job(targets=[make_target("carton")])
    pipeline, _, _ = build_pipeline(job, settings, monkeypatch=monkeypatch)
    monkeypatch.setattr(
        DetectionPipeline,
        "_process_loop",
        lambda self: (_ for _ in ()).throw(RuntimeError("ultralytics missing")),
    )
    pipeline.run()
    assert job.status is JobStatus.error
    assert job.error == "RuntimeError: ultralytics missing"


@pytest.mark.parametrize(
    "method",
    ["insert_event", "update_job_status", "update_job_progress"],
)
def test_persistence_failures_do_not_break_the_worker(settings, monkeypatch, method):
    item_id = uuid4()
    job = make_job(targets=[make_target("carton", item_id=item_id)])
    repository = InMemoryJobRepository()

    def boom(*args, **kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr(repository, method, boom)
    pipeline, client, _ = build_pipeline(job, settings, repository=repository)
    job.counts["carton"] = 1
    job.resolved_item_ids["carton"] = item_id

    pipeline._report_deltas()  # noqa: SLF001
    pipeline._persist_status()  # noqa: SLF001
    pipeline._cleanup()  # noqa: SLF001

    assert client.restocks == [(item_id, 1)]


def test_cleanup_releases_source_and_detector(settings):
    job = make_job(targets=[make_target("carton")])
    pipeline, _, source = build_pipeline(job, settings, frames=[[]])
    pipeline._cleanup()  # noqa: SLF001
    assert source.released is True
    assert pipeline._source is None and pipeline._detector is None  # noqa: SLF001
    assert job.stopped_at is not None


def test_persistence_helpers_are_noops_without_repository(settings):
    job = make_job(targets=[make_target("carton")])
    pipeline, _, _ = build_pipeline(job, settings)
    pipeline._persist_status()  # noqa: SLF001
    pipeline._persist_progress()  # noqa: SLF001
    pipeline._persist_event(  # noqa: SLF001
        target_name="carton",
        delta=1,
        item_id=uuid4(),
        report_mode="restock",
        status="success",
        error=None,
    )


# --------------------------------------------------------------------------- #
# Demo mode wiring                                                             #
# --------------------------------------------------------------------------- #
def test_start_selects_the_simulated_stack_for_demo_sources(settings, monkeypatch):
    from app.core.simulated import SimulatedDetector, SimulatedSource

    job = make_job(source="demo://cartons", targets=[make_target("carton")])
    pipeline = DetectionPipeline(job, FakeInventoryClient(), settings, None)
    pipeline._start()  # noqa: SLF001
    assert isinstance(pipeline._detector, SimulatedDetector)  # noqa: SLF001
    assert isinstance(pipeline._source, SimulatedSource)  # noqa: SLF001
    assert job.status is JobStatus.running
    assert job.started_at is not None
