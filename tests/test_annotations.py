"""
test_annotations.py — Validation tests for annotation requests and endpoints.
"""

import pytest
from pydantic import ValidationError
from services.backend.api.schemas import (
    CreateAnnotationRequest,
    UpdateAnnotationRequest,
)


def test_create_annotation_request_valid():
    req = CreateAnnotationRequest(
        review_session_id="session-123",
        drawing_id="drawing-456",
        content="Test review note",
        severity="critical",
        pen_type="alert_red",
        violation_id="violation-789",
    )
    assert req.severity == "critical"
    assert req.pen_type == "alert_red"
    assert req.violation_id == "violation-789"


def test_create_annotation_request_invalid_severity():
    with pytest.raises(ValidationError) as exc_info:
        CreateAnnotationRequest(
            review_session_id="session-123",
            drawing_id="drawing-456",
            content="Invalid severity note",
            severity="super_ultra_critical",  # invalid
        )
    assert "severity" in str(exc_info.value)


def test_create_annotation_request_invalid_pen_type():
    with pytest.raises(ValidationError) as exc_info:
        CreateAnnotationRequest(
            review_session_id="session-123",
            drawing_id="drawing-456",
            content="Invalid pen note",
            pen_type="neon_purple",  # invalid
        )
    assert "pen_type" in str(exc_info.value)


def test_update_annotation_request_valid():
    req = UpdateAnnotationRequest(
        content="Updated note content",
        severity="high",
        pen_type="warning_orange",
        status="resolved",
    )
    assert req.severity == "high"
    assert req.pen_type == "warning_orange"
    assert req.status == "resolved"


def test_update_annotation_request_invalid_severity():
    with pytest.raises(ValidationError) as exc_info:
        UpdateAnnotationRequest(severity="invalid_sev")
    assert "severity" in str(exc_info.value)
