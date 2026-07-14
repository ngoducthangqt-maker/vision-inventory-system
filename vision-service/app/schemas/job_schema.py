"""Job-related Pydantic schemas.

The service counts **multiple object categories** in a single job (e.g.
``carton`` and ``pallet``). Each category is described by a ``CountingTarget``
which maps a set of YOLO class names to an inventory item and a report mode.
This lets one camera feed restock cartons AND pallets to (potentially
different) inventory items at the same time.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class JobSourceType(str, Enum):
    """How to interpret the ``source`` string."""

    rtsp = "rtsp"
    file = "file"
    auto = "auto"  # infer from the source scheme


class JobStatus(str, Enum):
    """Lifecycle state of a detection job."""

    pending = "pending"
    running = "running"
    stopped = "stopped"
    error = "error"


class JobReportMode(str, Enum):
    """How detected deltas are reported to inventory-service."""

    restock = "restock"  # positive deltas -> POST /inventory-items/{id}/restock
    consume = "consume"  # positive deltas -> POST /inventory-items/{id}/consume


class EventStatus(str, Enum):
    """Outcome of a single upstream report attempt."""

    success = "success"
    failed = "failed"


# --------------------------------------------------------------------------- #
# Counting target                                                              #
# --------------------------------------------------------------------------- #
class CountingTarget(BaseModel):
    """A single category to count (e.g. ``carton`` or ``pallet``).

    Exactly one of ``target_item_id`` / ``target_sku`` must be provided so the
    service knows which inventory item to update when this category is seen.
    """

    name: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Logical category name, e.g. 'carton' or 'pallet'.",
        examples=["carton"],
    )
    class_names: list[str] = Field(
        ...,
        min_length=1,
        description="YOLO class names (lower-cased match) counted as this category.",
        examples=[["carton", "box"]],
    )
    target_item_id: UUID | None = Field(
        default=None, description="UUID of the inventory item to update."
    )
    target_sku: str | None = Field(
        default=None, description="SKU of the inventory item (resolved via GET /inventory-items)."
    )
    report_mode: JobReportMode = Field(
        default=JobReportMode.restock,
        description="Whether detections of this category restock or consume the item.",
    )

    @model_validator(mode="after")
    def _validate_target(self) -> CountingTarget:
        if self.target_item_id is None and self.target_sku is None:
            raise ValueError(
                f"Counting target {self.name!r}: either 'target_item_id' or 'target_sku' is required."
            )
        if self.target_item_id is not None and self.target_sku is not None:
            raise ValueError(
                f"Counting target {self.name!r}: 'target_item_id' and 'target_sku' are mutually exclusive."
            )
        return self


class CountingTargetResponse(BaseModel):
    """Public view of a counting target with live counters."""

    model_config = ConfigDict(from_attributes=True)

    name: str
    class_names: list[str]
    target_item_id: UUID | None
    target_sku: str | None
    resolved_item_id: UUID | None = None
    report_mode: JobReportMode
    current_count: int = 0
    last_reported_count: int = 0


# --------------------------------------------------------------------------- #
# Job create / response                                                        #
# --------------------------------------------------------------------------- #
class JobCreateRequest(BaseModel):
    """Payload accepted by ``POST /jobs``."""

    source: str = Field(
        ...,
        min_length=1,
        description="RTSP URL (e.g. rtsp://...) or path to a local video file.",
        examples=["rtsp://admin:pass@10.0.0.5:554/stream"],
    )
    source_type: JobSourceType = Field(
        default=JobSourceType.auto,
        description='"rtsp", "file" or "auto" (infer from scheme).',
    )
    targets: list[CountingTarget] = Field(
        ...,
        min_length=1,
        description="One or more categories to count, e.g. carton and pallet.",
    )
    model_path: str | None = Field(
        default=None,
        description="Override the default YOLO11 model path (e.g. 'runs/weights/best.pt').",
    )
    frame_sample_interval: int | None = Field(
        default=None, ge=1, description="Process 1 frame every N. Defaults to app setting."
    )
    report_interval_seconds: float | None = Field(
        default=None, ge=1.0, description="Seconds between upstream reports. Defaults to app setting."
    )
    auto_start: bool = Field(default=True, description="Start processing immediately on creation.")

    @model_validator(mode="after")
    def _unique_target_names(self) -> JobCreateRequest:
        names = [t.name for t in self.targets]
        if len(names) != len(set(names)):
            raise ValueError(f"Counting target names must be unique, got: {names}")
        return self


class JobResponse(BaseModel):
    """Response shape for a single detection job."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source: str
    source_type: JobSourceType
    targets: list[CountingTargetResponse]
    model_path: str
    frame_sample_interval: int
    report_interval_seconds: float
    status: JobStatus
    total_count: int = Field(default=0, description="Sum of current counts across all targets.")
    total_last_reported: int = Field(default=0)
    frames_processed: int = 0
    started_at: datetime | None = None
    last_report_at: datetime | None = None
    stopped_at: datetime | None = None
    error: str | None = None
    created_at: datetime


class JobsListResponse(BaseModel):
    """Paginated collection response."""

    jobs: list[JobResponse]
    total: int


class JobStopResponse(BaseModel):
    """Response for the stop endpoint."""

    id: UUID
    status: JobStatus
    total_count: int
    total_last_reported: int


# --------------------------------------------------------------------------- #
# Detection events (audit trail)                                              #
# --------------------------------------------------------------------------- #
class DetectionEventResponse(BaseModel):
    """A single report pushed to inventory-service."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    job_id: UUID
    target_name: str
    delta: int
    item_id: UUID
    report_mode: JobReportMode
    status: EventStatus
    error: str | None
    created_at: datetime


class DetectionEventsListResponse(BaseModel):
    """Collection of detection events for a job."""

    events: list[DetectionEventResponse]
    total: int


__all__ = [
    "JobSourceType",
    "JobStatus",
    "JobReportMode",
    "EventStatus",
    "CountingTarget",
    "CountingTargetResponse",
    "JobCreateRequest",
    "JobResponse",
    "JobsListResponse",
    "JobStopResponse",
    "DetectionEventResponse",
    "DetectionEventsListResponse",
]
