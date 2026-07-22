from datetime import datetime
from typing import Any

from beanie import Document
from pydantic import Field
from pymongo import ASCENDING, IndexModel


class DrawingDocument(Document):
    file_name: str = Field(..., description="Original name of the uploaded drawing")
    file_path: str = Field(..., description="Normalized relative path within storage root")
    file_hash: str = Field(..., description="SHA-256 checksum of file content to prevent duplication")
    file_size_bytes: int = Field(..., description="File size in bytes")
    format: str = Field(..., description="File extension format ('dwg' or 'dxf')")
    status: str = Field("queued", description="Ingestion/extraction state: queued, processing, completed, failed")
    entity_counts: dict[str, int] = Field(default_factory=dict, description="Counts of lines, circles, dimensions, etc.")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Extracted structural drawing metadata")
    ai_summary: dict[str, Any] | None = Field(None, description="Detailed 6-view AI summary of the drawing")
    
    # --- PHASE 7.1: DrawingDocument Revision Chain fields ---
    part_number: str | None = Field(None, description="Extracted part number identifier")
    revision_letter: str | None = Field(None, description="Drawing revision index (e.g. A, B, C)")
    previous_revision_id: str | None = Field(None, description="Reference to previous revision DrawingDocument")
    is_latest_revision: bool = Field(True, description="True if this is the most current revision in system")

    created_at: datetime = Field(default_factory=datetime.utcnow, description="Record creation time")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="Record last update time")

    class Settings:
        name = "drawing_documents"
        indexes = [
            IndexModel([("file_hash", ASCENDING)], unique=True),
            IndexModel([("created_at", ASCENDING)]),
            IndexModel([("status", ASCENDING)]),
            IndexModel([("part_number", ASCENDING)]),
            IndexModel([("is_latest_revision", ASCENDING)])
        ]
