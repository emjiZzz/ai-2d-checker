import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, status

from ...domain.models.room import Room
from ...infrastructure.storage import room_results_cache
from ...logger import logger
from ..dependencies import get_auth_token, get_or_404, resolve_username
from ..schemas import RoomCreateRequest, RoomResponse, StandardResponse, UpdateRoomRequest

router = APIRouter()


def _to_response(room: Room) -> RoomResponse:
    return RoomResponse(
        id=str(room.id),
        name=room.name,
        description=room.description,
        client_name=room.client_name,
        active_old_drawing_id=room.active_old_drawing_id,
        active_new_drawing_id=room.active_new_drawing_id,
        active_old_drawing_name=room.active_old_drawing_name,
        active_new_drawing_name=room.active_new_drawing_name,
        active_audit_session_id=room.active_audit_session_id,
        physical_comparison_results=json.loads(room.physical_comparison_results) if room.physical_comparison_results else None,
        zones_confirmed_for=room.zones_confirmed_for,
        comparison_method=room.comparison_method,
        room_mode=room.room_mode,
        created_by=room.created_by,
        created_at=room.created_at,
        updated_at=room.updated_at,
        last_opened_at=room.last_opened_at,
    )


@router.post(
    "/rooms",
    response_model=StandardResponse[RoomResponse],
    summary="Create a new testing Room",
    dependencies=[Depends(get_auth_token)],
)
async def create_room(
    payload: RoomCreateRequest,
    x_session_token: str | None = Header(None, alias="X-Session-Token"),
    x_engineer_name: str | None = Header(None, alias="X-Engineer-Name"),
):
    """
    Creates an isolated Room container for a comparison/testing session.
    Data isolation (linking drawings/audits to this room) is not implemented
    yet — see frontend-room-workflow-plan.md. This just creates the container.

    created_by is derived from the session token, never the request body, so
    ownership can't be spoofed. It stays nullable because rooms created before
    this (and any api-token-only caller) legitimately have no owner.
    """
    room = Room(
        name=payload.name,
        description=payload.description,
        client_name=payload.client_name,
        comparison_method=payload.comparison_method,
        room_mode=payload.room_mode,
        created_by=resolve_username(x_session_token, x_engineer_name),
    )
    await room.save()
    logger.info(f"Room created: {room.id} ('{room.name}') mode={room.room_mode} method={room.comparison_method}")
    return StandardResponse(success=True, data=_to_response(room))


@router.get(
    "/rooms",
    response_model=StandardResponse[list[RoomResponse]],
    summary="List all active (non-deleted) Rooms",
    dependencies=[Depends(get_auth_token)],
)
async def list_rooms(
    mine: bool = False,
    x_session_token: str | None = Header(None, alias="X-Session-Token"),
    x_engineer_name: str | None = Header(None, alias="X-Engineer-Name"),
):
    """
    Lists non-deleted Rooms.

    `mine=true` narrows to rooms the caller created. It is opt-in rather than
    the default because every room created before created_by was populated has
    created_by=None — defaulting to an owner filter would make those rooms
    silently vanish from the UI. Legacy ownerless rooms are included in the
    filtered view for the same reason: they'd otherwise be unreachable.
    """
    # `physical_comparison_results` is projected OUT, and the list is the only endpoint that
    # does this. It holds a whole comparison checklist as a JSON string — every finding and
    # every canvas marking — so listing 30 rooms shipped 398 KB and took 5.2 s against the
    # remote cluster (measured 2026-08-19), for a view that renders a room's name and status.
    # Dropping it takes the same call to ~90 ms.
    #
    # ⚠ It is projected at the DATABASE, not stripped afterwards, because the cost is the
    # bytes crossing the network and not the serialization — see
    # `infrastructure/storage/entity_cache.py` for the measurements behind that claim.
    #
    # ⚠ Every list row therefore reports `physical_comparison_results: null`, which is
    # indistinguishable from a room that has never been compared. No caller reads it off the
    # list today — `activeRoom` is populated from `GET /rooms/{id}` and from the PATCH
    # response, both of which carry the full field — and
    # `test_room_list_projection.py` pins that split so a future list consumer fails loudly
    # here instead of quietly rendering an empty checklist.
    query = {"is_deleted": False}
    docs = (
        await Room.get_pymongo_collection()
        .find(query, projection={"physical_comparison_results": 0})
        .sort("updated_at", -1)
        .to_list(None)
    )
    rooms = [Room.model_validate(d) for d in docs]

    if mine:
        username = resolve_username(x_session_token, x_engineer_name)
        if username:
            rooms = [r for r in rooms if r.created_by == username or r.created_by is None]

    return StandardResponse(success=True, data=[_to_response(r) for r in rooms])


@router.get(
    "/rooms/{room_id}",
    response_model=StandardResponse[RoomResponse],
    summary="Get a Room and mark it as opened",
    dependencies=[Depends(get_auth_token)],
)
async def get_room(room_id: str):
    # Fetched WITHOUT `physical_comparison_results`, which is served from disk below. That one
    # field is the whole cost of this endpoint: the same query is 0.043 s without it and 2.03 s
    # with it for room 228 (166 KB), and every room's latency is linear in its size. See
    # `infrastructure/storage/room_results_cache.py`.
    room = await get_or_404(
        Room, room_id, "Room not found.", projection={"physical_comparison_results": 0}
    )
    if room.is_deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Room not found.",
        )

    # Keyed on the `updated_at` just read, so this can only ever serve the payload that belongs
    # to the document in hand. `False` is a miss — distinct from `None`, a room with no results.
    cached = room_results_cache.load(room_id, room.updated_at)
    if cached is False:
        full = await Room.get_pymongo_collection().find_one(
            {"_id": room.id}, projection={"physical_comparison_results": 1}
        )
        room.physical_comparison_results = (full or {}).get("physical_comparison_results")
        room_results_cache.store(room_id, room.updated_at, room.physical_comparison_results)
    else:
        room.physical_comparison_results = cached

    # A raw `update_one`, not `room.set()` and not `room.save()`.
    #
    # `room.save()` rewrites the whole document, `physical_comparison_results` included, so it
    # pushed the entire checklist back over the wire to stamp a timestamp. `room.set()` fixed
    # only half of that: it *sends* one field, but Beanie's `Document.update` issues
    # `response_type=UpdateResponse.NEW_DOCUMENT` — a `find_one_and_update` returning the
    # document AFTER the write — and `merge_models` it back into `room`. So the checklist came
    # *back* instead, and stamping this timestamp cost 2.01 s of room 228's 4.53 s open
    # (measured 2026-08-19; the raw call is 0.041 s). Neither ODM helper can express "write
    # this and tell me nothing".
    #
    # The in-memory `room` is still updated, so the response reports the value just written
    # rather than the stale one that was read — which is all `merge_models` was buying here.
    room.last_opened_at = datetime.now(timezone.utc)
    await Room.get_pymongo_collection().update_one(
        {"_id": room.id}, {"$set": {"last_opened_at": room.last_opened_at}}
    )
    return StandardResponse(success=True, data=_to_response(room))


@router.patch(
    "/rooms/{room_id}",
    response_model=StandardResponse[RoomResponse],
    summary="Update a Room's active state",
    dependencies=[Depends(get_auth_token)],
)
async def update_room(room_id: str, payload: UpdateRoomRequest):
    room = await get_or_404(Room, room_id, "Room not found.")
    if room.is_deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Room not found.",
        )

    # exclude_unset: only touch fields the caller actually sent. The old
    # implementation unconditionally overwrote all four fields from the
    # payload, so any partial PATCH (e.g. a future rename-only update) would
    # null out active_old_drawing_id / active_new_drawing_id /
    # active_audit_session_id / physical_comparison_results as a side effect.
    updates = payload.model_dump(exclude_unset=True)
    if "physical_comparison_results" in updates:
        value = updates.pop("physical_comparison_results")
        room.physical_comparison_results = json.dumps(value) if value else None
    for field, value in updates.items():
        setattr(room, field, value)

    room.updated_at = datetime.now(timezone.utc)
    await room.save()

    # This is the only writer of `physical_comparison_results`, and it stamps `updated_at` on
    # the line above — which is what makes that pair a sound cache key. Warm the entry here
    # rather than leaving the next `GET` to miss: saving results and immediately reopening the
    # room is the common flow, and the miss costs the full 2 s refetch.
    room_results_cache.clear_for_room(room_id)
    room_results_cache.store(room_id, room.updated_at, room.physical_comparison_results)

    return StandardResponse(success=True, data=_to_response(room))


@router.delete(
    "/rooms/{room_id}",
    response_model=StandardResponse[dict],
    summary="Soft-delete a Room",
    dependencies=[Depends(get_auth_token)],
)
async def delete_room(room_id: str):
    room = await get_or_404(Room, room_id, "Room not found.")
    if room.is_deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Room not found.",
        )

    room.is_deleted = True
    room.deleted_at = datetime.now(timezone.utc)
    await room.save()
    room_results_cache.clear_for_room(room_id)

    # The room owns its drawings: hard-delete both slots (entities, jobs, files,
    # caches, records) so nothing dangles once the room is gone. The Room record
    # itself stays soft-deleted, matching AuditSession convention.
    from ...infrastructure.ingestion.drawing_ingestion_service import DrawingIngestionService
    for drawing_id in (room.active_old_drawing_id, room.active_new_drawing_id):
        if drawing_id:
            try:
                await DrawingIngestionService.purge_drawing(drawing_id)
            except Exception as e:
                logger.warning(f"Failed to purge drawing {drawing_id} on room {room_id} deletion: {e}")

    logger.info(f"Room soft-deleted and owned drawings purged: {room_id}")
    return StandardResponse(success=True, data={"deleted": True})
