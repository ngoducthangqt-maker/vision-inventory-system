"""Validation of caller-supplied job inputs.

``source`` and ``model_path`` come straight from an HTTP payload and are
handed to OpenCV / Ultralytics, which happily open arbitrary local files,
network URLs and pickled weight files (arbitrary code execution). Both are
therefore restricted here:

* ``source``  -> ``demo://`` , ``rtsp(s)://`` with a host, or a regular file
  below one of ``ALLOWED_MEDIA_DIRS``.
* ``model_path`` -> an official Ultralytics weight name (auto-downloaded) or
  a ``.pt`` file below ``ALLOWED_MODEL_DIR``.
"""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse

from app.schemas.job_schema import JobSourceType

# Official Ultralytics weights, e.g. "yolo11n.pt" / "yolo11x-seg.pt".
_OFFICIAL_WEIGHT_RE = re.compile(r"^yolo(?:11|v8)[nsmlx](?:-[a-z]+)?\.pt$")

_RTSP_SCHEMES = {"rtsp", "rtsps"}
_DEMO_SCHEME = "demo"


class InvalidJobInputError(ValueError):
    """Raised when a caller-supplied source or model path is not allowed."""


def _resolve_within(candidate: str, allowed_dirs: list[str]) -> Path:
    """Resolve ``candidate`` and ensure it stays inside ``allowed_dirs``."""
    if not allowed_dirs:
        raise InvalidJobInputError(
            "No allowed directory is configured for local file inputs."
        )
    path = Path(candidate).expanduser().resolve()
    for allowed in allowed_dirs:
        root = Path(allowed).expanduser().resolve()
        if path == root or root in path.parents:
            return path
    raise InvalidJobInputError(
        f"Path {candidate!r} is outside the allowed directories: "
        f"{', '.join(allowed_dirs)}."
    )


def validate_source(
    source: str,
    source_type: JobSourceType,
    *,
    allowed_media_dirs: list[str],
    allow_demo_sources: bool,
) -> str:
    """Return ``source`` when it is an allowed video source, else raise."""
    source = source.strip()
    if not source:
        raise InvalidJobInputError("source must not be empty.")

    scheme = urlparse(source).scheme.lower()

    if scheme == _DEMO_SCHEME:
        if not allow_demo_sources:
            raise InvalidJobInputError("demo:// sources are disabled.")
        if source_type is JobSourceType.file:
            raise InvalidJobInputError("demo:// sources cannot be of type 'file'.")
        return source

    if scheme in _RTSP_SCHEMES:
        if source_type is JobSourceType.file:
            raise InvalidJobInputError("An rtsp:// source cannot be of type 'file'.")
        if not urlparse(source).hostname:
            raise InvalidJobInputError("The rtsp:// source has no host.")
        return source

    if scheme:
        # http(s)://, file://, ftp://, and OpenCV/GStreamer pipeline strings
        # would let a caller read internal endpoints or local files.
        raise InvalidJobInputError(
            f"Unsupported source scheme {scheme!r}; expected rtsp://, rtsps:// "
            "or a local file path."
        )

    if source_type is JobSourceType.rtsp:
        raise InvalidJobInputError("source_type='rtsp' requires an rtsp:// URL.")

    path = _resolve_within(source, allowed_media_dirs)
    if not path.is_file():
        raise InvalidJobInputError(f"Video file {source!r} does not exist.")
    return str(path)


def validate_model_path(model_path: str, *, allowed_model_dir: str) -> str:
    """Return ``model_path`` when it is an allowed weight file, else raise."""
    model_path = model_path.strip()
    if not model_path:
        raise InvalidJobInputError("model_path must not be empty.")

    if _OFFICIAL_WEIGHT_RE.match(model_path):
        # Bare official weight name: Ultralytics downloads it from its own CDN.
        return model_path

    if urlparse(model_path).scheme:
        raise InvalidJobInputError(
            "model_path must be a local weight file, not a URL."
        )

    path = _resolve_within(model_path, [allowed_model_dir])
    if path.suffix != ".pt":
        raise InvalidJobInputError("model_path must point to a '.pt' weight file.")
    if not path.is_file():
        raise InvalidJobInputError(f"Model file {model_path!r} does not exist.")
    return str(path)


__all__ = ["InvalidJobInputError", "validate_source", "validate_model_path"]
