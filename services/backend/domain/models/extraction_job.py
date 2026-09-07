from datetime import datetime
from typing import Any

from beanie import Document
from pydantic import Field
from pymongo import ASCENDING, IndexModel


class ExtractionJob(Document):
    drawing_id: str = Field(..., description="Reference ID of the associated DrawingDocument")
    status: str = Field("queued", description="Job state: queued, processing, completed, failed")
    error_message: str | None = Field(None, description="Detailed error traceback if job failed")
    diagnostics: dict[str, Any] = Field(default_factory=dict, description="Pipeline metrics, logs, and durations")
    conversion_duration_seconds: float | None = Field(None, description="Time spent converting DWG to DXF")
    parsing_duration_seconds: float | None = Field(None, description="Time spent parsing DXF entities")
    total_duration_seconds: float | None = Field(None, description="Total pipeline execution time")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: datetime | None = Field(None)
    completed_at: datetime | None = Field(None)

    class Settings:
        name = "extraction_jobs"
        indexes = [
            IndexModel([("drawing_id", ASCENDING)]),
            IndexModel([("status", ASCENDING)]),
            IndexModel([("created_at", ASCENDING)])
        ]
