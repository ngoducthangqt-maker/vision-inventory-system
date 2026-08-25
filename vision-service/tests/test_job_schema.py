"""Tests for the job-related Pydantic schemas."""

from __future__ import annotations

from uuid import uuid4

import pytest
from app.schemas.job_schema import (
    CountingTarget,
    JobCreateRequest,
    JobReportMode,
    JobSourceType,
)
from pydantic import ValidationError


def test_target_accepts_item_id_only():
    item_id = uuid4()
    target = CountingTarget(name="carton", class_names=["carton"], target_item_id=item_id)
    assert target.target_item_id == item_id
    assert target.report_mode is JobReportMode.restock


def test_target_accepts_sku_only():
    target = CountingTarget(name="pallet", class_names=["pallet"], target_sku="PALLET-001")
    assert target.target_sku == "PALLET-001"


def test_target_requires_a_destination():
    with pytest.raises(ValidationError, match="either 'target_item_id' or 'target_sku'"):
        CountingTarget(name="carton", class_names=["carton"])


def test_target_rejects_both_destinations():
    with pytest.raises(ValidationError, match="mutually exclusive"):
        CountingTarget(
            name="carton",
            class_names=["carton"],
            target_item_id=uuid4(),
            target_sku="CARTON-001",
        )


def test_target_requires_at_least_one_class_name():
    with pytest.raises(ValidationError):
        CountingTarget(name="carton", class_names=[], target_sku="S")


def _request_payload(**overrides):
    data = {
        "source": "rtsp://camera/stream",
        "targets": [{"name": "carton", "class_names": ["carton"], "target_sku": "CARTON-001"}],
    }
    data.update(overrides)
    return data


def test_request_defaults():
    request = JobCreateRequest(**_request_payload())
    assert request.source_type is JobSourceType.auto
    assert request.auto_start is True
    assert request.model_path is None
    assert request.frame_sample_interval is None
    assert request.report_interval_seconds is None


def test_request_rejects_duplicate_target_names():
    targets = [
        {"name": "carton", "class_names": ["carton"], "target_sku": "A"},
        {"name": "carton", "class_names": ["box"], "target_sku": "B"},
    ]
    with pytest.raises(ValidationError, match="must be unique"):
        JobCreateRequest(**_request_payload(targets=targets))


def test_request_allows_distinct_target_names():
    targets = [
        {"name": "carton", "class_names": ["carton"], "target_sku": "A"},
        {"name": "pallet", "class_names": ["pallet"], "target_sku": "B"},
    ]
    request = JobCreateRequest(**_request_payload(targets=targets))
    assert [t.name for t in request.targets] == ["carton", "pallet"]


@pytest.mark.parametrize(
    "overrides",
    [
        {"source": ""},
        {"targets": []},
        {"frame_sample_interval": 0},
        {"report_interval_seconds": 0.5},
        {"source_type": "webcam"},
    ],
)
def test_request_rejects_invalid_values(overrides):
    with pytest.raises(ValidationError):
        JobCreateRequest(**_request_payload(**overrides))
