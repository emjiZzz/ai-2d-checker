"""The `rag` → `deterministic` rename, and the compat alias that makes it safe.

The method name is written into the room document, the comparison request, the room response
and the cache filename. `"rag"` named a technique the engine does not contain — no retrieval,
no LLM — which was tolerable while it was one default of four and became the system's entire
vocabulary once [[ADR-006]] removed the other three.

What these tests pin is the part that can silently rot: the alias is permanent. Rooms
written before the rename still say `"rag"` on disk and no migration was run, so the day the
alias is "cleaned up" as dead code is the day those rooms stop loading. Each test below says
which artifact would break.
"""

import pytest
from pydantic import ValidationError

from services.backend.api.schemas import (
    PhysicalComparisonRequest,
    RoomCreateRequest,
    RoomResponse,
)
from services.backend.domain.models.comparison_method import (
    DETERMINISTIC,
    LEGACY_METHOD_ALIASES,
    normalize_comparison_method,
)


def _request(**kw):
    return PhysicalComparisonRequest(reference_drawing_id="ref", drawing_id="rev", **kw)


def test_the_method_is_named_for_what_it_does():
    assert DETERMINISTIC == "deterministic"
    assert "rag" in LEGACY_METHOD_ALIASES


@pytest.mark.parametrize("value", sorted(LEGACY_METHOD_ALIASES))
def test_every_legacy_alias_folds_to_the_current_name(value):
    assert normalize_comparison_method(value) == DETERMINISTIC


def test_non_strings_pass_through_untouched():
    """The normaliser must not become a second validator — rejecting is the Literal's job, and
    doing it here produces an error naming this helper instead of the field the user set."""
    for value in (None, 7, {"a": 1}):
        assert normalize_comparison_method(value) is value


@pytest.mark.parametrize(
    "model, kwargs",
    [
        (PhysicalComparisonRequest, {"reference_drawing_id": "ref", "drawing_id": "rev"}),
        (RoomCreateRequest, {"name": "a room"}),
    ],
)
def test_legacy_rag_is_accepted_and_normalised_on_input(model, kwargs):
    """A desktop build older than the rename still POSTs `"rag"`. Rejecting it would 422 every
    comparison that client runs, which is a hard break for a shipped app."""
    assert model(**kwargs, comparison_method="rag").comparison_method == DETERMINISTIC


@pytest.mark.parametrize(
    "model, kwargs",
    [
        (PhysicalComparisonRequest, {"reference_drawing_id": "ref", "drawing_id": "rev"}),
        (RoomCreateRequest, {"name": "a room"}),
    ],
)
def test_the_default_is_the_current_name(model, kwargs):
    assert model(**kwargs).comparison_method == DETERMINISTIC


def test_a_room_response_carrying_the_legacy_name_still_serialises():
    """RoomResponse is built from a Room document. A room created before the rename holds
    `"rag"` in Mongo — no migration was run — so this is the read path for real stored data."""
    from datetime import datetime

    response = RoomResponse(
        id="1",
        name="legacy room",
        comparison_method="rag",
        created_at=datetime(2026, 7, 22),
        updated_at=datetime(2026, 7, 22),
    )
    assert response.comparison_method == DETERMINISTIC


def test_a_removed_method_is_still_rejected():
    """The alias must not become a general-purpose accept-anything. `hybrid` and friends were
    deleted in ADR-006; a request naming one is a real error and must surface as one."""
    for removed in ("hybrid", "rag_ai", "ai_vision"):
        with pytest.raises(ValidationError):
            _request(comparison_method=removed)


def test_the_eval_runner_still_accepts_the_legacy_spelling():
    """`tools/eval.py --method rag` appears in the vault, in shell history and in the runner's
    own docstring. The rename must not turn those invocations into a ValueError."""
    from services.backend.infrastructure.eval.runner import OFFLINE_METHODS

    assert {"rag", DETERMINISTIC} <= OFFLINE_METHODS


def test_the_cache_filename_uses_the_new_name():
    """The method is a path segment, so the rename orphans pre-rename cache entries by design
    — measured at one real v42 file. This pins that the new name is what gets written, since a
    silent revert here would look like a cache that never hits."""
    from services.backend.infrastructure.audit.comparison.cache_manager import (
        ComparisonCacheManager,
    )

    path = ComparisonCacheManager._get_cache_path("refid", "revid", "refhash", "revhash")
    assert f"_{DETERMINISTIC}_" in path.name
    assert "_rag_" not in path.name
