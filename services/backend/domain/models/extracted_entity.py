from datetime import datetime
from typing import Any

from beanie import Document
from pydantic import Field
from pymongo import ASCENDING, IndexModel

# Bump when the shape of `properties` / `geometry` changes such that previously
# extracted rows can no longer be interpreted the same way. Stored on the parent
# DrawingDocument so stale extractions are detectable without re-reading entities.
EXTRACTION_SCHEMA_VERSION = 2


class ExtractedEntity(Document):
    drawing_id: str = Field(..., description="Reference ID of the associated DrawingDocument")
    job_id: str = Field(..., description="Reference ID of the extraction pipeline job")
    entity_type: str = Field(..., description="Normalized CAD type: line, circle, arc, polyline, dimension, text, block, layer")
    layer: str = Field("0", description="Layer name the entity resides on")

    # Promoted out of `properties` so they can be indexed. Entity-handle lookup is
    # the addressing scheme for AI-grounded findings and canvas hit-testing; scanning
    # a nested dict field for it does not scale.
    handle: str | None = Field(None, description="Source DXF entity handle, unique within the drawing")
    parent_handle: str | None = Field(None, description="Handle of the owning INSERT when this entity came from an exploded block")
    space: str = Field("model", description="Coordinate space of `geometry`: 'model' or 'paper'")
    viewport_index: int = Field(-1, description="Index into the drawing's viewport transform, or -1 for identity/no viewport")

    properties: dict[str, Any] = Field(default_factory=dict, description="CAD metadata properties (start, end, radius, text, etc.)")
    geometry: dict[str, Any] = Field(default_factory=dict, description="Coordinates, length, bounds, or vectors")
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "extracted_entities"
        indexes = [
            IndexModel([("drawing_id", ASCENDING)]),
            IndexModel([("job_id", ASCENDING)]),
            IndexModel([("entity_type", ASCENDING)]),
            IndexModel([("layer", ASCENDING)]),
            # Handle resolution is always scoped to one drawing.
            IndexModel([("drawing_id", ASCENDING), ("handle", ASCENDING)]),
            IndexModel([("drawing_id", ASCENDING), ("parent_handle", ASCENDING)]),
            # Layer/type filtering within a drawing backs the entity manifest and
            # the scene endpoint.
            IndexModel([("drawing_id", ASCENDING), ("entity_type", ASCENDING)]),
        ]
