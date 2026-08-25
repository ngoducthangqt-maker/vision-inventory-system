"""Small helpers shared across the service layers.

These live here (rather than being redefined per module) because both
repositories, the job manager and the pipeline need the exact same time
source, target/job-state serialization and "ignore-but-log" persistence
semantics.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any
from uuid import UUID


def utcnow() -> datetime:
    """Timezone-aware current UTC timestamp."""
    return datetime.now(timezone.utc)


def target_to_dict(target: Any) -> dict[str, Any]:
    """Serialize a ``CountingTarget`` (pydantic) into a JSON-storable dict."""
    return {
        "name": target.name,
        "class_names": list(target.class_names),
        "target_item_id": str(target.target_item_id) if target.target_item_id else None,
        "target_sku": target.target_sku,
        "report_mode": target.report_mode.value
        if hasattr(target.report_mode, "value")
        else str(target.report_mode),
    }


def serialize_item_ids(item_ids: Mapping[str, UUID | None]) -> dict[str, str | None]:
    """Stringify resolved item ids so they can be stored as JSON."""
    return {k: (str(v) if v is not None else None) for k, v in item_ids.items()}


def present_values(**values: Any) -> dict[str, Any]:
    """Drop ``None`` entries so callers only update the fields they supplied."""
    return {k: v for k, v in values.items() if v is not None}


@contextmanager
def swallow_persistence_errors(logger: logging.Logger, message: str, *args: Any) -> Iterator[None]:
    """Log and suppress persistence failures so a worker thread keeps running."""
    try:
        yield
    except Exception:  # noqa: BLE001 - persistence must not kill the caller
        logger.exception(message, *args)


__all__ = [
    "utcnow",
    "target_to_dict",
    "serialize_item_ids",
    "present_values",
    "swallow_persistence_errors",
]
