from datetime import datetime
from typing import Any

from beanie import Document
from pydantic import Field
from pymongo import ASCENDING, IndexModel


class StandardDocument(Document):
    name: str = Field(..., description="Name of the engineering standard document")
    file_path: str = Field(..., description="Relative sandboxed file path to the standard document")
    standard_hash: str = Field(..., description="SHA-256 hash checksum of the standard document")
    file_size_bytes: int = Field(..., description="File size in bytes")
    format: str = Field(..., description="File extension/format: pdf, txt, md")
    scope: str = Field("client_specific", description="Scope of standard: 'universal' or 'client_specific'")
    client_name: str | None = Field(None, description="Associated client name if scope is client_specific")
    category: str | None = Field(None, description="Category of the standard e.g., Dimensioning, Tolerancing, Welding")
    description: str | None = Field(None, description="Detailed description of the standard contents")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Arbitrary metadata from parsing")
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "standard_documents"
        indexes = [
            IndexModel([("standard_hash", ASCENDING)], unique=True),
            IndexModel([("scope", ASCENDING)]),
            IndexModel([("client_name", ASCENDING)]),
            IndexModel([("created_at", ASCENDING)])
        ]
