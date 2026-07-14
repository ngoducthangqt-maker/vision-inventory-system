"""Service layer: job management and the detection pipeline."""

from app.services.job import DetectionJob
from app.services.job_manager import JobManager, JobNotFoundError, get_job_manager
from app.services.pipeline import DetectionPipeline

__all__ = [
    "DetectionJob",
    "JobManager",
    "JobNotFoundError",
    "DetectionPipeline",
    "get_job_manager",
]
