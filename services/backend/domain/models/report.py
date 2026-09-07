from datetime import datetime

from beanie import Document
from pydantic import Field


class Report(Document):
    audit_id: str
    pdf_path: str
    format: str = "pdf"
    generated_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "reports"
