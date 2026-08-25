"""Tests for the OpenCV-backed ``VideoSource`` using a stub ``cv2`` module."""

from __future__ import annotations

import sys
import types
from typing import Any

import pytest
from app.core.source import VideoSource, VideoSourceError
from app.schemas.job_schema import JobSourceType


class StubCapture:
    def __init__(self, source: Any, api: Any = None, *, opened: bool = True) -> None:
        self.source = source
        self.api = api
        self._opened = opened
        self.props: dict[int, float] = {}
        self.released = False
        self.frames = [(True, "frame-1"), (True, "frame-2"), (False, None)]

    def isOpened(self) -> bool:  # noqa: N802 - mirrors the cv2 API
        return self._opened

    def set(self, prop: int, value: float) -> None:
        self.props[prop] = value

    def get(self, prop: int) -> float:
        return {StubCv2.CAP_PROP_FPS: 25.0}.get(prop, 0.0)

    def read(self) -> tuple[bool, Any]:
        return self.frames.pop(0) if self.frames else (False, None)

    def release(self) -> None:
        self.released = True


class StubCv2:
    CAP_FFMPEG = 1900
    CAP_PROP_BUFFERSIZE = 38
    CAP_PROP_FPS = 5

    def __init__(self, *, opened: bool = True) -> None:
        self.opened = opened
        self.captures: list[StubCapture] = []

    def VideoCapture(self, source: Any, api: Any = None) -> StubCapture:  # noqa: N802
        capture = StubCapture(source, api, opened=self.opened)
        self.captures.append(capture)
        return capture


@pytest.fixture
def stub_cv2(monkeypatch) -> StubCv2:
    stub = StubCv2()
    monkeypatch.setattr(VideoSource, "_import_cv2", staticmethod(lambda: stub))
    return stub


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("rtsp://cam/stream", JobSourceType.rtsp),
        ("RTSP://CAM/STREAM", JobSourceType.rtsp),
        ("/videos/clip.mp4", JobSourceType.file),
    ],
)
def test_auto_source_type_inference(source, expected):
    assert VideoSource(source).source_type is expected


def test_explicit_source_type_is_kept():
    assert VideoSource("/clip.mp4", JobSourceType.rtsp).source_type is JobSourceType.rtsp
    assert VideoSource("/clip.mp4", "file").source_type is JobSourceType.file


def test_unknown_source_type_string_is_rejected():
    with pytest.raises(ValueError, match="Unknown source_type"):
        VideoSource("/clip.mp4", "webcam")


def test_open_rtsp_uses_ffmpeg_backend_and_small_buffer(stub_cv2):
    source = VideoSource("rtsp://cam/stream")
    source.open()
    capture = stub_cv2.captures[0]
    assert capture.api == StubCv2.CAP_FFMPEG
    assert capture.props == {StubCv2.CAP_PROP_BUFFERSIZE: 1}


def test_open_file_uses_default_backend(stub_cv2):
    VideoSource("/videos/clip.mp4").open()
    assert stub_cv2.captures[0].api is None


def test_open_raises_when_capture_cannot_be_opened(monkeypatch):
    stub = StubCv2(opened=False)
    monkeypatch.setattr(VideoSource, "_import_cv2", staticmethod(lambda: stub))
    with pytest.raises(VideoSourceError, match="Cannot open video source"):
        VideoSource("/missing.mp4").open()


def test_read_before_open_raises():
    with pytest.raises(VideoSourceError, match="not opened"):
        VideoSource("/clip.mp4").read()


def test_read_returns_frames_then_eof(stub_cv2):
    source = VideoSource("/clip.mp4")
    source.open()
    assert source.read() == (True, "frame-1")
    assert source.read() == (True, "frame-2")
    assert source.read() == (False, None)


def test_release_is_idempotent(stub_cv2):
    source = VideoSource("/clip.mp4")
    source.open()
    capture = stub_cv2.captures[0]
    source.release()
    source.release()
    assert capture.released is True
    assert source._cap is None  # noqa: SLF001


def test_fps_is_zero_before_open_and_reported_after(stub_cv2):
    source = VideoSource("/clip.mp4")
    assert source.fps == 0.0
    source.open()
    assert source.fps == 25.0


def test_context_manager_opens_and_releases(stub_cv2):
    with VideoSource("/clip.mp4") as source:
        assert source._cap is not None  # noqa: SLF001
    assert stub_cv2.captures[0].released is True


def test_import_cv2_raises_helpful_error_when_missing(monkeypatch):
    monkeypatch.setitem(sys.modules, "cv2", None)
    real_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __import__

    def fake_import(name: str, *args: Any, **kwargs: Any) -> types.ModuleType:
        if name == "cv2":
            raise ImportError("no cv2")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", fake_import)
    with pytest.raises(RuntimeError, match="OpenCV"):
        VideoSource._import_cv2()  # noqa: SLF001
