"""Tests for the YOLO11 detector wrapper, with a stubbed ultralytics module."""

from __future__ import annotations

import sys
import types
from typing import Any

import pytest
from app.core.detector import Detection, ObjectDetector


class StubTensor:
    def __init__(self, value: Any) -> None:
        self._value = value

    def item(self) -> Any:
        return self._value

    def tolist(self) -> Any:
        return self._value


class StubBoxes:
    def __init__(self, rows: list[tuple[int, float, list[float]]], *, with_ids: bool = True) -> None:
        self.cls = [StubTensor(row[0]) for row in rows]
        self.conf = [StubTensor(row[1]) for row in rows]
        self.xyxy = [StubTensor(row[2]) for row in rows]
        self.id = [StubTensor(100 + i) for i in range(len(rows))] if with_ids else None

    def __len__(self) -> int:
        return len(self.cls)


class StubResult:
    def __init__(self, boxes: StubBoxes | None) -> None:
        self.boxes = boxes


class StubYOLO:
    """Records constructor / track kwargs and returns scripted results."""

    instances: list[StubYOLO] = []
    results: list[StubResult] = []

    def __init__(self, model_path: str) -> None:
        self.model_path = model_path
        self.names = {0: "carton", 1: "pallet"}
        self.track_kwargs: dict[str, Any] = {}
        StubYOLO.instances.append(self)

    def track(self, frame: Any, **kwargs: Any) -> list[StubResult]:
        self.frame = frame
        self.track_kwargs = kwargs
        return StubYOLO.results


@pytest.fixture
def stub_ultralytics(monkeypatch):
    StubYOLO.instances = []
    StubYOLO.results = []
    module = types.ModuleType("ultralytics")
    module.YOLO = StubYOLO
    monkeypatch.setitem(sys.modules, "ultralytics", module)
    return StubYOLO


def test_detection_defaults():
    detection = Detection("carton", 1, 0.5)
    assert detection.bbox == []


def test_init_loads_model_and_class_names(stub_ultralytics):
    detector = ObjectDetector("weights/best.pt", tracker_config="botsort.yaml", confidence_threshold=0.5)
    assert detector.model_path == "weights/best.pt"
    assert detector.names == {0: "carton", 1: "pallet"}
    assert stub_ultralytics.instances[0].model_path == "weights/best.pt"


def test_detect_and_track_passes_tracking_options(stub_ultralytics):
    detector = ObjectDetector("m.pt", tracker_config="botsort.yaml", confidence_threshold=0.5)
    detector.detect_and_track("frame")
    kwargs = stub_ultralytics.instances[0].track_kwargs
    assert kwargs["persist"] is True
    assert kwargs["tracker"] == "botsort.yaml"
    assert kwargs["conf"] == 0.5
    assert kwargs["verbose"] is False


def test_detect_and_track_maps_boxes_to_detections(stub_ultralytics):
    stub_ultralytics.results = [
        StubResult(StubBoxes([(0, 0.9, [1.0, 2.0, 3.0, 4.0]), (1, 0.7, [5.0, 6.0, 7.0, 8.0])]))
    ]
    detections = ObjectDetector("m.pt").detect_and_track("frame")
    assert [(d.class_name, d.track_id, d.confidence) for d in detections] == [
        ("carton", 100, 0.9),
        ("pallet", 101, 0.7),
    ]
    assert detections[0].bbox == [1.0, 2.0, 3.0, 4.0]


def test_detect_and_track_handles_missing_track_ids(stub_ultralytics):
    stub_ultralytics.results = [StubResult(StubBoxes([(0, 0.9, [0, 0, 1, 1])], with_ids=False))]
    assert ObjectDetector("m.pt").detect_and_track("frame")[0].track_id is None


def test_detect_and_track_skips_results_without_boxes(stub_ultralytics):
    stub_ultralytics.results = [StubResult(None)]
    assert ObjectDetector("m.pt").detect_and_track("frame") == []


def test_unknown_class_id_falls_back_to_its_index(stub_ultralytics):
    stub_ultralytics.results = [StubResult(StubBoxes([(7, 0.6, [0, 0, 1, 1])]))]
    assert ObjectDetector("m.pt").detect_and_track("frame")[0].class_name == "7"
