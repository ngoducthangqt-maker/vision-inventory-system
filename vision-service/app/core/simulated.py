"""Simulated detector + video source for demo / testing without a camera.

When a job's ``source`` starts with ``demo://`` the pipeline uses these
components instead of YOLO11 + OpenCV, so the full Camera -> YOLO ->
Inventory API -> Postgres flow can be exercised with zero ML dependencies
(no torch, no opencv, no RTSP camera).

The simulator plays a scripted sequence of frames in which cartons and
pallets (matching the job's target class names) appear over time, with stable
track IDs so the unique-counting logic is exercised exactly like the real
detector would.
"""

from __future__ import annotations

import time
from typing import Any

from app.core.detector import Detection


# A scripted "video" of ~24 frames. Track IDs are stable so each physical
# object is counted once. Class names match the default demo targets
# ("carton" and "pallet"); a "person" appears as ignored noise.
#
#   frame 1-2 : carton #1 appears
#   frame 3-4 : carton #2 appears (carton #1 still visible)
#   frame 5-6 : pallet #10 appears
#   frame 7-8 : carton #3 appears, pallet #11 appears
#   frame 9-10: pallet #12 appears
#   frame 11  : a "person" (noise) appears alongside
#   frame 12-24: everyone stays on screen (no new counts)
_DEMO_FRAMES: list[list[Detection]] = []
_DEMO_FRAMES.append([Detection("carton", 1, 0.92, [10, 10, 60, 60])])
_DEMO_FRAMES.append([Detection("carton", 1, 0.91, [12, 12, 62, 62])])
_DEMO_FRAMES.append([Detection("carton", 1, 0.90, [14, 14, 64, 64]), Detection("carton", 2, 0.85, [100, 10, 150, 60])])
_DEMO_FRAMES.append([Detection("carton", 1, 0.90, [16, 16, 66, 66]), Detection("carton", 2, 0.84, [102, 12, 152, 62])])
_DEMO_FRAMES.append([Detection("carton", 1, 0.89, [18, 18, 68, 68]), Detection("carton", 2, 0.83, [104, 14, 154, 64]), Detection("pallet", 10, 0.93, [10, 100, 160, 200])])
_DEMO_FRAMES.append([Detection("carton", 1, 0.88, [20, 20, 70, 70]), Detection("carton", 2, 0.82, [106, 16, 156, 66]), Detection("pallet", 10, 0.92, [12, 102, 162, 202])])
_DEMO_FRAMES.append([Detection("carton", 1, 0.87, [22, 22, 72, 72]), Detection("carton", 2, 0.81, [108, 18, 158, 68]), Detection("pallet", 10, 0.91, [14, 104, 164, 204]), Detection("carton", 3, 0.78, [200, 10, 250, 60]), Detection("pallet", 11, 0.88, [180, 100, 320, 200])])
_DEMO_FRAMES.append([Detection("carton", 1, 0.86, [24, 24, 74, 74]), Detection("carton", 2, 0.80, [110, 20, 160, 70]), Detection("pallet", 10, 0.90, [16, 106, 166, 206]), Detection("carton", 3, 0.77, [202, 12, 252, 62]), Detection("pallet", 11, 0.87, [182, 102, 322, 202])])
_DEMO_FRAMES.append([Detection("carton", 1, 0.85, [26, 26, 76, 76]), Detection("carton", 2, 0.79, [112, 22, 162, 72]), Detection("pallet", 10, 0.89, [18, 108, 168, 208]), Detection("carton", 3, 0.76, [204, 14, 254, 64]), Detection("pallet", 11, 0.86, [184, 104, 324, 204]), Detection("pallet", 12, 0.84, [340, 100, 480, 200])])
for _ in range(15):
    _DEMO_FRAMES.append(_DEMO_FRAMES[-1][:])  # hold final frame


class SimulatedDetector:
    """Drop-in replacement for ``ObjectDetector`` that returns scripted frames."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        # Accept the same kwargs as ObjectDetector so the pipeline can build
        # either transparently.
        pass

    def detect_and_track(self, frame: Any) -> list[Detection]:
        # ``frame`` is the index (int) produced by SimulatedSource.read().
        if isinstance(frame, int) and 0 <= frame < len(_DEMO_FRAMES):
            return _DEMO_FRAMES[frame]
        return []


class SimulatedSource:
    """Drop-in replacement for ``VideoSource`` playing the scripted sequence.

    ``read()`` sleeps briefly between frames so the job runs for several
    seconds (a realistic pacing for a live demo) and returns the frame index
    as the "frame" payload, which ``SimulatedDetector`` consumes.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self._i = 0

    def open(self) -> None:
        pass

    def read(self) -> tuple[bool, Any]:
        if self._i >= len(_DEMO_FRAMES):
            return False, None
        idx = self._i
        self._i += 1
        # Pace the demo so a job runs ~12s (24 frames * ~0.5s).
        time.sleep(0.5)
        return True, idx

    def release(self) -> None:
        self._i = len(_DEMO_FRAMES)


def is_demo_source(source: str) -> bool:
    """Return ``True`` when ``source`` selects the simulated demo pipeline."""
    return source.lower().startswith("demo://")


__all__ = [
    "SimulatedDetector",
    "SimulatedSource",
    "is_demo_source",
]
