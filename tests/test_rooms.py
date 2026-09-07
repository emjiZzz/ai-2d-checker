import uuid
from datetime import datetime, timedelta

import pytest
from unittest.mock import MagicMock

from services.backend.domain.models.room import Room


@pytest.fixture(autouse=True)
def mock_beanie_rooms(monkeypatch):
    """
    In-memory mock store for the Room Beanie document, following the same
    pattern used in test_phase4_audit_pipeline.py / test_phase3_cad_pipeline.py
    so this file runs fully offline with no real MongoDB connection.
    """
    monkeypatch.setattr(Room, "get_pymongo_collection", classmethod(lambda cls: MagicMock()))

    class MockField:
        def __init__(self, name):
            self.name = name

        def __eq__(self, other):
            class Comparison:
                def __init__(self, left, right):
                    self.left = left
                    self.right = right

            return Comparison(self, other)

        def __neg__(self):
            # Beanie's real ExpressionField supports unary "-" for descending
            # sort (e.g. .sort(-Room.updated_at)); the mocked sort() below
            # ignores the argument and sorts by the real instance attribute
            # instead, so this only needs to make the expression evaluable.
            return self

    Room.is_deleted = MockField("is_deleted")
    Room.updated_at = MockField("updated_at")

    mock_rooms: dict[str, Room] = {}

    async def mock_save(self):
        if not hasattr(self, "id") or self.id is None:
            self.id = uuid.uuid4().hex
        self.updated_at = datetime.utcnow()
        mock_rooms[str(self.id)] = self
        return self

    async def mock_get(cls, id):
        return mock_rooms.get(str(id))

    class MockFind:
        def __init__(self, query=None):
            self.query = query

        def sort(self, *args, **kwargs):
            return self

        async def to_list(self, *args, **kwargs):
            results = list(mock_rooms.values())
            # Honor an is_deleted == False filter if present; otherwise return all.
            if self.query is not None and getattr(self.query.left, "name", "") == "is_deleted":
                target = self.query.right
                results = [r for r in results if r.is_deleted == target]
            return sorted(results, key=lambda r: r.updated_at, reverse=True)

    def mock_find(cls, *args, **kwargs):
        query = args[0] if args else None
        return MockFind(query)

    monkeypatch.setattr(Room, "save", mock_save)
    monkeypatch.setattr(Room, "get", classmethod(mock_get))
    monkeypatch.setattr(Room, "find", classmethod(mock_find))

    return mock_rooms


@pytest.mark.asyncio
async def test_create_room_appears_in_list(mock_beanie_rooms):
    """
    A created room must be persisted and immediately visible via find().
    """
    room = Room(name="Bracket Rev C vs Rev D", client_name="KEMCO")
    await room.save()

    assert room.id is not None

    listed = await Room.find(Room.is_deleted == False).sort(-Room.updated_at).to_list()  # noqa: E712
    assert len(listed) == 1
    assert listed[0].name == "Bracket Rev C vs Rev D"
    assert listed[0].client_name == "KEMCO"


@pytest.mark.asyncio
async def test_get_room_updates_last_opened_at(mock_beanie_rooms):
    """
    Opening a room (via Room.get + save, mirroring the router's get_room handler)
    must update last_opened_at.
    """
    room = Room(name="Test Room")
    await room.save()
    assert room.last_opened_at is None

    fetched = await Room.get(room.id)
    fetched.last_opened_at = datetime.utcnow()
    await fetched.save()

    refetched = await Room.get(room.id)
    assert refetched.last_opened_at is not None


@pytest.mark.asyncio
async def test_soft_deleted_room_excluded_from_list(mock_beanie_rooms):
    """
    Soft-deleting a room must remove it from the active list without deleting
    the underlying document (matches AuditSession's soft-delete convention).
    """
    room = Room(name="Room To Delete")
    await room.save()

    room.is_deleted = True
    room.deleted_at = datetime.utcnow()
    await room.save()

    listed = await Room.find(Room.is_deleted == False).sort(-Room.updated_at).to_list()  # noqa: E712
    assert len(listed) == 0

    # The document itself still exists (soft delete, not gone).
    still_exists = await Room.get(room.id)
    assert still_exists is not None
    assert still_exists.is_deleted is True


@pytest.mark.asyncio
async def test_delete_room_purges_both_owned_drawings(mock_beanie_rooms, monkeypatch):
    """
    Room-owned model: deleting a room must hard-delete both drawings it owns
    (via the shared purge_drawing helper) while the Room record itself stays
    soft-deleted. Nothing dangles.
    """
    from services.backend.api.routers.rooms import delete_room
    from services.backend.infrastructure.ingestion.drawing_ingestion_service import DrawingIngestionService

    purged: list[str] = []

    async def fake_purge(cls, drawing_id):
        purged.append(drawing_id)

    monkeypatch.setattr(DrawingIngestionService, "purge_drawing", classmethod(fake_purge))

    room = Room(
        name="Bracket Room",
        active_old_drawing_id="old-drawing-1",
        active_new_drawing_id="new-drawing-2",
    )
    await room.save()

    result = await delete_room(str(room.id))

    assert result.success is True
    assert sorted(purged) == ["new-drawing-2", "old-drawing-1"]  # both slots hard-deleted

    stored = await Room.get(room.id)
    assert stored.is_deleted is True  # room record soft-deleted, not gone


@pytest.mark.asyncio
async def test_delete_room_without_drawings_purges_nothing(mock_beanie_rooms, monkeypatch):
    """A room holding no drawings deletes cleanly without calling purge_drawing."""
    from services.backend.api.routers.rooms import delete_room
    from services.backend.infrastructure.ingestion.drawing_ingestion_service import DrawingIngestionService

    purged: list[str] = []

    async def fake_purge(cls, drawing_id):
        purged.append(drawing_id)

    monkeypatch.setattr(DrawingIngestionService, "purge_drawing", classmethod(fake_purge))

    room = Room(name="Empty Room")
    await room.save()

    result = await delete_room(str(room.id))

    assert result.success is True
    assert purged == []


@pytest.mark.asyncio
async def test_list_sorted_by_updated_at_descending(mock_beanie_rooms):
    """
    Rooms must list most-recently-updated first.
    """
    older = Room(name="Older Room")
    await older.save()
    older.updated_at = datetime.utcnow() - timedelta(hours=1)
    mock_beanie_rooms[str(older.id)] = older

    newer = Room(name="Newer Room")
    await newer.save()

    listed = await Room.find(Room.is_deleted == False).sort(-Room.updated_at).to_list()  # noqa: E712
    assert [r.name for r in listed] == ["Newer Room", "Older Room"]


# ── Zone-review gate: Room.zones_confirmed_for ────────────────────────────────
#
# The 2D workspace hides the Comparison Results panel until the user has reviewed the zone
# boxes for the loaded drawing pair. That confirmation is persisted here. The field stores
# the PAIR rather than a boolean, so swapping either drawing invalidates it without any
# imperative clearing scattered across the upload handlers.


@pytest.mark.asyncio
async def test_new_room_defaults_to_unconfirmed(mock_beanie_rooms):
    room = Room(name="Fresh Room")
    await room.save()

    assert (await Room.get(room.id)).zones_confirmed_for is None


@pytest.mark.asyncio
async def test_legacy_room_document_without_the_field_defaults_to_none(mock_beanie_rooms):
    """Rooms created before this field existed must load, not raise.

    Backs the claim that no migration or backfill is needed: Mongo documents predating the
    field simply have no such key, and Pydantic supplies the default on parse.
    """
    legacy = Room(**{"name": "Legacy Room", "client_name": "KEMCO"})

    assert legacy.zones_confirmed_for is None


@pytest.mark.asyncio
async def test_confirmation_round_trips(mock_beanie_rooms):
    room = Room(name="Room")
    await room.save()

    pair = "6a66cab4fef0570aff55418c:6a66cac6fef0570aff55439e"
    fetched = await Room.get(room.id)
    fetched.zones_confirmed_for = pair
    await fetched.save()

    assert (await Room.get(room.id)).zones_confirmed_for == pair


@pytest.mark.asyncio
async def test_confirmation_can_be_cleared(mock_beanie_rooms):
    """Explicit null must clear it — that is how a caller re-closes the gate."""
    room = Room(name="Room", zones_confirmed_for="a:b")
    await room.save()

    fetched = await Room.get(room.id)
    fetched.zones_confirmed_for = None
    await fetched.save()

    assert (await Room.get(room.id)).zones_confirmed_for is None


@pytest.mark.asyncio
async def test_partial_patch_preserves_the_confirmation(mock_beanie_rooms):
    """The important one.

    AuditWorkspace reverse-syncs drawing/session identity to the room on every change, and
    its payload never mentions zones_confirmed_for. The router applies PATCH bodies with
    `model_dump(exclude_unset=True)`, so an absent key must leave the stored value alone. If
    that ever regresses, every room silently un-confirms on the next drawing change and the
    user is thrown back to the zone editor for no visible reason.
    """
    from services.backend.api.schemas import UpdateRoomRequest

    pair = "old123:new456"
    room = Room(name="Room", zones_confirmed_for=pair)
    await room.save()

    # Exactly the shape AuditWorkspace.tsx sends.
    payload = UpdateRoomRequest(
        active_old_drawing_id="old123",
        active_new_drawing_id="new456",
        active_old_drawing_name="ref.dxf",
        active_new_drawing_name="rev.dxf",
        active_audit_session_id=None,
        physical_comparison_results=None,
    )
    updates = payload.model_dump(exclude_unset=True)

    assert "zones_confirmed_for" not in updates, (
        "an unset field must not appear in the PATCH body"
    )

    fetched = await Room.get(room.id)
    for field, value in updates.items():
        if field == "physical_comparison_results":
            continue
        setattr(fetched, field, value)
    await fetched.save()

    assert (await Room.get(room.id)).zones_confirmed_for == pair


@pytest.mark.asyncio
async def test_update_request_accepts_the_field(mock_beanie_rooms):
    """Guards the API surface: the field must be settable through UpdateRoomRequest."""
    from services.backend.api.schemas import UpdateRoomRequest

    updates = UpdateRoomRequest(zones_confirmed_for="a:b").model_dump(exclude_unset=True)

    assert updates == {"zones_confirmed_for": "a:b"}
