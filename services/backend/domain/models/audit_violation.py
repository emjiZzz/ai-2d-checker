from datetime import datetime
from typing import Any

from beanie import Document
from pydantic import Field
from pymongo import ASCENDING, DESCENDING, IndexModel


class AuditViolation(Document):
    audit_session_id: str = Field(..., description="Reference ID of the associated AuditSession")
    severity: str = Field(..., description="Severity level: critical, high, medium, low")
    category: str = Field(..., description="Normalized violation category: missing_dimension, invalid_layer, empty_title_block, etc.")
    description: str = Field(..., description="Detailed description of the violation")
    recommendation: str = Field(..., description="Actionable recommendation to resolve the violation")
    affected_entities: list[dict[str, Any]] = Field(default_factory=list, description="List of drawing entities affected by this violation")
    confidence: float = Field(default_factory=lambda: 1.0, description="Hallucination/matching confidence level from 0.0 to 1.0")
    source: str = Field(..., description="Violation detector source: rule_engine or gemini_vision")
    coordinates: list[list[float]] | None = Field(None, description="Visual boundary coordinates: [[x1, y1], [x2, y2]] or coordinates of affected points")
    standard_reference: str | None = Field(None, description=" Grounding text or section identifier in the standard document")
    pen_type: str = Field("ai_red", description="Virtual pen color: ai_green, ai_red, checker_blue, resolved_green, resolved_pink")
    is_resolved: bool = Field(False, description="Whether the violation has been verified as resolved")
    resolved_at: datetime | None = Field(None, description="Timestamp when the violation was verified as resolved")
    checker_remarks: str | None = Field(None, description="Supervisor or checker feedback comment")
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "audit_violations"
        indexes = [
            IndexModel([("audit_session_id", ASCENDING)]),
            IndexModel([("severity", ASCENDING)]),
            IndexModel([("confidence", DESCENDING)]),
            IndexModel([("created_at", DESCENDING)])
        ]
