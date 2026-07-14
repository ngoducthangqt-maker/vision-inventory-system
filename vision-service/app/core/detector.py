"""YOLO11-based object detector.

The heavy ``ultralytics`` / ``torch`` imports are performed lazily inside
``__init__`` so that the FastAPI application can start (and serve ``/health``,
``/docs``, etc.) even when the ML stack is not installed. Job execution will
surface a clear error message if the dependencies are missing.

This detector is **category-agnostic**: it returns every tracked detection
(class name + track id). Category matching (which classes count as a "carton"
or a "pallet") is the pipeline's responsibility, so a single detector can
serve jobs counting any combination of object types.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Detection:
    """A single tracked detection produced for one frame."""

    class_name: str
    track_id: int | None
    confidence: float
    bbox: list[float] = field(default_factory=list)  # [x1, y1, x2, y2]


class ObjectDetector:
    """Wraps an Ultralytics YOLO11 model for tracking.

    Returns *all* tracked detections; the caller decides which classes to
    count via ``class_name`` matching.
    """

    def __init__(
        self,
        model_path: str,
        *,
        tracker_config: str = "bytetrack.yaml",
        confidence_threshold: float = 0.35,
    ) -> None:
        try:
            from ultralytics import YOLO  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise RuntimeError(
                "The 'ultralytics' package is required for detection. "
                "Install it with: pip install ultralytics"
            ) from exc

        self._YOLO = YOLO  # noqa: N818 - kept for potential re-use / introspection
        self.model_path = model_path
        self.tracker_config = tracker_config
        self.confidence_threshold = confidence_threshold
        self.model = YOLO(model_path)
        self.names: dict[int, str] = {int(k): str(v) for k, v in self.model.names.items()}

    # ------------------------------------------------------------------ #
    # Inference                                                           #
    # ------------------------------------------------------------------ #
    def detect_and_track(self, frame: Any) -> list[Detection]:
        """Run tracking on ``frame`` and return all tracked detections.

        Uses ``model.track(..., persist=True)`` so tracker state persists
        across calls within the same job, enabling unique object counting
        via stable track IDs.
        """
        results = self.model.track(
            frame,
            persist=True,
            tracker=self.tracker_config,
            conf=self.confidence_threshold,
            verbose=False,
        )
        detections: list[Detection] = []
        for result in results:
            boxes = getattr(result, "boxes", None)
            if boxes is None:
                continue
            # ``boxes.id`` is None when tracking could not assign an id.
            track_ids = boxes.id
            for i in range(len(boxes)):
                cls_id = int(boxes.cls[i].item())
                cls_name = self.names.get(cls_id, str(cls_id))
                tid = int(track_ids[i].item()) if track_ids is not None else None
                conf = float(boxes.conf[i].item())
                xyxy = boxes.xyxy[i].tolist()
                detections.append(
                    Detection(
                        class_name=cls_name,
                        track_id=tid,
                        confidence=conf,
                        bbox=xyxy,
                    )
                )
        return detections


__all__ = ["ObjectDetector", "Detection"]
