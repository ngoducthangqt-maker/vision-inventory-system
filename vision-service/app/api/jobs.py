"""HTTP routes for detection jobs."""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.exc import SQLAlchemyError

from app.clients.inventory_client import InventoryClientError, ItemNotFoundError
from app.config import Settings, get_settings
from app.schemas.job_schema import (
    CountingTargetResponse,
    DetectionEventResponse,
    DetectionEventsListResponse,
    EventStatus,
    JobCreateRequest,
    JobReportMode,
    JobResponse,
    JobsListResponse,
    JobStatus,
    JobStopResponse,
)
from app.services.job_manager import JobManager, JobNotFoundError, get_job_manager

router = APIRouter(prefix="/jobs", tags=["jobs"])
logger = logging.getLogger(__name__)


def _to_target_response(job, target) -> CountingTargetResponse:  # type: ignore[no-untyped-def]
    return CountingTargetResponse(
        name=target.name,
        class_names=list(target.class_names),
        target_item_id=target.target_item_id,
        target_sku=target.target_sku,
        resolved_item_id=job.resolved_item_ids.get(target.name),
        report_mode=target.report_mode,
        current_count=job.counts.get(target.name, 0),
        last_reported_count=job.last_reported_counts.get(target.name, 0),
    )


def _to_response(job) -> JobResponse:  # type: ignore[no-untyped-def]
    return JobResponse(
        id=job.id,
        source=job.source,
        source_type=job.source_type,
        targets=[_to_target_response(job, t) for t in job.targets],
        model_path=job.model_path,
        frame_sample_interval=job.frame_sample_interval,
        report_interval_seconds=job.report_interval_seconds,
        status=job.status,
        total_count=job.total_count,
        total_last_reported=job.total_last_reported,
        frames_processed=job.frames_processed,
        started_at=job.started_at,
        last_report_at=job.last_report_at,
        stopped_at=job.stopped_at,
        error=job.error,
        created_at=job.created_at,
    )


def _event_to_response(row) -> DetectionEventResponse:  # type: ignore[no-untyped-def]
    return DetectionEventResponse(
        id=row.id,
        job_id=row.job_id,
        target_name=row.target_name,
        delta=row.delta,
        item_id=row.item_id,
        report_mode=JobReportMode(row.report_mode),
        status=EventStatus(row.status),
        error=row.error,
        created_at=row.created_at,
    )


# --------------------------------------------------------------------------- #
# Create                                                                       #
# --------------------------------------------------------------------------- #
@router.post(
    "",
    response_model=JobResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        404: {"description": "Target inventory item / SKU not found."},
        502: {"description": "inventory-service communication failure."},
    },
    summary="Create a carton/pallet counting detection job",
)
async def create_job(
    payload: JobCreateRequest,
    manager: JobManager = Depends(get_job_manager),
    settings: Settings = Depends(get_settings),
) -> JobResponse:
    # When auto_start is on, pre-validate target item ids so callers get fast
    # feedback on bad UUIDs. (SKU resolution happens in the worker thread.)
    if payload.auto_start:
        client = manager._client  # noqa: SLF001 - intentional access for pre-check
        try:
            for target in payload.targets:
                if target.target_item_id is not None:
                    client.ensure_item_exists(target.target_item_id)
        except ItemNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from None
        except InventoryClientError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"inventory-service unreachable: {exc}",
            ) from None

    try:
        job = manager.create_job(payload)
    except RuntimeError as exc:
        # E.g. ultralytics / opencv not installed.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        ) from None
    return _to_response(job)


# --------------------------------------------------------------------------- #
# List                                                                         #
# --------------------------------------------------------------------------- #
@router.get("", response_model=JobsListResponse, summary="List detection jobs")
async def list_jobs(
    status_filter: JobStatus | None = Query(default=None, alias="status"),
    manager: JobManager = Depends(get_job_manager),
) -> JobsListResponse:
    jobs = manager.list_jobs()
    if status_filter is not None:
        jobs = [j for j in jobs if j.status is status_filter]
    return JobsListResponse(jobs=[_to_response(j) for j in jobs], total=len(jobs))


# --------------------------------------------------------------------------- #
# Read one                                                                     #
# --------------------------------------------------------------------------- #
@router.get(
    "/{job_id}",
    response_model=JobResponse,
    responses={404: {"description": "Job not found."}},
    summary="Get a single detection job",
)
async def get_job(
    job_id: UUID,
    manager: JobManager = Depends(get_job_manager),
) -> JobResponse:
    try:
        job = manager.get_job(job_id)
    except JobNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found.",
        ) from None
    return _to_response(job)


# --------------------------------------------------------------------------- #
# Events (audit trail)                                                         #
# --------------------------------------------------------------------------- #
@router.get(
    "/{job_id}/events",
    response_model=DetectionEventsListResponse,
    responses={
        404: {"description": "Job not found."},
        503: {"description": "Detection event store unavailable."},
    },
    summary="List detection events (reports sent to inventory-service)",
)
async def list_job_events(
    job_id: UUID,
    manager: JobManager = Depends(get_job_manager),
) -> DetectionEventsListResponse:
    try:
        manager.get_job(job_id)
    except JobNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found.",
        ) from None
    try:
        rows = manager.list_events(job_id)
    except SQLAlchemyError as exc:
        logger.exception("Failed to list detection events for job %s", job_id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Detection event store unavailable: {exc}",
        ) from None
    return DetectionEventsListResponse(
        events=[_event_to_response(r) for r in rows],
        total=len(rows),
    )


# --------------------------------------------------------------------------- #
# Stop                                                                         #
# --------------------------------------------------------------------------- #
@router.post(
    "/{job_id}/stop",
    response_model=JobStopResponse,
    responses={404: {"description": "Job not found."}},
    summary="Stop a running detection job",
)
async def stop_job(
    job_id: UUID,
    manager: JobManager = Depends(get_job_manager),
) -> JobStopResponse:
    try:
        job = manager.stop_job(job_id)
    except JobNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found.",
        ) from None
    return JobStopResponse(
        id=job.id,
        status=job.status,
        total_count=job.total_count,
        total_last_reported=job.total_last_reported,
    )


# --------------------------------------------------------------------------- #
# Delete                                                                       #
# --------------------------------------------------------------------------- #
@router.delete(
    "/{job_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={404: {"description": "Job not found."}},
    summary="Stop and remove a detection job",
)
async def delete_job(
    job_id: UUID,
    manager: JobManager = Depends(get_job_manager),
) -> Response:
    try:
        manager.delete_job(job_id)
    except JobNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found.",
        ) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = ["router"]
