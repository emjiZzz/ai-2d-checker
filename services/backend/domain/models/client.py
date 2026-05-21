from datetime import datetime
from beanie import Document
from pydantic import Field
from pymongo import IndexModel, ASCENDING

class ClientDocument(Document):
    name: str = Field(..., description="Unique client name: e.g. KEMCO, AGCC, JFE, NIKKO, TEX")
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "clients"
        indexes = [
            IndexModel([("name", ASCENDING)], unique=True)
        ]
