from datetime import datetime
from beanie import Document
from pydantic import Field

class Drawing(Document):
    file_path: str
    format: str
    hash: str
    metadata: dict = Field(default_factory=dict)
    upload_date: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "drawings"
