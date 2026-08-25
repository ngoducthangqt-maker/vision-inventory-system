"""Tests for the simulated detector / source used by demo jobs."""

from __future__ import annotations

import pytest
from app.core import simulated
from app.core.simulated import (
    SimulatedDetector,
    SimulatedSource,
    is_demo_source,
)


@pytest.fixture(autouse=True)
def no_pacing_sleep(monkeypatch):
    """Remove the demo pacing delay so tests stay fast."""
    monkeypatch.setattr(simulated.time, "sleep", lambda _seconds: None)


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("demo://cartons", True),
        ("DEMO://cartons", True),
        ("rtsp://cam/stream", False),
        ("/videos/clip.mp4", False),
    ],
)
def test_is_demo_source(source, expected):
    assert is_demo_source(source) is expected


def test_detector_accepts_the_real_detector_kwargs():
    detector = SimulatedDetector(
        model_path="yolo11n.pt", tracker_config="bytetrack.yaml", confidence_threshold=0.4
    )
    assert detector.detect_and_track(0)


def test_detector_returns_scripted_detections_for_valid_indices():
    detector = SimulatedDetector()
    first = detector.detect_and_track(0)
    assert [(d.class_name, d.track_id) for d in first] == [("carton", 1)]


@pytest.mark.parametrize("frame", [-1, 10_000, None, "0"])
def test_detector_returns_nothing_for_invalid_frames(frame):
    assert SimulatedDetector().detect_and_track(frame) == []


def test_source_yields_every_scripted_frame_then_eof():
    source = SimulatedSource("demo://x")
    source.open()
    indices = []
    while True:
        ok, frame = source.read()
        if not ok:
            break
        indices.append(frame)
    assert indices == list(range(len(simulated._DEMO_FRAMES)))  # noqa: SLF001
    assert source.read() == (False, None)


def test_release_stops_further_reads():
    source = SimulatedSource("demo://x")
    source.release()
    assert source.read() == (False, None)


def test_scripted_sequence_counts_unique_cartons_and_pallets():
    """Playing the whole script must yield 3 cartons and 3 pallets."""
    detector = SimulatedDetector()
    source = SimulatedSource("demo://x")
    seen: dict[int, str] = {}
    while True:
        ok, frame = source.read()
        if not ok:
            break
        for detection in detector.detect_and_track(frame):
            seen.setdefault(detection.track_id, detection.class_name)

    counts = {name: list(seen.values()).count(name) for name in set(seen.values())}
    assert counts == {"carton": 3, "pallet": 3}
