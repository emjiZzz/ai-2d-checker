from datetime import datetime

from beanie import Document
from pydantic import Field
from pymongo import ASCENDING, IndexModel


class OverlayRegion(Document):
    """
    Represents a geometric bounding box, polygon, or mask rendered over the DXF canvas
    to highlight critical zones, missing parts, or complex violations.
    """
    review_session_id: str = Field(..., description="Reference ID to the active ReviewSession")
    drawing_id: str = Field(..., description="Reference to the underlying DrawingDocument")
    
    label: str = Field(..., description="Short tag or label for the region")
    shape_type: str = Field(default="rectangle", description="rectangle, polygon, circle")
    
    # Coordinates defining the region (e.g. [[x1, y1], [x2, y2]] for rect)
    points: list[list[float]] = Field(..., description="Vertices defining the boundary")
    
    color_hex: str = Field(default="#FF0000", description="Highlight overlay color")
    opacity: float = Field(default=0.3, description="Fill opacity level")
    
    associated_annotation_id: str | None = Field(None, description="Linked annotation if any")
    
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "overlay_regions"
        indexes = [
            IndexModel([("review_session_id", ASCENDING)]),
            IndexModel([("drawing_id", ASCENDING)])
        ]
