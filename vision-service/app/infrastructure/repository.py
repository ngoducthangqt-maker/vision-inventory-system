"""Sync repository for detection jobs and events.

Each method opens its own short-lived session so the worker thread (and the
FastAPI threadpool endpoints) can call it safely without sharing session
state across threads.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from app.infrastructure.models import DetectionEventModel, DetectionJobModel


def _target_to_dict(target: Any) -> dict[str, Any]:
    """Serialize a ``CountingTarget`` (pydantic) into a JSON-storable dict."""
    return {
        "name": target.name,
        "class_names": list(target.class_names),
        "target_item_id": str(target.target_item_id) if target.target_item_id else None,
        "target_sku": target.target_sku,
        "report_mode": target.report_mode.value
        if hasattr(target.report_mode, "value")
        else str(target.report_mode),
    }


class JobRepository:
    """Persistence gateway for detection jobs and their audit events."""

    def __init__(self, session_factory: sessionmaker[Session] | None = None) -> None:
        # Resolve the default session factory lazily so the service can start
        # without a configured database (graceful degradation).
        if session_factory is None:
            from app.core.database import get_session_factory

            session_factory = get_session_factory()
        self._session_factory = session_factory

    # ------------------------------------------------------------------ #
    # Jobs                                                                #
    # ------------------------------------------------------------------ #
    def insert_job(
        self,
        *,
        job_id: UUID,
        source: str,
        source_type: str,
        model_path: str,
        targets: Sequence[Any],
        status: str,
        counts: dict[str, int],
        last_reported_counts: dict[str, int],
        resolved_item_ids: dict[str, str | None],
        created_at: datetime,
    ) -> None:
        row = DetectionJobModel(
            id=job_id,
            source=source,
            source_type=source_type,
            model_path=model_path,
            targets=[_target_to_dict(t) for t in targets],
            status=status,
            counts=counts,
            last_reported_counts=last_reported_counts,
            resolved_item_ids=resolved_item_ids,
            frames_processed=0,
            created_at=created_at,
        )
        with self._session_factory() as session:
            session.add(row)
            session.commit()

    def update_job_status(
        self,
        job_id: UUID,
        *,
        status: str,
        error: str | None = None,
        started_at: datetime | None = None,
        last_report_at: datetime | None = None,
        stopped_at: datetime | None = None,
    ) -> None:
        values: dict[str, Any] = {"status": status}
        if error is not None:
            values["error"] = error
        if started_at is not None:
            values["started_at"] = started_at
        if last_report_at is not None:
            values["last_report_at"] = last_report_at
        if stopped_at is not None:
            values["stopped_at"] = stopped_at
        with self._session_factory() as session:
            session.execute(
                update(DetectionJobModel).where(DetectionJobModel.id == job_id).values(**values)
            )
            session.commit()

    def update_job_progress(
        self,
        job_id: UUID,
        *,
        counts: dict[str, int],
        last_reported_counts: dict[str, int],
        resolved_item_ids: dict[str, str | None],
        frames_processed: int,
        last_report_at: datetime | None = None,
    ) -> None:
        values: dict[str, Any] = {
            "counts": counts,
            "last_reported_counts": last_reported_counts,
            "resolved_item_ids": resolved_item_ids,
            "frames_processed": frames_processed,
        }
        if last_report_at is not None:
            values["last_report_at"] = last_report_at
        with self._session_factory() as session:
            session.execute(
                update(DetectionJobModel).where(DetectionJobModel.id == job_id).values(**values)
            )
            session.commit()

    def get_job(self, job_id: UUID) -> DetectionJobModel | None:
        with self._session_factory() as session:
            return session.get(DetectionJobModel, job_id)

    def list_jobs(self) -> list[DetectionJobModel]:
        with self._session_factory() as session:
            stmt = select(DetectionJobModel).order_by(DetectionJobModel.created_at.desc())
            return list(session.scalars(stmt).all())

    # ------------------------------------------------------------------ #
    # Events                                                              #
    # ------------------------------------------------------------------ #
    def insert_event(
        self,
        *,
        job_id: UUID,
        target_name: str,
        delta: int,
        item_id: UUID,
        report_mode: str,
        status: str,
        error: str | None,
    ) -> None:
        row = DetectionEventModel(
            job_id=job_id,
            target_name=target_name,
            delta=delta,
            item_id=item_id,
            report_mode=report_mode,
            status=status,
            error=error,
        )
        with self._session_factory() as session:
            session.add(row)
            session.commit()

    def list_events(self, job_id: UUID) -> list[DetectionEventModel]:
        with self._session_factory() as session:
            stmt = (
                select(DetectionEventModel)
                .where(DetectionEventModel.job_id == job_id)
                .order_by(DetectionEventModel.created_at.desc())
            )
            return list(session.scalars(stmt).all())


__all__ = ["JobRepository"]
