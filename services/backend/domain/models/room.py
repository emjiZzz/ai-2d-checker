from datetime import datetime
from typing import Literal


from beanie import Document
from pydantic import Field
from pymongo import ASCENDING, DESCENDING, IndexModel


class Room(Document):
    """
    A Room is an isolated container for a single comparison/testing session
    (Phase A, room-based workflow). Data isolation (linking specific drawings/
    audit sessions to a Room) is deliberately NOT modeled yet — see
    frontend-room-workflow-plan.md "Deferred" section. This is the container
    only; what it holds is a later phase.
    """
    name: str = Field(..., description="User-facing room label, e.g. 'Bracket Rev C vs Rev D'")
    description: str | None = Field(None, description="Optional free-text notes about this test session")
    client_name: str | None = Field(None, description="Optional associated client, for grounding/filtering later")
    created_by: str | None = Field(None, description="Username who created the room")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    last_opened_at: datetime | None = Field(None, description="Updated each time the room is opened")
    comparison_method: Literal["deterministic", "full_ai", "full_ai_vision"] = Field("deterministic", description="Method used for physical comparison in this room")
    

    # Per-room data isolation
    active_old_drawing_id: str | None = Field(None, description="ID of the old/reference drawing active in this room")
    active_new_drawing_id: str | None = Field(None, description="ID of the new/revised drawing active in this room")
    active_audit_session_id: str | None = Field(None, description="ID of the active audit session in this room")
    physical_comparison_results: str | None = Field(None, description="Cached AI physical comparison checklist results as JSON string")

    # Soft deletion, matching AuditSession's established convention in this codebase.
    is_deleted: bool = Field(False, description="Soft deletion flag")
    deleted_at: datetime | None = Field(None, description="Timestamp of deletion")
    deleted_by: str | None = Field(None, description="Username who deleted it")

    class Settings:
        name = "rooms"
        indexes = [
            IndexModel([("is_deleted", ASCENDING)]),
            IndexModel([("created_at", DESCENDING)]),
            IndexModel([("client_name", ASCENDING)]),
        ]
