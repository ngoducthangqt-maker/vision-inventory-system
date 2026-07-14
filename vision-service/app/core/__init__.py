"""Core building blocks: YOLO11 detector and OpenCV video source."""

from app.core.detector import Detection, ObjectDetector
from app.core.source import VideoSource, VideoSourceError

__all__ = ["ObjectDetector", "Detection", "VideoSource", "VideoSourceError"]
