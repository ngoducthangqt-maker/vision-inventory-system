"""OpenCV-backed video source supporting RTSP streams and video files.

OpenCV (``cv2``) is imported lazily so the rest of the service stays
importable in environments without OpenCV installed.
"""

from __future__ import annotations

from typing import Any

from app.schemas.job_schema import JobSourceType


class VideoSourceError(RuntimeError):
    """Raised when a video source cannot be opened."""


class VideoSource:
    """Thin wrapper around ``cv2.VideoCapture``."""

    def __init__(self, source: str, source_type: JobSourceType | str = JobSourceType.auto) -> None:
        self.source = source
        if isinstance(source_type, str) and source_type not in {e.value for e in JobSourceType}:
            raise ValueError(f"Unknown source_type: {source_type!r}")
        self.source_type = JobSourceType(source_type) if isinstance(source_type, str) else source_type
        if self.source_type is JobSourceType.auto:
            self.source_type = (
                JobSourceType.rtsp
                if source.lower().startswith("rtsp://")
                else JobSourceType.file
            )
        self._cap: Any | None = None

    # ------------------------------------------------------------------ #
    # Lifecycle                                                           #
    # ------------------------------------------------------------------ #
    def open(self) -> None:
        """Open the underlying ``VideoCapture``."""
        cv2 = self._import_cv2()
        if self.source_type is JobSourceType.rtsp:
            # FFMPEG backend with a tiny buffer reduces latency for live streams.
            cap = cv2.VideoCapture(self.source, cv2.CAP_FFMPEG)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        else:
            cap = cv2.VideoCapture(self.source)

        if not cap.isOpened():
            raise VideoSourceError(f"Cannot open video source: {self.source!r}")
        self._cap = cap

    def read(self) -> tuple[bool, Any]:
        """Read the next frame. Returns ``(False, None)`` on EOF / stream end."""
        if self._cap is None:
            raise VideoSourceError("VideoSource is not opened. Call open() first.")
        return self._cap.read()

    def release(self) -> None:
        """Release the underlying capture device."""
        if self._cap is not None:
            try:
                self._cap.release()
            finally:
                self._cap = None

    # ------------------------------------------------------------------ #
    # Properties                                                          #
    # ------------------------------------------------------------------ #
    @property
    def fps(self) -> float:
        """Best-effort frames-per-second reported by the capture device."""
        if self._cap is None:
            return 0.0
        cv2 = self._import_cv2()
        return float(self._cap.get(cv2.CAP_PROP_FPS) or 0.0)

    # ------------------------------------------------------------------ #
    # Helpers                                                             #
    # ------------------------------------------------------------------ #
    @staticmethod
    def _import_cv2() -> Any:
        try:
            import cv2  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise RuntimeError(
                "OpenCV (opencv-python) is required to read video sources. "
                "Install it with: pip install opencv-python"
            ) from exc
        return cv2

    def __enter__(self) -> VideoSource:
        self.open()
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.release()


__all__ = ["VideoSource", "VideoSourceError"]
