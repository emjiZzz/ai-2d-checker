from datetime import datetime
from typing import Any, Dict, Optional
from beanie import Document
from pydantic import Field
from pymongo import IndexModel, ASCENDING

class StandardChunk(Document):
    standard_id: str = Field(..., description="Reference ID of the parent StandardDocument")
    standard_hash: str = Field(..., description="SHA-256 hash of the parent StandardDocument")
    chunk_index: int = Field(..., description="Sequential index of the chunk starting from 0")
    content: str = Field(..., description="Text segment contents of this standard chunk")
    section_header: Optional[str] = Field(None, description="Section header or title if resolved")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Chunk specific properties like page number, line spans")
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "standard_chunks"
        indexes = [
            IndexModel([("standard_id", ASCENDING)]),
            IndexModel([("standard_hash", ASCENDING)]),
            IndexModel([("standard_id", ASCENDING), ("chunk_index", ASCENDING)], unique=True)
        ]
