"""Shared fixtures for the vision-service test suite.

The tests never load YOLO/torch/OpenCV and never touch Postgres: the detector,
the video source, the inventory REST client and the repository are all
replaced by lightweight fakes.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest
from app.config import Settings
from app.core.detector import Detection
from app.schemas.job_schema import CountingTarget, JobReportMode, JobSourceType
from app.services.job import DetectionJob


class FakeInventoryClient:
    """Records calls instead of performing HTTP requests."""

    def __init__(self, *, sku_map: dict[str, UUID] | None = None) -> None:
        self.sku_map = sku_map or {}
        self.ensured: list[UUID] = []
        self.restocks: list[tuple[UUID, int]] = []
        self.consumes: list[tuple[UUID, int]] = []
        self.raise_on_report: Exception | None = None
        self.raise_on_ensure: Exception | None = None
        self.raise_on_resolve: Exception | None = None

    def ensure_item_exists(self, item_id: UUID) -> None:
        if self.raise_on_ensure is not None:
            raise self.raise_on_ensure
        self.ensured.append(item_id)

    def resolve_item_id_by_sku(self, sku: str) -> UUID:
        if self.raise_on_resolve is not None:
            raise self.raise_on_resolve
        return self.sku_map[sku]

    def restock(self, item_id: UUID, amount: int) -> dict[str, Any]:
        if self.raise_on_report is not None:
            raise self.raise_on_report
        self.restocks.append((item_id, amount))
        return {"amount": amount}

    def consume(self, item_id: UUID, amount: int) -> dict[str, Any]:
        if self.raise_on_report is not None:
            raise self.raise_on_report
        self.consumes.append((item_id, amount))
        return {"amount": amount}


class FakeDetector:
    """Returns a scripted list of detections per frame."""

    def __init__(self, frames: list[list[Detection]]) -> None:
        self.frames = frames

    def detect_and_track(self, frame: Any) -> list[Detection]:
        if isinstance(frame, int) and 0 <= frame < len(self.frames):
            return self.frames[frame]
        return []


class FakeSource:
    """Yields frame indices, then signals end-of-stream."""

    def __init__(self, frame_count: int) -> None:
        self.frame_count = frame_count
        self._i = 0
        self.released = False

    def open(self) -> None:
        pass

    def read(self) -> tuple[bool, Any]:
        if self._i >= self.frame_count:
            return False, None
        idx = self._i
        self._i += 1
        return True, idx

    def release(self) -> None:
        self.released = True


def make_target(
    name: str = "carton",
    *,
    class_names: list[str] | None = None,
    item_id: UUID | None = None,
    sku: str | None = None,
    report_mode: JobReportMode = JobReportMode.restock,
) -> CountingTarget:
    if item_id is None and sku is None:
        item_id = uuid4()
    return CountingTarget(
        name=name,
        class_names=class_names or [name],
        target_item_id=item_id,
        target_sku=sku,
        report_mode=report_mode,
    )


def make_job(
    *,
    source: str = "rtsp://camera/stream",
    source_type: JobSourceType = JobSourceType.rtsp,
    targets: list[CountingTarget] | None = None,
    model_path: str = "yolo11n.pt",
    frame_sample_interval: int = 1,
    report_interval_seconds: float = 1.0,
) -> DetectionJob:
    return DetectionJob(
        source=source,
        source_type=source_type,
        targets=targets or [make_target()],
        model_path=model_path,
        frame_sample_interval=frame_sample_interval,
        report_interval_seconds=report_interval_seconds,
    )


@pytest.fixture
def settings() -> Settings:
    return Settings(_env_file=None)


@pytest.fixture
def fake_client() -> FakeInventoryClient:
    return FakeInventoryClient()
