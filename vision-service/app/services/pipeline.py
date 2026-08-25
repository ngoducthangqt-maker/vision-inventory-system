"""Detection pipeline.

Ties together the video source, the YOLO11 detector, the inventory REST client
and the Postgres repository. Runs inside a worker thread (one per job).

Loop:
  1. Resolve every counting target to an inventory item id.
  2. Open the video source; for every Nth frame run YOLO11 tracking.
  3. Map each new track id to a counting category via class-name matching and
     increment that category's counter (unique-object counting).
  4. Every ``report_interval_seconds`` push per-category deltas to the
     inventory-service (restock / consume) and persist a ``detection_event``
     audit row + updated job progress to Postgres.
  5. On stop or EOF flush a final per-category delta report.

This realises the end-to-end data flow:
    Camera (RTSP) -> YOLO -> Inventory API -> Postgres
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from uuid import UUID

from app.clients.inventory_client import (
    InventoryClient,
    InventoryClientError,
    ItemNotFoundError,
)
from app.config import Settings
from app.core.detector import ObjectDetector
from app.core.source import VideoSource, VideoSourceError
from app.infrastructure.repository import JobRepository
from app.schemas.job_schema import EventStatus, JobReportMode, JobStatus
from app.services.job import DetectionJob
from app.utils import serialize_item_ids, swallow_persistence_errors, utcnow

logger = logging.getLogger(__name__)


class DetectionPipeline:
    """Runs a single detection job to completion (or until stopped)."""

    def __init__(
        self,
        job: DetectionJob,
        inventory_client: InventoryClient,
        settings: Settings,
        repository: JobRepository | None = None,
    ) -> None:
        self._job = job
        self._client = inventory_client
        self._settings = settings
        self._repo = repository
        self._detector: ObjectDetector | None = None
        self._source: VideoSource | None = None

        # track_id -> target_name (which category a tracked object belongs to)
        self._seen_track_ids: dict[int, str] = {}
        # class_name (lower-cased) -> target_name, built from job targets
        self._class_to_target: dict[str, str] = {}

    # ------------------------------------------------------------------ #
    # Main entry point                                                    #
    # ------------------------------------------------------------------ #
    def run(self) -> None:
        """Execute the job. Updates ``job`` state; never raises."""
        try:
            self._build_class_map()
            self._resolve_targets()
            self._start()
            self._process_loop()
            self._final_report()
            self._job.status = JobStatus.stopped
        except ItemNotFoundError as exc:
            logger.warning("Job %s: %s", self._job.id, exc)
            self._job.status = JobStatus.error
            self._job.error = str(exc)
        except VideoSourceError as exc:
            logger.warning("Job %s: video source error: %s", self._job.id, exc)
            self._job.status = JobStatus.error
            self._job.error = str(exc)
        except Exception as exc:  # noqa: BLE001 - top-level worker guard
            logger.exception("Job %s failed unexpectedly", self._job.id)
            self._job.status = JobStatus.error
            self._job.error = f"{type(exc).__name__}: {exc}"
        finally:
            self._cleanup()

    # ------------------------------------------------------------------ #
    # Setup                                                               #
    # ------------------------------------------------------------------ #
    def _build_class_map(self) -> None:
        """Build a lower-cased class-name -> target-name lookup from targets."""
        for target in self._job.targets:
            for class_name in target.class_names:
                key = class_name.strip().lower()
                if key:
                    self._class_to_target[key] = target.name

    def _resolve_targets(self) -> None:
        """Resolve each target's inventory item (UUID or SKU -> resolved id)."""
        for target in self._job.targets:
            if target.target_item_id is not None:
                self._client.ensure_item_exists(target.target_item_id)
                self._job.resolved_item_ids[target.name] = target.target_item_id
            else:
                assert target.target_sku is not None
                item_id = self._client.resolve_item_id_by_sku(target.target_sku)
                self._job.resolved_item_ids[target.name] = item_id

    def _start(self) -> None:
        """Instantiate the detector and open the video source.

        When the source selects demo mode (``demo://...``) the simulated
        detector/source are used instead of YOLO11 + OpenCV, so the full
        pipeline runs with zero ML dependencies.
        """
        from app.core.simulated import SimulatedDetector, SimulatedSource, is_demo_source

        self._job.status = JobStatus.running
        self._job.started_at = utcnow()
        if is_demo_source(self._job.source):
            self._detector = SimulatedDetector(
                model_path=self._job.model_path,
                tracker_config=self._settings.tracker_config,
                confidence_threshold=self._settings.confidence_threshold,
            )
            self._source = SimulatedSource(self._job.source, self._job.source_type)
            logger.info("Job %s using DEMO mode (simulated detector + source).", self._job.id)
        else:
            self._detector = ObjectDetector(
                model_path=self._job.model_path,
                tracker_config=self._settings.tracker_config,
                confidence_threshold=self._settings.confidence_threshold,
            )
            self._source = VideoSource(self._job.source, self._job.source_type)
        self._source.open()
        self._persist_status()
        logger.info(
            "Job %s started: source=%s type=%s model=%s targets=%s",
            self._job.id,
            self._job.source,
            self._job.source_type.value,
            self._job.model_path,
            [t.name for t in self._job.targets],
        )

    # ------------------------------------------------------------------ #
    # Frame loop                                                          #
    # ------------------------------------------------------------------ #
    def _process_loop(self) -> None:
        """Read frames, count unique objects per category, report deltas."""
        assert self._detector is not None and self._source is not None

        sample_interval = max(1, self._job.frame_sample_interval)
        report_interval = max(1.0, self._job.report_interval_seconds)
        last_report_ts = time.monotonic()
        frame_idx = 0

        while not self._job.stop_requested:
            ok, frame = self._source.read()
            if not ok:
                logger.info("Job %s: end of stream reached.", self._job.id)
                break

            frame_idx += 1
            self._job.frames_processed = frame_idx
            if frame_idx % sample_interval != 0:
                continue

            detections = self._detector.detect_and_track(frame)
            for det in detections:
                if det.track_id is None:
                    continue
                if det.track_id in self._seen_track_ids:
                    # Already counted this tracked object (in any category).
                    continue
                key = det.class_name.strip().lower()
                target_name = self._class_to_target.get(key)
                if target_name is None:
                    # Class is not part of any counting target; ignore.
                    continue
                self._seen_track_ids[det.track_id] = target_name
                self._job.counts[target_name] = self._job.counts.get(target_name, 0) + 1

            now = time.monotonic()
            if now - last_report_ts >= report_interval:
                self._report_deltas()
                last_report_ts = now

    # ------------------------------------------------------------------ #
    # Reporting                                                           #
    # ------------------------------------------------------------------ #
    def _report_deltas(self) -> None:
        """Push per-category count deltas upstream and persist audit events."""
        report_time = utcnow()
        any_reported = False

        for target in self._job.targets:
            count = self._job.counts.get(target.name, 0)
            last = self._job.last_reported_counts.get(target.name, 0)
            delta = count - last
            if delta <= 0:
                continue

            item_id = self._job.resolved_item_ids.get(target.name)
            if item_id is None:
                continue

            status = EventStatus.success
            error: str | None = None
            try:
                if target.report_mode is JobReportMode.restock:
                    self._client.restock(item_id, delta)
                else:
                    self._client.consume(item_id, delta)
            except InventoryClientError as exc:
                status = EventStatus.failed
                error = str(exc)
                logger.warning(
                    "Job %s target %s: upstream %s failed (delta=%d): %s",
                    self._job.id,
                    target.name,
                    target.report_mode.value,
                    delta,
                    exc,
                )

            # Persist an audit event for this report attempt (success or fail).
            self._persist_event(
                target_name=target.name,
                delta=delta,
                item_id=item_id,
                report_mode=target.report_mode.value,
                status=status.value,
                error=error,
            )

            if status is EventStatus.success:
                self._job.last_reported_counts[target.name] = count
                any_reported = True
                logger.info(
                    "Job %s reported %s delta=%d for target=%s (total=%d)",
                    self._job.id,
                    target.report_mode.value,
                    delta,
                    target.name,
                    count,
                )

        if any_reported:
            self._job.last_report_at = report_time
            self._persist_progress(last_report_at=report_time)

    def _final_report(self) -> None:
        """Flush any remaining per-category deltas when the job ends."""
        self._report_deltas()

    # ------------------------------------------------------------------ #
    # Persistence helpers                                                 #
    # ------------------------------------------------------------------ #
    def _persist_status(
        self,
        *,
        error: str | None = None,
        stopped_at: datetime | None = None,
        last_report_at: datetime | None = None,
    ) -> None:
        if self._repo is None:
            return
        with swallow_persistence_errors(
            logger, "Job %s: failed to persist status", self._job.id
        ):
            self._repo.update_job_status(
                self._job.id,
                status=self._job.status.value,
                error=error,
                started_at=self._job.started_at,
                stopped_at=stopped_at,
                last_report_at=last_report_at,
            )

    def _persist_progress(self, *, last_report_at: datetime | None = None) -> None:
        if self._repo is None:
            return
        with swallow_persistence_errors(
            logger, "Job %s: failed to persist progress", self._job.id
        ):
            self._repo.update_job_progress(
                self._job.id,
                counts=dict(self._job.counts),
                last_reported_counts=dict(self._job.last_reported_counts),
                resolved_item_ids=serialize_item_ids(self._job.resolved_item_ids),
                frames_processed=self._job.frames_processed,
                last_report_at=last_report_at,
            )

    def _persist_event(
        self,
        *,
        target_name: str,
        delta: int,
        item_id: UUID,
        report_mode: str,
        status: str,
        error: str | None,
    ) -> None:
        if self._repo is None:
            return
        with swallow_persistence_errors(
            logger, "Job %s: failed to persist event", self._job.id
        ):
            self._repo.insert_event(
                job_id=self._job.id,
                target_name=target_name,
                delta=delta,
                item_id=item_id,
                report_mode=report_mode,
                status=status,
                error=error,
            )

    # ------------------------------------------------------------------ #
    # Cleanup                                                             #
    # ------------------------------------------------------------------ #
    def _cleanup(self) -> None:
        if self._source is not None:
            self._source.release()
            self._source = None
        # Drop detector to release GPU/CPU memory held by the model.
        self._detector = None
        self._job.stopped_at = utcnow()
        self._persist_status(
            error=self._job.error,
            stopped_at=self._job.stopped_at,
            last_report_at=self._job.last_report_at,
        )
        self._persist_progress()


__all__ = ["DetectionPipeline"]
