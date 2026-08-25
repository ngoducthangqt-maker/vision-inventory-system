"""In-memory JobRepository for demos / tests without Postgres.

Implements the same interface as ``JobRepository`` but stores jobs and events
in plain dicts. Selected via the ``REPOSITORY_MODE=inmemory`` setting (see
``job_manager.get_job_manager``).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from app.utils import present_values, target_to_dict, utcnow


class _JobRow:
    """Mimics the ORM row attributes read by the API layer."""

    def __init__(self, **kw: Any) -> None:
        self.__dict__.update(kw)


class _EventRow:
    def __init__(self, **kw: Any) -> None:
        self.id = kw.get("id", uuid4())
        self.job_id = kw["job_id"]
        self.target_name = kw["target_name"]
        self.delta = kw["delta"]
        self.item_id = kw["item_id"]
        self.report_mode = kw["report_mode"]
        self.status = kw["status"]
        self.error = kw.get("error")
        self.created_at = kw.get("created_at", utcnow())


class InMemoryJobRepository:
    """Process-local, thread-safe (via GIL) stand-in for the Postgres repo."""

    def __init__(self) -> None:
        self._jobs: dict[UUID, dict[str, Any]] = {}
        self._events: list[_EventRow] = []

    def insert_job(self, *, job_id: UUID, source: str, source_type: str, model_path: str,
                   targets: list[Any], status: str, counts: dict[str, int],
                   last_reported_counts: dict[str, int], resolved_item_ids: dict[str, Any],
                   created_at: datetime) -> None:
        self._jobs[job_id] = {
            "id": job_id,
            "source": source,
            "source_type": source_type,
            "model_path": model_path,
            "targets": [target_to_dict(t) for t in targets],
            "status": status,
            "counts": dict(counts),
            "last_reported_counts": dict(last_reported_counts),
            "resolved_item_ids": dict(resolved_item_ids),
            "frames_processed": 0,
            "started_at": None,
            "last_report_at": None,
            "stopped_at": None,
            "error": None,
            "created_at": created_at,
        }

    def update_job_status(self, job_id: UUID, *, status: str, error: str | None = None,
                          started_at: datetime | None = None, last_report_at: datetime | None = None,
                          stopped_at: datetime | None = None) -> None:
        self._apply(
            job_id,
            status=status,
            **present_values(
                error=error,
                started_at=started_at,
                last_report_at=last_report_at,
                stopped_at=stopped_at,
            ),
        )

    def update_job_progress(self, job_id: UUID, *, counts: dict[str, int],
                            last_reported_counts: dict[str, int],
                            resolved_item_ids: dict[str, Any], frames_processed: int,
                            last_report_at: datetime | None = None) -> None:
        self._apply(
            job_id,
            counts=dict(counts),
            last_reported_counts=dict(last_reported_counts),
            resolved_item_ids=dict(resolved_item_ids),
            frames_processed=frames_processed,
            **present_values(last_report_at=last_report_at),
        )

    def _apply(self, job_id: UUID, **values: Any) -> None:
        """Merge a partial update into a stored job (no-op when unknown)."""
        row = self._jobs.get(job_id)
        if row is None:
            return
        row.update(values)

    def get_job(self, job_id: UUID) -> _JobRow | None:
        row = self._jobs.get(job_id)
        return _JobRow(**row) if row else None

    def list_jobs(self) -> list[_JobRow]:
        return [_JobRow(**dict(r)) for r in self._jobs.values()]

    def insert_event(self, *, job_id: UUID, target_name: str, delta: int, item_id: UUID,
                     report_mode: str, status: str, error: str | None) -> None:
        self._events.append(_EventRow(
            job_id=job_id, target_name=target_name, delta=delta, item_id=item_id,
            report_mode=report_mode, status=status, error=error,
        ))

    def list_events(self, job_id: UUID) -> list[_EventRow]:
        return [e for e in self._events if e.job_id == job_id]


__all__ = ["InMemoryJobRepository"]
