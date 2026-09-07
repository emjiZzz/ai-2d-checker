"""A Room declares what it is FOR, separately from which engine compares.

`comparison_method` names an engine and is a `Literal` of one; ADR-006 deleted the picker that
used to offer alternatives. A manual check runs no engine, so it is a second axis rather than a
fourth method — folding it in would make one field answer two questions and resurrect the
picker ADR-006 removed.

The tests below pin the two properties that make that split safe: the axes stay independent,
and a room written before `room_mode` existed still loads as what it always was.
"""

from datetime import datetime
from typing import get_args

import pytest

from services.backend.api.schemas import RoomCreateRequest, RoomResponse


def _response(**kwargs) -> RoomResponse:
    """A minimal valid RoomResponse; `created_at`/`updated_at` are required by the schema."""
    now = datetime(2026, 8, 18)
    return RoomResponse(id="1", name="r", created_at=now, updated_at=now, **kwargs)
from services.backend.domain.models.comparison_method import ComparisonMethodName
from services.backend.domain.models.room_mode import (
    AI_COMPARISON,
    MANUAL_CHECK,
    RoomMode,
    normalize_room_mode,
)


def test_room_mode_and_comparison_method_are_separate_axes():
    """Neither vocabulary may leak into the other."""
    modes = set(get_args(RoomMode))
    methods = set(get_args(ComparisonMethodName))

    assert modes == {AI_COMPARISON, MANUAL_CHECK}
    assert methods == {"deterministic"}
    assert not modes & methods, (
        "A room mode has appeared in comparison_method (or vice versa). comparison_method names "
        "which engine compares; a manual check runs none. Keep them orthogonal."
    )


def test_a_room_predating_the_field_is_an_ai_comparison_room():
    """No migration was run, and none is needed: absent and the default mean the same thing."""
    assert normalize_room_mode(None) == AI_COMPARISON
    assert RoomCreateRequest(name="r").room_mode == AI_COMPARISON
    assert _response().room_mode == AI_COMPARISON


@pytest.mark.parametrize("mode", [AI_COMPARISON, MANUAL_CHECK])
def test_both_modes_round_trip(mode):
    assert RoomCreateRequest(name="r", room_mode=mode).room_mode == mode
    assert _response(room_mode=mode).room_mode == mode


def test_an_unknown_mode_defaults_rather_than_refusing_the_room():
    """A room that opens in the wrong mode is visible and one click from correct.

    A room that cannot be loaded at all is neither — and this field only decides which UI opens,
    so failing closed costs more than it protects.
    """
    assert normalize_room_mode("something_new") == AI_COMPARISON
    assert normalize_room_mode(42) == AI_COMPARISON
    assert RoomCreateRequest(name="r", room_mode="nonsense").room_mode == AI_COMPARISON


def test_a_manual_check_room_still_records_a_comparison_method():
    """The axes are independent: a manual room carries `deterministic` and never invokes it.

    Blanking the method would make the field mean "no engine exists for this room", which is a
    third state it does not have.
    """
    req = RoomCreateRequest(name="r", room_mode=MANUAL_CHECK)
    assert req.comparison_method == "deterministic"
