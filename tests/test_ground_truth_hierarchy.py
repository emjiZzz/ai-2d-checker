"""A marking states its room, and states the same room its session does.

The hierarchy is room -> session -> marking. It was only ever reachable downward: a marking
carried `session_id` and the room lived one join away on `ManualCheckSession`, so grouping the
raw collection by room was not possible without resolving every session first.

`room_id` is denormalised onto the marking rather than the markings being embedded under a room,
because `sync_manager` merges the two stores by `_id`. Separate documents reconcile; markings
inside one room document are a single `_id`, and two stores taking markings on the same room
would be a lost update the sync cannot detect. See
[[Gotcha - A Union Sync Means No Deletion Is Durable]].

Denormalisation that is not pinned is just duplication, so this pins it: the writer takes the
value from the session it already loaded, and the field is indexed for the reads that motivated
it.
"""
from __future__ import annotations

import ast
import inspect
from pathlib import Path

from services.backend.domain.models.ground_truth import GroundTruthMarking, ManualCheckSession

ROUTER = Path(__file__).resolve().parents[1] / "services/backend/api/routers/ground_truth.py"


def test_a_marking_carries_a_room():
    assert "room_id" in GroundTruthMarking.model_fields


def test_room_id_defaults_to_empty_rather_than_being_required():
    """Rows in `storage/backups/` predate the field; a restore must read back, not fail.

    An empty value means "written before the field existed", which is why it is not `None` and
    not required.
    """
    field = GroundTruthMarking.model_fields["room_id"]
    assert field.default == ""
    assert not field.is_required()


def test_the_writer_takes_the_room_from_the_session_it_already_loaded():
    """The one place the two copies could disagree is the write.

    Asserted on the source: `create_marking` is an async handler over Beanie documents, so
    exercising it for real would need a database, and the property is *which value is assigned*.
    """
    tree = ast.parse(ROUTER.read_text(encoding="utf-8"))
    handler = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "create_marking"
    )
    constructions = [
        node
        for node in ast.walk(handler)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "GroundTruthMarking"
    ]
    assert constructions, "create_marking no longer constructs a GroundTruthMarking"

    for call in constructions:
        room = next((kw for kw in call.keywords if kw.arg == "room_id"), None)
        assert room is not None, (
            "create_marking builds a marking without a room_id. The room would then be "
            "reachable only by joining through the session, which is what this field exists "
            "to avoid."
        )
        # `session.room_id` and nothing else: a room taken from the request body would let a
        # caller file a marking under a room its session does not belong to.
        assert isinstance(room.value, ast.Attribute), room.value
        assert room.value.attr == "room_id"
        assert isinstance(room.value.value, ast.Name)
        assert room.value.value.id == "session", (
            "room_id must come from the loaded session, not from the payload or the path."
        )


def test_the_session_is_still_the_owner_of_the_room():
    """If the session ever stopped carrying `room_id`, the marking's copy would be the only one.

    That is a different design and needs deciding rather than inheriting, so it fails here.
    """
    assert "room_id" in ManualCheckSession.model_fields


def test_grouping_by_room_is_indexed():
    """A browse and a per-room export both filter on room; neither should collection-scan."""
    indexes = GroundTruthMarking.Settings.indexes
    keys = [tuple(k for k, _ in idx.document["key"].items()) for idx in indexes]
    assert ("room_id",) in keys
    assert any(k[0] == "room_id" and len(k) > 1 for k in keys), (
        "no compound index leads with room_id; the live-rows-in-a-room read is the point of it."
    )


def test_the_retrieval_record_carries_the_room():
    """A hit that cannot say which room it came from cannot be grouped back to one."""
    from services.backend.infrastructure.retrieval import service as retrieval_service

    source = inspect.getsource(retrieval_service.ground_truth_record)
    assert '"room_id"' in source
