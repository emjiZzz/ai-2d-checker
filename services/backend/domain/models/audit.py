from datetime import datetime

from beanie import Document
from pydantic import Field


class AuditResult(Document):
    drawing_id: str
    violations: list[dict] = Field(default_factory=list)
    compliance_score: float
    ai_response_path: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "audit_results"
