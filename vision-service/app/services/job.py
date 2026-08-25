"""In-memory detection job domain object.

Holds the runtime state of a single detection job, supporting **multiple
counting categories** (e.g. ``carton`` and ``pallet``). Per-category counters
and resolved inventory item ids are tracked independently.
"""

from __future__ import annotations

from datetime import datetime
from threading import Event
from uuid import UUID, uuid4

from app.schemas.job_schema import CountingTarget, JobSourceType, JobStatus
from app.utils import utcnow


class DetectionJob:
    """Runtime state for one multi-category counting job."""

    def __init__(
        self,
        *,
        source: str,
        source_type: JobSourceType,
        targets: list[CountingTarget],
        model_path: str,
        frame_sample_interval: int,
        report_interval_seconds: float,
    ) -> None:
        if not targets:
            raise ValueError("A job requires at least one counting target.")
        self.id: UUID = uuid4()
        self.source: str = source
        self.source_type: JobSourceType = source_type
        self.targets: list[CountingTarget] = list(targets)
        self.model_path: str = model_path
        self.frame_sample_interval: int = frame_sample_interval
        self.report_interval_seconds: float = report_interval_seconds

        # Per-category runtime state.
        names = [t.name for t in self.targets]
        self.counts: dict[str, int] = {n: 0 for n in names}
        self.last_reported_counts: dict[str, int] = {n: 0 for n in names}
        self.resolved_item_ids: dict[str, UUID | None] = {n: None for n in names}

        # Job-level state.
        self.status: JobStatus = JobStatus.pending
        self.frames_processed: int = 0
        self.started_at: datetime | None = None
        self.last_report_at: datetime | None = None
        self.stopped_at: datetime | None = None
        self.error: str | None = None
        self.created_at: datetime = utcnow()

        # Synchronisation primitive used to request a graceful stop.
        self._stop_event: Event = Event()

    # ------------------------------------------------------------------ #
    # Aggregates                                                          #
    # ------------------------------------------------------------------ #
    @property
    def total_count(self) -> int:
        """Sum of current counts across all targets."""
        return sum(self.counts.values())

    @property
    def total_last_reported(self) -> int:
        """Sum of last reported counts across all targets."""
        return sum(self.last_reported_counts.values())

    # ------------------------------------------------------------------ #
    # Stop signalling                                                     #
    # ------------------------------------------------------------------ #
    def request_stop(self) -> None:
        """Signal the worker thread to stop after the current frame."""
        self._stop_event.set()

    @property
    def stop_requested(self) -> bool:
        return self._stop_event.is_set()

    # ------------------------------------------------------------------ #
    # Target lookup                                                       #
    # ------------------------------------------------------------------ #
    def target_named(self, name: str) -> CountingTarget | None:
        """Return the target with the given name, or ``None``."""
        for t in self.targets:
            if t.name == name:
                return t
        return None


__all__ = ["DetectionJob"]
