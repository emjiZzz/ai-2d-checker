from datetime import datetime
from typing import Any

from beanie import Document
from pydantic import Field, field_validator
from pymongo import ASCENDING, DESCENDING, IndexModel

from .cad_point import CadPoint, coerce_cad_point_list


#: The two values `resolution_type` actually holds. Defined here because R1 made the field
#: readable for the first time — until then it had exactly one writer (`audits.py`) and **no
#: readers at all**, which is how its own description came to advertise `confirmed` /
#: `rejected_hallucination`, a pair nothing has ever written. The written spelling wins: it is
#: what is in the database, and inventing a migration to satisfy a docstring would be backwards.
RESOLUTION_APPROVED = "APPROVED"
RESOLUTION_REJECTED = "REJECTED"


class AuditViolation(Document):
    audit_session_id: str = Field(..., description="Reference ID of the associated AuditSession")
    severity: str = Field(..., description="Severity level: critical, high, medium, low")
    category: str = Field(..., description="Normalized violation category: missing_dimension, invalid_layer, empty_title_block, etc.")
    description: str = Field(..., description="Detailed description of the violation")
    recommendation: str = Field(..., description="Actionable recommendation to resolve the violation")
    affected_entities: list[dict[str, Any]] = Field(default_factory=list, description="List of drawing entities affected by this violation")
    confidence: float = Field(default_factory=lambda: 1.0, description="Hallucination/matching confidence level from 0.0 to 1.0")
    source: str = Field(..., description="Violation detector source: rule_engine or gemini_vision")
    # Typed envelope, same reasoning as AnnotationDocument.coordinates. Violations are
    # regenerated on each audit run, so drift self-heals here -- but Phase 5 writeback
    # needs the space/layout/viewport provenance to invert a finding back into the
    # source file's model space.
    coordinates: list[CadPoint] | None = Field(None, description="Affected point(s) with coordinate-space provenance")
    entity_handle: str | None = Field(None, description="Source CAD entity handle cited by AI")
    standard_reference: str | None = Field(None, description=" Grounding text or section identifier in the standard document")
    pen_type: str = Field("ai_red", description="Virtual pen color: ai_green, ai_red, checker_blue, resolved_green, resolved_pink")
    resolution_type: str | None = Field(None, description="Resolution classification: APPROVED or REJECTED (see RESOLUTION_APPROVED/RESOLUTION_REJECTED)")
    is_resolved: bool = Field(False, description="Whether the violation has been verified as resolved")
    resolved_at: datetime | None = Field(None, description="Timestamp when the violation was verified as resolved")
    checker_remarks: str | None = Field(None, description="Supervisor or checker feedback comment")
    created_at: datetime = Field(default_factory=datetime.utcnow)

    @field_validator("coordinates", mode="before")
    @classmethod
    def _coerce_coordinates(cls, value: object) -> list[CadPoint] | None:
        """Normalise the shapes the ~8 violation producers pass.

        They range from a single `[x, y]` (title_block_rules, row_extractor) to a list
        of pairs (layer_rules) to already-stamped CadPoints (persistence_handler).
        Coercing centrally keeps the stored type uniform without threading a
        DrawingDocument into rule engines that have no access to one.
        """
        return coerce_cad_point_list(value)

    class Settings:
        name = "audit_violations"
        indexes = [
            IndexModel([("audit_session_id", ASCENDING)]),
            IndexModel([("severity", ASCENDING)]),
            IndexModel([("confidence", DESCENDING)]),
            IndexModel([("created_at", DESCENDING)])
        ]
