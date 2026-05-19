from datetime import datetime
from typing import Any, Dict, Optional
from beanie import Document
from pydantic import Field
from pymongo import IndexModel, ASCENDING

class StandardDocument(Document):
    name: str = Field(..., description="Name of the engineering standard document")
    file_path: str = Field(..., description="Relative sandboxed file path to the standard document")
    standard_hash: str = Field(..., description="SHA-256 hash checksum of the standard document")
    file_size_bytes: int = Field(..., description="File size in bytes")
    format: str = Field(..., description="File extension/format: pdf, txt, md")
    category: Optional[str] = Field(None, description="Category of the standard e.g., Dimensioning, Tolerancing, Welding")
    description: Optional[str] = Field(None, description="Detailed description of the standard contents")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary metadata from parsing")
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "standard_documents"
        indexes = [
            IndexModel([("standard_hash", ASCENDING)], unique=True),
            IndexModel([("created_at", ASCENDING)])
        ]
