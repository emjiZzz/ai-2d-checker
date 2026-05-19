from datetime import datetime
from beanie import Document
from pydantic import Field

class Standard(Document):
    name: str
    version: str
    file_path: str
    embedded: bool = False
    uploaded_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "standards"
