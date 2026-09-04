from datetime import datetime

from beanie import Document
from pydantic import Field


class Comparison(Document):
    original_id: str
    modified_id: str
    overlay_path: str
    diff_metadata: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "comparisons"
