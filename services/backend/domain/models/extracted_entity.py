from datetime import datetime
from typing import Any

from beanie import Document
from pydantic import Field
from pymongo import ASCENDING, IndexModel


class ExtractedEntity(Document):
    drawing_id: str = Field(..., description="Reference ID of the associated DrawingDocument")
    job_id: str = Field(..., description="Reference ID of the extraction pipeline job")
    entity_type: str = Field(..., description="Normalized CAD type: line, circle, arc, polyline, dimension, text, block, layer")
    layer: str = Field("0", description="Layer name the entity resides on")
    properties: dict[str, Any] = Field(default_factory=dict, description="CAD metadata properties (start, end, radius, text, etc.)")
    geometry: dict[str, Any] = Field(default_factory=dict, description="Coordinates, length, bounds, or vectors")
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "extracted_entities"
        indexes = [
            IndexModel([("drawing_id", ASCENDING)]),
            IndexModel([("job_id", ASCENDING)]),
            IndexModel([("entity_type", ASCENDING)]),
            IndexModel([("layer", ASCENDING)])
        ]
