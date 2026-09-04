from datetime import datetime
from typing import Any

from beanie import Document
from pydantic import Field
from pymongo import ASCENDING, DESCENDING, IndexModel


class ReviewSession(Document):
    """
    State container for an active or past engineering review workspace.
    Groups annotations, compared drawings, and view states.
    """
    title: str = Field(..., description="Human-readable title for this review session")
    primary_drawing_id: str = Field(..., description="The main DrawingDocument being reviewed")
    comparison_drawing_id: str | None = Field(None, description="Optional baseline DrawingDocument for diffing")
    audit_session_id: str | None = Field(None, description="Optional linked AuditSession for violation overlays")
    
    reviewer_id: str = Field(..., description="Local user token/identifier")
    status: str = Field(default="in_progress", description="in_progress, completed, archived")
    
    # Store viewport state so the user can return exactly where they left off
    last_viewport_state: dict[str, Any] = Field(
        default_factory=dict, 
        description="Persisted camera state {x, y, zoom, active_layers}"
    )
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "review_sessions"
        indexes = [
            IndexModel([("primary_drawing_id", ASCENDING)]),
            IndexModel([("reviewer_id", ASCENDING)]),
            IndexModel([("status", ASCENDING)]),
            IndexModel([("updated_at", DESCENDING)])
        ]
