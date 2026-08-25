"""Tests for the caller-supplied ``source`` / ``model_path`` validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.validation import (
    InvalidJobInputError,
    validate_model_path,
    validate_source,
)
from app.schemas.job_schema import JobSourceType


def _validate(source: str, media_dir: Path, source_type: JobSourceType = JobSourceType.auto) -> str:
    return validate_source(
        source,
        source_type,
        allowed_media_dirs=[str(media_dir)],
        allow_demo_sources=True,
    )


def test_rtsp_and_demo_sources_are_accepted(tmp_path: Path) -> None:
    assert _validate("rtsp://cam.local:554/stream", tmp_path) == "rtsp://cam.local:554/stream"
    assert _validate("demo://warehouse", tmp_path) == "demo://warehouse"


def test_allowed_local_video_is_accepted(tmp_path: Path) -> None:
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"")
    assert _validate(str(video), tmp_path) == str(video)


@pytest.mark.parametrize(
    "source",
    [
        "http://169.254.169.254/latest/meta-data",  # SSRF into cloud metadata
        "file:///etc/passwd",
        "/etc/passwd",
        "../../etc/passwd",
        "v4l2src ! videoconvert ! appsink",  # GStreamer pipeline
        "",
    ],
)
def test_disallowed_sources_are_rejected(source: str, tmp_path: Path) -> None:
    with pytest.raises(InvalidJobInputError):
        _validate(source, tmp_path)


def test_demo_sources_can_be_disabled(tmp_path: Path) -> None:
    with pytest.raises(InvalidJobInputError):
        validate_source(
            "demo://warehouse",
            JobSourceType.auto,
            allowed_media_dirs=[str(tmp_path)],
            allow_demo_sources=False,
        )


def test_official_weight_names_are_accepted(tmp_path: Path) -> None:
    assert validate_model_path("yolo11n.pt", allowed_model_dir=str(tmp_path)) == "yolo11n.pt"


def test_local_weight_inside_allowed_dir_is_accepted(tmp_path: Path) -> None:
    weights = tmp_path / "best.pt"
    weights.write_bytes(b"")
    assert validate_model_path(str(weights), allowed_model_dir=str(tmp_path)) == str(weights)


@pytest.mark.parametrize(
    "model_path",
    [
        "https://evil.example/payload.pt",  # remote pickle -> code execution
        "../../../home/user/payload.pt",
        "/etc/passwd",
        "",
    ],
)
def test_disallowed_model_paths_are_rejected(model_path: str, tmp_path: Path) -> None:
    with pytest.raises(InvalidJobInputError):
        validate_model_path(model_path, allowed_model_dir=str(tmp_path))
