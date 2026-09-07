"""Marking one entity twice replaces the first rather than making a second live row.

Two live markings on one entity become two labels for one entity in the corpus and two records
in retrieval. Observed twice in 163 real markings, both on handle-less block-exploded children,
which is the case the identity rule has to get right.

Replacement is a supersession, not a delete: the first row is retracted and points at the row
that replaced it. That keeps the engineer's earlier judgement readable and keeps `superseded_by`
distinguishable from a human changing their mind, which is signal a consumer may want to weigh.
"""
from __future__ import annotations

from services.backend.domain.models.cad_point import CadPoint
from services.backend.domain.models.ground_truth import (
    SAME_ENTITY_TOLERANCE,
    EntityAddress,
    GroundTruthMarking,
)


def _addr(**overrides) -> EntityAddress:
    fields = {
        "drawing_id": "d1",
        "handle": None,
        "parent_handle": None,
        "entity_type": "text",
        "layer": "0",
        "text": "カラ－",
        "point": CadPoint.model_construct(x=358.89, y=31.67, space="model"),
    }
    fields.update(overrides)
    return EntityAddress.model_construct(**fields)


def _marking(**overrides) -> GroundTruthMarking:
    fields = {
        "session_id": "s1",
        "side": "both",
        "ref_address": _addr(),
        "rev_address": None,
        "status": "MATCHED",
        "category": "title_block",
        "ref_text": "カラ－",
        "rev_text": "カラ－",
        "annotator": "engineer",
        "retracted_at": None,
        "superseded_by": None,
    }
    fields.update(overrides)
    m = GroundTruthMarking.model_construct(**fields)
    m.id = overrides.get("id", "m1")
    return m


# ---------------------------------------------------------------------------
# Identity: a handle decides it, and only without one does the rest apply
# ---------------------------------------------------------------------------

def test_the_same_handle_is_the_same_entity():
    a = _addr(handle="1B2A", text="one")
    b = _addr(handle="1B2A", text="something else entirely")
    assert a.identifies_same_entity_as(b)


def test_a_different_handle_is_a_different_entity():
    assert not _addr(handle="1B2A").identifies_same_entity_as(_addr(handle="1B2B"))


def test_a_handle_on_only_one_side_is_not_a_match():
    """Nothing proves they are the same, so the conservative answer is no."""
    assert not _addr(handle="1B2A").identifies_same_entity_as(_addr(handle=None))


def test_a_different_drawing_is_never_the_same_entity():
    assert not _addr(handle="1B2A").identifies_same_entity_as(
        _addr(handle="1B2A", drawing_id="d2")
    )


def test_handle_less_entities_match_on_type_layer_text_and_position():
    """The real duplicates were handle-less and agreed on all four."""
    assert _addr().identifies_same_entity_as(_addr())


def test_an_absent_handle_is_the_empty_string_not_none():
    """The regression that reached production on 2026-09-07.

    The extractor writes `""` for a block-exploded child, not `None`. `handle is not None` was
    therefore true for every such entity, so the comparison short-circuited on `"" == ""` and
    called them all one entity -- the tier-2 discriminators never ran. A live session superseded
    17 unrelated markings in a chain and the engineer kept 11 of 18 without seeing anything.

    Two entities with empty-string handles at different places must be different.
    """
    here = _addr(handle="", point=CadPoint.model_construct(x=87.5, y=685.017, space="model"))
    there = _addr(handle="", point=CadPoint.model_construct(x=136.875, y=685.0, space="model"))
    assert not here.identifies_same_entity_as(there)


def test_an_empty_handle_still_matches_itself_through_the_fallback():
    """Normalising `""` to absent must not stop a genuine re-mark from being recognised."""
    assert _addr(handle="").identifies_same_entity_as(_addr(handle=""))


def test_an_empty_handle_and_a_real_handle_are_not_the_same_entity():
    assert not _addr(handle="").identifies_same_entity_as(_addr(handle="1B2A"))


def test_an_empty_parent_handle_is_also_absent():
    """`parent_handle` reaches the same comparison and has the same empty-string shape."""
    assert _addr(handle="", parent_handle="").identifies_same_entity_as(
        _addr(handle="", parent_handle=None)
    )


def test_handle_less_entities_at_different_places_are_different():
    """Two identical strings elsewhere on the sheet are two entities, not one."""
    far = _addr(point=CadPoint.model_construct(x=100.0, y=200.0, space="model"))
    assert not _addr().identifies_same_entity_as(far)


def test_position_matching_allows_the_tolerance_and_no_more():
    inside = _addr(
        point=CadPoint.model_construct(
            x=358.89 + SAME_ENTITY_TOLERANCE / 2, y=31.67, space="model"
        )
    )
    outside = _addr(
        point=CadPoint.model_construct(
            x=358.89 + SAME_ENTITY_TOLERANCE * 2, y=31.67, space="model"
        )
    )
    assert _addr().identifies_same_entity_as(inside)
    assert not _addr().identifies_same_entity_as(outside)


def test_a_different_layer_is_a_different_entity():
    assert not _addr().identifies_same_entity_as(_addr(layer="TITLE"))


# ---------------------------------------------------------------------------
# Marking-level: both addressed sides must agree
# ---------------------------------------------------------------------------

def test_two_markings_on_one_entity_target_the_same_thing():
    assert _marking(id="a").targets_same_entity_as(_marking(id="b"))


def test_a_marking_addressing_both_sides_needs_both_to_agree():
    """A CHANGED marking spans two entities; matching on the reference alone would merge two
    different revisions of the same reference."""
    rev_a = _addr(point=CadPoint.model_construct(x=1.0, y=1.0, space="model"))
    rev_b = _addr(point=CadPoint.model_construct(x=99.0, y=99.0, space="model"))
    assert not _marking(id="a", rev_address=rev_a).targets_same_entity_as(
        _marking(id="b", rev_address=rev_b)
    )


def test_a_marking_with_no_addresses_matches_nothing():
    """`create_marking` refuses these, so this only guards the helper itself."""
    empty = _marking(id="a", ref_address=None, rev_address=None)
    assert not empty.targets_same_entity_as(_marking(id="b"))


def test_sides_addressed_differently_do_not_match():
    """One marking names only the reference, the other only the revision."""
    ref_only = _marking(id="a", ref_address=_addr(), rev_address=None)
    rev_only = _marking(id="b", ref_address=None, rev_address=_addr())
    assert not ref_only.targets_same_entity_as(rev_only)


# ---------------------------------------------------------------------------
# The supersession is distinguishable from a human retraction
# ---------------------------------------------------------------------------

def test_superseded_by_defaults_to_none():
    """A marking the engineer retracted carries no `superseded_by`, which is how the two are
    told apart downstream."""
    assert _marking().superseded_by is None


def test_the_writer_supersedes_rather_than_deleting():
    """Asserted on the source: the handler is async over Beanie and needs a database to run.

    The property is that the earlier row is retracted and linked, never removed -- a delete
    would lose the engineer's first judgement and there would be no way back.
    """
    from pathlib import Path

    router = Path(__file__).resolve().parents[1] / "services/backend/api/routers/ground_truth.py"
    source = router.read_text(encoding="utf-8")
    fn_start = source.index("async def _supersede_earlier_markings_on")
    fn = source[fn_start : source.index("\nasync def ", fn_start + 1)]
    assert "retracted_at = now" in fn
    assert "superseded_by = str(marking.id)" in fn
    assert ".delete()" not in fn
