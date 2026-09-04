from datetime import datetime
from typing import Literal


from beanie import Document
from pydantic import Field, field_validator

from .comparison_method import (
    DETERMINISTIC,
    ComparisonMethodName,
    normalize_comparison_method,
)
from .room_mode import AI_COMPARISON, RoomMode, normalize_room_mode
from pymongo import ASCENDING, DESCENDING, IndexModel


class Room(Document):
    """
    A Room is an isolated container for a single comparison/testing session.
    Per-room data isolation (active_old_drawing_id / active_new_drawing_id /
    active_audit_session_id / physical_comparison_results below) is
    implemented: AuditWorkspace.tsx syncs the workspace's live state into
    these fields on every change, so reopening a Room restores what was
    active in it. This went beyond frontend-room-workflow-plan.md's original
    Phase A scope, which deliberately deferred isolation — see
    _deprecated/README.md for the full history of that plan.
    """
    name: str = Field(..., description="User-facing room label, e.g. 'Bracket Rev C vs Rev D'")
    description: str | None = Field(None, description="Optional free-text notes about this test session")
    client_name: str | None = Field(None, description="Optional associated client, for grounding/filtering later")
    created_by: str | None = Field(None, description="Username who created the room")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    last_opened_at: datetime | None = Field(None, description="Updated each time the room is opened")
    # Only the deterministic method survives. `rag_ai`, `ai_vision` and `hybrid` were removed
    # (ADR-006); no live room used them — all 48 that did were already soft-deleted.
    # Retained as a one-value Literal rather than dropped so the field keeps its meaning in the
    # API and stays the place a second method would be declared.
    comparison_method: ComparisonMethodName = Field(DETERMINISTIC, description="Method used for physical comparison in this room")

    # What the room is FOR — orthogonal to which engine compares. A manual-check room compares
    # nothing; it collects human ground truth. Kept off `comparison_method` deliberately: that
    # field names an engine, and overloading it would resurrect the method picker ADR-006
    # removed. See room_mode.py.
    room_mode: RoomMode = Field(AI_COMPARISON, description="Whether this room is an AI comparison or a manual engineer check")

    # Rooms written before the rename say "rag". No migration was run, so this validator is
    # what makes those documents loadable — see comparison_method.py on why it is permanent.
    _normalize_method = field_validator("comparison_method", mode="before")(
        lambda v: normalize_comparison_method(v)
    )

    # Rooms written before `room_mode` existed have no such field; they were all AI comparison
    # rooms, which is the default. No migration — absent and default mean the same thing.
    _normalize_room_mode = field_validator("room_mode", mode="before")(
        lambda v: normalize_room_mode(v)
    )
    

    # Per-room data isolation
    active_old_drawing_id: str | None = Field(None, description="ID of the old/reference drawing active in this room")
    active_new_drawing_id: str | None = Field(None, description="ID of the new/revised drawing active in this room")
    active_old_drawing_name: str | None = Field(None, description="Name of the old/reference drawing active in this room")
    active_new_drawing_name: str | None = Field(None, description="Name of the new/revised drawing active in this room")
    active_audit_session_id: str | None = Field(None, description="ID of the active audit session in this room")
    physical_comparison_results: str | None = Field(None, description="Cached AI physical comparison checklist results as JSON string")
    zones_confirmed_for: str | None = Field(
        None,
        description=(
            "'{old_drawing_id}:{new_drawing_id}' of the pair whose zone boxes the user "
            "reviewed and confirmed. The workspace hides the comparison panel until this "
            "matches the currently loaded pair. Storing the pair rather than a boolean means "
            "swapping either drawing invalidates the confirmation on its own — zones aligned "
            "to one sheet say nothing about a different one."
        ),
    )

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
