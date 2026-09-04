from datetime import datetime

from beanie import Document
from pydantic import Field, field_validator
from pymongo import ASCENDING, DESCENDING, IndexModel

from .cad_point import CadPoint, coerce_cad_point


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
    # A typed envelope rather than a bare [x, y]: a pin is user-authored and never
    # regenerated, so if the drawing is re-rendered against different bounds there is
    # otherwise nothing recording that the stored position has stopped meaning what it
    # meant. Stamped server-side by infrastructure/cad/coordinate_stamp.py.
    coordinates: CadPoint | None = Field(None, description="Pin centre with coordinate-space provenance")
    target_entity_ids: list[str] = Field(default_factory=list, description="List of ExtractedEntity IDs this annotates")
    
    # Context
    violation_id: str | None = Field(None, description="Optional link to a generated AuditViolation")
    status: str = Field(default="open", description="open, resolved, dismissed")
    pen_type: str = Field("checker_blue", description="Virtual pen color: checker_blue, resolved_pink")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    @field_validator("coordinates", mode="before")
    @classmethod
    def _coerce_coordinates(cls, value: object) -> CadPoint | None:
        """Accept a bare [x, y] from any writer that bypasses the router's stamping.

        The router stamps full provenance; this is the safety net, not the main path.
        """
        return coerce_cad_point(value)

    class Settings:
        name = "annotations"
        indexes = [
            IndexModel([("review_session_id", ASCENDING)]),
            IndexModel([("drawing_id", ASCENDING)]),
            IndexModel([("status", ASCENDING)]),
            IndexModel([("created_at", DESCENDING)])
        ]
