import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status

from ...domain.models.room import Room
from ...logger import logger
from ..dependencies import get_auth_token, get_or_404
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
        comparison_method=room.comparison_method,
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
async def create_room(payload: RoomCreateRequest):
    """
    Creates an isolated Room container for a comparison/testing session.
    Data isolation (linking drawings/audits to this room) is not implemented
    yet — see frontend-room-workflow-plan.md. This just creates the container.
    """
    room = Room(
        name=payload.name,
        description=payload.description,
        client_name=payload.client_name,
        comparison_method=payload.comparison_method,
    )
    await room.save()
    logger.info(f"Room created: {room.id} ('{room.name}') method={room.comparison_method}")
    return StandardResponse(success=True, data=_to_response(room))


@router.get(
    "/rooms",
    response_model=StandardResponse[list[RoomResponse]],
    summary="List all active (non-deleted) Rooms",
    dependencies=[Depends(get_auth_token)],
)
async def list_rooms():
    rooms = await Room.find(Room.is_deleted == False).sort(-Room.updated_at).to_list()  # noqa: E712
    return StandardResponse(success=True, data=[_to_response(r) for r in rooms])


@router.get(
    "/rooms/{room_id}",
    response_model=StandardResponse[RoomResponse],
    summary="Get a Room and mark it as opened",
    dependencies=[Depends(get_auth_token)],
)
async def get_room(room_id: str):
    room = await get_or_404(Room, room_id, "Room not found.")
    if room.is_deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Room not found.",
        )

    room.last_opened_at = datetime.now(timezone.utc)
    await room.save()
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
    
    # Invalidate cache for associated drawings to prevent stale comparison results
    from ...infrastructure.audit.comparison.cache_manager import ComparisonCacheManager
    if room.active_old_drawing_id:
        ComparisonCacheManager.clear_cache_for_drawing(room.active_old_drawing_id)
    if room.active_new_drawing_id:
        ComparisonCacheManager.clear_cache_for_drawing(room.active_new_drawing_id)
        
    logger.info(f"Room soft-deleted: {room_id}")
    return StandardResponse(success=True, data={"deleted": True})
