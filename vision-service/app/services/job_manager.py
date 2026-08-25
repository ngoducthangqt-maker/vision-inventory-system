"""In-memory + Postgres job manager.

Owns the registry of active/finished detection jobs and the worker threads
that execute them. Job metadata and audit events are also persisted to
Postgres via ``JobRepository`` so the data survives restarts. A module-level
singleton (``get_job_manager``) is used by the FastAPI dependency.
"""

from __future__ import annotations

import logging
import threading
from uuid import UUID

from app.clients.inventory_client import InventoryClient
from app.config import Settings, get_settings
from app.infrastructure.repository import JobRepository
from app.schemas.job_schema import JobCreateRequest
from app.services.job import DetectionJob
from app.services.pipeline import DetectionPipeline
from app.utils import serialize_item_ids, swallow_persistence_errors

logger = logging.getLogger(__name__)


class JobNotFoundError(KeyError):
    """Raised when a job id is not registered."""

    def __init__(self, job_id: UUID) -> None:
        self.job_id = job_id
        super().__init__(f"Job {job_id} not found.")


class JobManager:
    """Thread-safe registry + launcher of detection jobs."""

    def __init__(
        self,
        settings: Settings,
        inventory_client: InventoryClient,
        repository: JobRepository | None,
    ) -> None:
        self._settings = settings
        self._client = inventory_client
        self._repo = repository
        self._jobs: dict[UUID, DetectionJob] = {}
        self._threads: dict[UUID, threading.Thread] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ #
    # CRUD                                                                #
    # ------------------------------------------------------------------ #
    def create_job(self, request: JobCreateRequest) -> DetectionJob:
        """Create a job from a request and (optionally) start it."""
        job = DetectionJob(
            source=request.source,
            source_type=request.source_type,
            targets=request.targets,
            model_path=request.model_path or self._settings.default_model_path,
            frame_sample_interval=request.frame_sample_interval
            or self._settings.default_frame_sample_interval,
            report_interval_seconds=request.report_interval_seconds
            or self._settings.default_report_interval_seconds,
        )
        with self._lock:
            self._jobs[job.id] = job

        # Persist the initial job row so it is durable even before running.
        self._persist_job_insert(job)

        if request.auto_start:
            self._start_thread(job)
        return job

    def get_job(self, job_id: UUID) -> DetectionJob:
        with self._lock:
            if job_id not in self._jobs:
                raise JobNotFoundError(job_id)
            return self._jobs[job_id]

    def list_jobs(self) -> list[DetectionJob]:
        with self._lock:
            return list(self._jobs.values())

    def stop_job(self, job_id: UUID) -> DetectionJob:
        job = self.get_job(job_id)
        job.request_stop()
        return job

    def delete_job(self, job_id: UUID) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
        if job is None:
            raise JobNotFoundError(job_id)
        job.request_stop()
        thread = self._threads.get(job_id)
        if thread is not None and thread.is_alive():
            thread.join(timeout=5.0)
        with self._lock:
            self._jobs.pop(job_id, None)
            self._threads.pop(job_id, None)

    # ------------------------------------------------------------------ #
    # Audit events                                                        #
    # ------------------------------------------------------------------ #
    def list_events(self, job_id: UUID) -> list:
        """Return persisted detection events for a job (empty if no DB)."""
        if self._repo is None:
            return []
        try:
            self.get_job(job_id)  # raises if unknown in-memory
        except JobNotFoundError:
            pass  # still allow reading historical events for finished/removed jobs
        return self._repo.list_events(job_id)

    # ------------------------------------------------------------------ #
    # Worker management                                                   #
    # ------------------------------------------------------------------ #
    def _start_thread(self, job: DetectionJob) -> None:
        pipeline = DetectionPipeline(
            job=job,
            inventory_client=self._client,
            settings=self._settings,
            repository=self._repo,
        )
        thread = threading.Thread(
            target=pipeline.run,
            name=f"vision-job-{job.id}",
            daemon=True,
        )
        with self._lock:
            self._threads[job.id] = thread
        thread.start()

    def shutdown(self) -> None:
        """Stop every running job and wait briefly for threads to exit."""
        with self._lock:
            jobs = list(self._jobs.values())
        for job in jobs:
            job.request_stop()
        for job in jobs:
            thread = self._threads.get(job.id)
            if thread is not None and thread.is_alive():
                thread.join(timeout=5.0)

    # ------------------------------------------------------------------ #
    # Persistence                                                         #
    # ------------------------------------------------------------------ #
    def _persist_job_insert(self, job: DetectionJob) -> None:
        if self._repo is None:
            return
        with swallow_persistence_errors(
            logger, "Job %s: failed to persist initial row", job.id
        ):
            self._repo.insert_job(
                job_id=job.id,
                source=job.source,
                source_type=job.source_type.value,
                model_path=job.model_path,
                targets=job.targets,
                status=job.status.value,
                counts=dict(job.counts),
                last_reported_counts=dict(job.last_reported_counts),
                resolved_item_ids=serialize_item_ids(job.resolved_item_ids),
                created_at=job.created_at,
            )


# --------------------------------------------------------------------------- #
# Singleton accessor (used by FastAPI dependency injection)                    #
# --------------------------------------------------------------------------- #
_job_manager: JobManager | None = None
_singleton_lock = threading.Lock()


def get_job_manager() -> JobManager:
    """Return the process-wide ``JobManager`` singleton."""
    global _job_manager
    if _job_manager is None:
        with _singleton_lock:
            if _job_manager is None:
                settings = get_settings()
                client = InventoryClient(
                    base_url=settings.inventory_service_url,
                    api_prefix=settings.inventory_api_prefix,
                    timeout_seconds=settings.inventory_request_timeout_seconds,
                )
                # The repository is optional: the service still runs (in-memory
                # only) when Postgres is not configured/unreachable at startup.
                # ``REPOSITORY_MODE=inmemory`` forces the in-memory repo (no DB).
                repo: JobRepository | None
                if (settings.environment != "production" and
                        getattr(settings, "repository_mode", "") == "inmemory"):
                    from app.infrastructure.inmemory_repository import InMemoryJobRepository
                    repo = InMemoryJobRepository()
                    logger.info("Using in-memory JobRepository (REPOSITORY_MODE=inmemory).")
                else:
                    try:
                        repo = JobRepository()
                    except Exception:  # noqa: BLE001
                        logger.exception("JobRepository unavailable; running without DB persistence.")
                        repo = None
                _job_manager = JobManager(settings, client, repo)
    return _job_manager


__all__ = ["JobManager", "JobNotFoundError", "get_job_manager"]
