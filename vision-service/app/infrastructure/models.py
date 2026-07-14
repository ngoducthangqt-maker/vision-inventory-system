"""SQLAlchemy ORM models for the vision-service database.

Tables:
    detection_jobs    - one row per detection job (durable runtime state)
    detection_events  - audit log of every report sent to inventory-service

The "Camera -> YOLO -> Inventory API -> Postgres" data flow lands here:
each upstream report (the result of counting via YOLO and pushing through the
Inventory API) is persisted as a ``detection_events`` row.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DetectionJobModel(Base):
    """Persisted record of a detection job."""

    __tablename__ = "detection_jobs"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    source: Mapped[str] = mapped_column(String(512), nullable=False)
    source_type: Mapped[str] = mapped_column(String(16), nullable=False)
    model_path: Mapped[str] = mapped_column(String(256), nullable=False)
    # Serialised list of CountingTarget dicts (name, class_names, report_mode, ...).
    targets: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    # {target_name: count} and {target_name: last_reported_count}.
    counts: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    last_reported_counts: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    resolved_item_ids: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    frames_processed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_report_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    stopped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<DetectionJobModel id={self.id} status={self.status!r}>"


class DetectionEventModel(Base):
    """Audit entry for a single report pushed to inventory-service."""

    __tablename__ = "detection_events"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    job_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("detection_jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    target_name: Mapped[str] = mapped_column(String(64), nullable=False)
    delta: Mapped[int] = mapped_column(Integer, nullable=False)
    item_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    report_mode: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)  # success | failed
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, index=True
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<DetectionEventModel job={self.job_id} target={self.target_name!r} "
            f"delta={self.delta} status={self.status!r}>"
        )


__all__ = ["DetectionJobModel", "DetectionEventModel"]
