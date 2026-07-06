from datetime import datetime

from beanie import Document
from pydantic import Field
from pymongo import ASCENDING, DESCENDING, IndexModel


class AnnotationDocument(Document):
    """
    Stores engineering review annotations, pins, and markups linked to a drawing or specific geometry.
    """
    review_session_id: str = Field(..., description="Reference ID to the active ReviewSession")
    drawing_id: str = Field(..., description="Reference to the underlying DrawingDocument")
    author_id: str = Field(..., description="Local username or reviewer token identifier")
    
    annotation_type: str = Field(..., description="Type of annotation: pin, region, geometry_link, note")
    content: str = Field(..., description="Text content of the annotation or markdown note")
    severity: str = Field(default="info", description="Severity tag: info, low, medium, high, critical")
    
    # Spatial linking
    coordinates: list[float] | None = Field(None, description="[x, y] center point for pins")
    target_entity_ids: list[str] = Field(default_factory=list, description="List of ExtractedEntity IDs this annotates")
    
    # Context
    violation_id: str | None = Field(None, description="Optional link to a generated AuditViolation")
    status: str = Field(default="open", description="open, resolved, dismissed")
    pen_type: str = Field("checker_blue", description="Virtual pen color: checker_blue, resolved_pink")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "annotations"
        indexes = [
            IndexModel([("review_session_id", ASCENDING)]),
            IndexModel([("drawing_id", ASCENDING)]),
            IndexModel([("status", ASCENDING)]),
            IndexModel([("created_at", DESCENDING)])
        ]
