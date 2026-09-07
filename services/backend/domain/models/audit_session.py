from datetime import datetime
from typing import Any

from beanie import Document
from pydantic import Field
from pymongo import ASCENDING, DESCENDING, IndexModel


class AuditSession(Document):
    drawing_id: str = Field(..., description="Reference ID of the audited DrawingDocument")
    reference_drawing_id: str | None = Field(None, description="Optional baseline reference Drawing ID")
    standard_id: str | None = Field(None, description="Reference ID of the grounding StandardDocument")
    client_name: str | None = Field(None, description="Name of the audited Client")
    status: str = Field("queued", description="Active pipeline status: queued, processing, completed, failed")
    compliance_score: float | None = Field(None, description="Computed compliance score (0-100) where 100 is fully compliant")
    confidence_score: float | None = Field(None, description="Aggregated confidence metric (0.0 - 1.0) of standard match accuracy")
    error_message: str | None = Field(None, description="Detailed trace on pipeline failure")
    timings: dict[str, float] = Field(default_factory=dict, description="Step durations: rule_engine_seconds, ai_engine_seconds, total_seconds")
    diagnostics: dict[str, Any] = Field(default_factory=dict, description="Timings, confidence metrics, and processing logs")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: datetime | None = Field(None, description="Timestamp when worker popped the job")
    completed_at: datetime | None = Field(None, description="Timestamp when pipeline completed or failed")
    remarks: str | None = Field(None, description="Custom auditor remarks or remarks log")
    username: str | None = Field(None, description="User who initiated the audit")
    is_deleted: bool = Field(False, description="Soft deletion flag")
    deleted_at: datetime | None = Field(None, description="Timestamp of deletion")
    deleted_by: str | None = Field(None, description="Username who deleted it")
    is_restored: bool = Field(False, description="Flag indicating if the session was restored from the trash")

    class Settings:
        name = "audit_sessions"
        indexes = [
            IndexModel([("drawing_id", ASCENDING)]),
            IndexModel([("standard_id", ASCENDING)]),
            IndexModel([("client_name", ASCENDING)]),
            IndexModel([("status", ASCENDING)]),
            IndexModel([("confidence_score", DESCENDING)]),
            IndexModel([("created_at", DESCENDING)])
        ]
