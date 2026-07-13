from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status

from ...domain.models.room import Room
from ...logger import logger
from ..dependencies import get_auth_token
from ..schemas import RoomCreateRequest, RoomResponse, StandardResponse, UpdateRoomRequest

router = APIRouter()


def _to_response(room: Room) -> RoomResponse:
    import json
    return RoomResponse(
        id=str(room.id),
        name=room.name,
        description=room.description,
        client_name=room.client_name,
        active_old_drawing_id=room.active_old_drawing_id,
        active_new_drawing_id=room.active_new_drawing_id,
        active_audit_session_id=room.active_audit_session_id,
        physical_comparison_results=json.loads(room.physical_comparison_results) if room.physical_comparison_results else None,
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
    )
    await room.save()
    logger.info(f"Room created: {room.id} ('{room.name}')")
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
    room = await Room.get(room_id)
    if not room or room.is_deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Room not found.",
        )

    room.last_opened_at = datetime.utcnow()
    await room.save()
    return StandardResponse(success=True, data=_to_response(room))


@router.patch(
    "/rooms/{room_id}",
    response_model=StandardResponse[RoomResponse],
    summary="Update a Room's active state",
    dependencies=[Depends(get_auth_token)],
)
async def update_room(room_id: str, payload: UpdateRoomRequest):
    print(f"DEBUG: PATCH room {room_id} payload: {payload.dict()}", flush=True)
    room = await Room.get(room_id)
    if not room or room.is_deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Room not found.",
        )

    room.active_old_drawing_id = payload.active_old_drawing_id
    room.active_new_drawing_id = payload.active_new_drawing_id
    room.active_audit_session_id = payload.active_audit_session_id
    import json
    room.physical_comparison_results = json.dumps(payload.physical_comparison_results) if payload.physical_comparison_results else None
    room.updated_at = datetime.utcnow()
    await room.save()
    
    return StandardResponse(success=True, data=_to_response(room))


@router.delete(
    "/rooms/{room_id}",
    response_model=StandardResponse[dict],
    summary="Soft-delete a Room",
    dependencies=[Depends(get_auth_token)],
)
async def delete_room(room_id: str):
    room = await Room.get(room_id)
    if not room or room.is_deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Room not found.",
        )

    room.is_deleted = True
    room.deleted_at = datetime.utcnow()
    await room.save()
    logger.info(f"Room soft-deleted: {room_id}")
    return StandardResponse(success=True, data={"deleted": True})
