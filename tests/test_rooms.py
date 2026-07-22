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
