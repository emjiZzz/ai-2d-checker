"""Ground-truth capture: an engineer's manual check of a drawing pair.

## What this router does not do

It does not run, call, or influence the comparison engine, and it does not feed the learned
model. Markings land in their own collections and stop there. How they later become training
rows is a decision worth making with data in hand — see `domain/models/ground_truth.py` on why
the schema is a superset, so making it later costs no re-labelling.

## Why markings save one at a time

A session on a dense sheet is an hour of work (`M745230A01` carries 68 addressable rows). A
submit-shaped API loses all of it to one crash or one closed laptop, and an annotator who has
lost an hour does not come back. `submit` therefore *finalises* a session; it is not the point
at which the data first exists.

## Where category validation lives

`domain/` may not import `infrastructure/` (`tests/test_layer_boundaries.py`), so
`GroundTruthMarking.category` is a plain `str` and the real check happens here, against
`taxonomy.Category` itself rather than a hand-copied list. `tests/test_ground_truth_submission.py`
pins that this stays true.
"""

from datetime import UTC, datetime
from typing import Annotated, Literal, get_args

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field

from ...domain.models.drawing_document import DrawingDocument
from ...domain.models.ground_truth import (
    EntityAddress,
    GroundTruthMarking,
    ManualCheckSession,
    MarkingStatus,
)
from ...infrastructure.audit.comparison.taxonomy import Category
from ...infrastructure.cad.coordinate_stamp import stamp_pair
from ...logger import logger
from ..dependencies import get_auth_token, get_or_404, resolve_username
from ..schemas import StandardResponse

router = APIRouter()

#: The six canonical categories, read off `taxonomy.Category` rather than restated. A literal
#: list here would be a second opinion about what a category is, and it would drift silently —
#: a marking filed under a category the engine does not know is not a corrupt row, it is an
#: invisible one.
VALID_CATEGORIES: frozenset[str] = frozenset(get_args(Category))


# ── wire models ──────────────────────────────────────────────────────────────────────
# Fixed fields throughout. No bare `dict` anywhere: hard constraint 1 is about
# `PhysicalComparisonResponse` specifically, but the reason (an open-ended object becomes
# open-ended `additionalProperties` in a generated schema) is not specific to it.


class EntityAddressPayload(BaseModel):
    """One clicked entity, as the client saw it.

    The client sends a bare `[x, y]`; the server stamps the coordinate space, layout, viewport
    index and render-bounds snapshot, because it owns the DrawingDocument and the client does
    not. Same division of labour as annotation pins.
    """

    drawing_id: str
    handle: str | None = None
    parent_handle: str | None = None
    entity_type: str
    layer: str = "0"
    text: str = ""
    coordinates: list[float] | None = Field(
        None, description="Bare [x, y] in drawing units; stamped server-side into a CadPoint"
    )


class CreateSessionRequest(BaseModel):
    room_id: str
    ref_drawing_id: str
    rev_drawing_id: str
    notes: str = ""


class CreateMarkingRequest(BaseModel):
    status: MarkingStatus
    category: str
    ref_address: EntityAddressPayload | None = None
    rev_address: EntityAddressPayload | None = None
    ref_text: str = ""
    rev_text: str = ""
    text_was_edited: bool = False
    is_bulk: bool = False
    notes: str = ""


class UpdateMarkingRequest(BaseModel):
    """Only the fields an engineer can revise after the fact.

    Neither address is editable: an address describes *which entity was clicked*, and changing
    it would silently convert a marking into a statement about something the annotator never
    looked at. Re-stamp instead.
    """

    status: MarkingStatus | None = None
    category: str | None = None
    ref_text: str | None = None
    rev_text: str | None = None
    text_was_edited: bool | None = None
    is_bulk: bool | None = None
    notes: str | None = None


class MarkingResponse(BaseModel):
    id: str
    session_id: str
    side: Literal["ref", "rev", "both"]
    status: str
    category: str
    ref_text: str
    rev_text: str
    text_was_edited: bool
    is_bulk: bool
    notes: str
    annotator: str
    ref_handle: str | None = None
    rev_handle: str | None = None
    ref_coordinates: list[float] | None = None
    rev_coordinates: list[float] | None = None
    created_at: datetime
    retracted_at: datetime | None = None


class SessionResponse(BaseModel):
    id: str
    room_id: str
    ref_drawing_id: str
    rev_drawing_id: str
    annotator: str
    status: str
    notes: str
    marking_count: int
    started_at: datetime
    submitted_at: datetime | None = None


# ── helpers ──────────────────────────────────────────────────────────────────────────


def _require_category(value: str) -> str:
    if value not in VALID_CATEGORIES:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Unknown category {value!r}. Categories must come from taxonomy.py, never be "
                f"invented. Valid: {sorted(VALID_CATEGORIES)}"
            ),
        )
    return value


async def _to_address(payload: EntityAddressPayload | None) -> EntityAddress | None:
    """Build a durable address, stamping the coordinate against its own drawing.

    Loads the DrawingDocument to capture `source_file_hash` and the render-bounds snapshot. A
    missing drawing is tolerated — the address is simply less recoverable, which is honest —
    rather than failing a stamp the engineer already made.
    """
    if payload is None:
        return None

    drawing = None
    try:
        drawing = await DrawingDocument.get(payload.drawing_id)
    except Exception as exc:
        logger.debug(f"[ground_truth] could not load drawing {payload.drawing_id}: {exc}")

    metadata = (getattr(drawing, "metadata", None) or {}) if drawing else {}

    return EntityAddress(
        drawing_id=payload.drawing_id,
        handle=payload.handle,
        parent_handle=payload.parent_handle,
        entity_type=payload.entity_type,
        layer=payload.layer,
        text=payload.text,
        point=stamp_pair(payload.coordinates, drawing),
        # The source DXF's hash. Unlike every entity id, this survives re-extraction, so it is
        # what proves a re-resolved address is still pointing into the same drawing.
        source_file_hash=(getattr(drawing, "file_hash", None) or metadata.get("file_hash")),
        extraction_schema_version=getattr(drawing, "extraction_schema_version", None),
    )


def _side_of(marking: GroundTruthMarking) -> str:
    if marking.ref_address and marking.rev_address:
        return "both"
    return "ref" if marking.ref_address else "rev"


def _marking_response(m: GroundTruthMarking) -> MarkingResponse:
    return MarkingResponse(
        id=str(m.id),
        session_id=m.session_id,
        side=m.side,
        status=m.status,
        category=m.category,
        ref_text=m.ref_text,
        rev_text=m.rev_text,
        text_was_edited=m.text_was_edited,
        is_bulk=m.is_bulk,
        notes=m.notes,
        annotator=m.annotator,
        ref_handle=m.ref_address.handle if m.ref_address else None,
        rev_handle=m.rev_address.handle if m.rev_address else None,
        ref_coordinates=(
            m.ref_address.point.as_pair() if m.ref_address and m.ref_address.point else None
        ),
        rev_coordinates=(
            m.rev_address.point.as_pair() if m.rev_address and m.rev_address.point else None
        ),
        created_at=m.created_at,
        retracted_at=m.retracted_at,
    )


def _session_response(s: ManualCheckSession) -> SessionResponse:
    return SessionResponse(
        id=str(s.id),
        room_id=s.room_id,
        ref_drawing_id=s.ref_drawing_id,
        rev_drawing_id=s.rev_drawing_id,
        annotator=s.annotator,
        status=s.status,
        notes=s.notes,
        marking_count=s.marking_count,
        started_at=s.started_at,
        submitted_at=s.submitted_at,
    )


async def _recount(session: ManualCheckSession) -> None:
    """Recompute `marking_count` from the live rows rather than incrementing.

    A counter that is incremented on create and decremented on retract drifts the first time a
    write fails halfway. Counting is cheap here and cannot disagree with the data.
    """
    session.marking_count = await GroundTruthMarking.find(
        GroundTruthMarking.session_id == str(session.id),
        GroundTruthMarking.retracted_at == None,  # noqa: E711 — Beanie builds a query, not a bool
    ).count()
    await session.save()


# ── routes ───────────────────────────────────────────────────────────────────────────


@router.post(
    "/ground-truth/sessions",
    response_model=StandardResponse[SessionResponse],
    summary="Open a manual engineer check over a reference/revision pair",
    dependencies=[Depends(get_auth_token)],
)
async def create_session(
    payload: CreateSessionRequest,
    x_session_token: Annotated[str | None, Header(alias="X-Session-Token")] = None,
):
    session = ManualCheckSession(
        room_id=payload.room_id,
        ref_drawing_id=payload.ref_drawing_id,
        rev_drawing_id=payload.rev_drawing_id,
        annotator=resolve_username(x_session_token) or "unknown",
        notes=payload.notes,
    )
    await session.save()
    logger.info(
        f"[ground_truth] Manual check opened: session {session.id} on room {session.room_id} "
        f"by {session.annotator}"
    )
    return StandardResponse(success=True, data=_session_response(session))


@router.get(
    "/ground-truth/sessions",
    response_model=StandardResponse[list[SessionResponse]],
    summary="List manual check sessions",
    dependencies=[Depends(get_auth_token)],
)
async def list_sessions(room_id: str | None = Query(None)):
    query = (
        ManualCheckSession.find(ManualCheckSession.room_id == room_id)
        if room_id
        else ManualCheckSession.find_all()
    )
    sessions = await query.sort(-ManualCheckSession.started_at).to_list()
    return StandardResponse(success=True, data=[_session_response(s) for s in sessions])


@router.get(
    "/ground-truth/sessions/{session_id}/markings",
    response_model=StandardResponse[list[MarkingResponse]],
    summary="Every marking in a session",
    dependencies=[Depends(get_auth_token)],
)
async def list_markings(session_id: str, include_retracted: bool = Query(False)):
    query = GroundTruthMarking.find(GroundTruthMarking.session_id == session_id)
    markings = await query.sort(+GroundTruthMarking.created_at).to_list()
    if not include_retracted:
        markings = [m for m in markings if m.retracted_at is None]
    return StandardResponse(success=True, data=[_marking_response(m) for m in markings])


@router.post(
    "/ground-truth/sessions/{session_id}/markings",
    response_model=StandardResponse[MarkingResponse],
    summary="Record one engineer decision",
    dependencies=[Depends(get_auth_token)],
)
async def create_marking(
    session_id: str,
    payload: CreateMarkingRequest,
    x_session_token: Annotated[str | None, Header(alias="X-Session-Token")] = None,
):
    session = await get_or_404(
        ManualCheckSession, session_id, f"Manual check session not found: {session_id}"
    )
    _require_category(payload.category)

    if payload.ref_address is None and payload.rev_address is None:
        # The failure this whole feature exists to avoid. The marker already in the product
        # (`CanvasContextMenu` -> `custom_marker_*`) records that a human pointed at a place and
        # nothing about what they saw there, which is why nothing can learn from it. A marking
        # with no entity is that same empty record, and it is cheaper to refuse than to store.
        raise HTTPException(
            status_code=422,
            detail=(
                "A marking must address at least one entity. A stamp that resolved to no entity "
                "records that someone pointed somewhere, which is not usable as ground truth."
            ),
        )

    marking = GroundTruthMarking(
        session_id=session_id,
        side="rev",  # replaced below, once both addresses are known
        ref_address=await _to_address(payload.ref_address),
        rev_address=await _to_address(payload.rev_address),
        status=payload.status,
        category=payload.category,
        ref_text=payload.ref_text,
        rev_text=payload.rev_text,
        text_was_edited=payload.text_was_edited,
        is_bulk=payload.is_bulk,
        notes=payload.notes,
        annotator=resolve_username(x_session_token) or session.annotator,
    )
    marking.side = _side_of(marking)
    await marking.save()
    await _recount(session)

    return StandardResponse(success=True, data=_marking_response(marking))


@router.patch(
    "/ground-truth/markings/{marking_id}",
    response_model=StandardResponse[MarkingResponse],
    summary="Revise a marking's judgement, not its address",
    dependencies=[Depends(get_auth_token)],
)
async def update_marking(marking_id: str, payload: UpdateMarkingRequest):
    marking = await get_or_404(
        GroundTruthMarking, marking_id, f"Marking not found: {marking_id}"
    )
    if payload.category is not None:
        _require_category(payload.category)

    for field, value in payload.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(marking, field, value)

    await marking.save()
    return StandardResponse(success=True, data=_marking_response(marking))


@router.delete(
    "/ground-truth/markings/{marking_id}",
    response_model=StandardResponse[MarkingResponse],
    summary="Retract a marking (marks it; never deletes)",
    dependencies=[Depends(get_auth_token)],
)
async def retract_marking(marking_id: str):
    """Retract rather than delete.

    This collection is both the dataset and the record of who asserted what. A row that
    silently vanishes is unauditable, and a retraction is itself information — it says a human
    changed their mind, which a later consumer may want to weigh differently from a decision
    that was never made. Same reasoning as `AuditFeedbackDocument.retracted_at`.
    """
    marking = await get_or_404(
        GroundTruthMarking, marking_id, f"Marking not found: {marking_id}"
    )
    if marking.retracted_at is None:
        marking.retracted_at = datetime.now(UTC)
        await marking.save()

        session = await ManualCheckSession.get(marking.session_id)
        if session:
            await _recount(session)

    return StandardResponse(success=True, data=_marking_response(marking))


@router.post(
    "/ground-truth/sessions/{session_id}/submit",
    response_model=StandardResponse[SessionResponse],
    summary="Finalise a manual check",
    dependencies=[Depends(get_auth_token)],
)
async def submit_session(session_id: str):
    """Close the session. The markings are already saved; this records that it is finished."""
    session = await get_or_404(
        ManualCheckSession, session_id, f"Manual check session not found: {session_id}"
    )
    await _recount(session)
    session.status = "submitted"
    session.submitted_at = datetime.now(UTC)
    await session.save()

    logger.info(
        f"[ground_truth] Manual check submitted: session {session.id}, "
        f"{session.marking_count} marking(s) by {session.annotator}"
    )
    return StandardResponse(success=True, data=_session_response(session))
