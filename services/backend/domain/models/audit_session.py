from datetime import datetime
from typing import Any, Dict, Optional
from beanie import Document
from pydantic import Field
from pymongo import IndexModel, ASCENDING, DESCENDING

class AuditSession(Document):
    drawing_id: str = Field(..., description="Reference ID of the audited DrawingDocument")
    standard_id: str = Field(..., description="Reference ID of the grounding StandardDocument")
    status: str = Field("queued", description="Active pipeline status: queued, processing, completed, failed")
    compliance_score: Optional[float] = Field(None, description="Computed compliance score (0-100) where 100 is fully compliant")
    confidence_score: Optional[float] = Field(None, description="Aggregated confidence metric (0.0 - 1.0) of standard match accuracy")
    error_message: Optional[str] = Field(None, description="Detailed trace on pipeline failure")
    timings: Dict[str, float] = Field(default_factory=dict, description="Step durations: rule_engine_seconds, ai_engine_seconds, total_seconds")
    diagnostics: Dict[str, Any] = Field(default_factory=dict, description="Timings, confidence metrics, and processing logs")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = Field(None, description="Timestamp when worker popped the job")
    completed_at: Optional[datetime] = Field(None, description="Timestamp when pipeline completed or failed")

    class Settings:
        name = "audit_sessions"
        indexes = [
            IndexModel([("drawing_id", ASCENDING)]),
            IndexModel([("standard_id", ASCENDING)]),
            IndexModel([("status", ASCENDING)]),
            IndexModel([("confidence_score", DESCENDING)]),
            IndexModel([("created_at", DESCENDING)])
        ]
