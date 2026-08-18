"""The ground-truth router's contract: what it refuses, and what it never destroys.

DB access is fully mocked (same approach as `test_zone_templates_router.py`), so this runs
offline. The handlers are called directly rather than through a TestClient — the questions here
are about the rules, not about routing.

Two of these tests exist because of specific prior defects in this repo rather than from
general caution, and they say so where they sit.
"""

from datetime import UTC, datetime
from typing import get_args
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from services.backend.api.routers import ground_truth as gt
from services.backend.domain.models.ground_truth import (
    EntityAddress,
    GroundTruthMarking,
    ManualCheckSession,
)
from services.backend.infrastructure.audit.comparison.taxonomy import Category

# `asyncio_mode = "auto"` in pyproject.toml collects async tests without a marker, so a
# module-level `pytest.mark.asyncio` would only warn on the sync tests here.


def _address(handle="1B2A", drawing_id="drw1", text="60"):
    return gt.EntityAddressPayload(
        drawing_id=drawing_id,
        handle=handle,
        entity_type="text",
        layer="0",
        text=text,
        coordinates=[10.0, 20.0],
    )


def _session():
    return ManualCheckSession(
        room_id="room1",
        ref_drawing_id="ref1",
        rev_drawing_id="rev1",
        annotator="imrysn",
    )


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    """No database, no drawing lookups. Every write is captured instead of performed.

    Beanie's `Document.__init__` reaches for its collection, so that has to be stubbed before
    any document is constructed -- same pattern as `test_zone_templates_router.py`.
    """
    for model in (gt.ManualCheckSession, gt.GroundTruthMarking):
        monkeypatch.setattr(
            model, "get_pymongo_collection", classmethod(lambda cls: MagicMock()), raising=False
        )
    monkeypatch.setattr(gt.ManualCheckSession, "save", AsyncMock(), raising=False)
    monkeypatch.setattr(gt.GroundTruthMarking, "save", AsyncMock(), raising=False)
    monkeypatch.setattr(gt.DrawingDocument, "get", AsyncMock(return_value=None), raising=False)
    monkeypatch.setattr(gt, "_recount", AsyncMock())
    monkeypatch.setattr(gt, "get_or_404", AsyncMock(return_value=_session()))


# ── the category must come from the taxonomy, not from here ──────────────────────────


def test_valid_categories_is_read_off_the_taxonomy_not_restated():
    """A hand-copied category list would drift, and the drift would be invisible.

    `GroundTruthMarking.category` is a plain `str` because `domain/` may not import
    `infrastructure/` (`tests/test_layer_boundaries.py`). That makes this router the only place
    the real check happens — so it has to read `taxonomy.Category` itself. A marking filed under
    a category the engine has never heard of is not a corrupt row, it is an *invisible* one:
    every downstream group-by silently drops it.
    """
    assert gt.VALID_CATEGORIES == frozenset(get_args(Category))
    assert len(gt.VALID_CATEGORIES) == 6


async def test_an_invented_category_is_refused():
    with pytest.raises(HTTPException) as exc:
        await gt.create_marking(
            "sess1",
            gt.CreateMarkingRequest(
                status="ADDED", category="Manual Marker", rev_address=_address()
            ),
        )
    assert exc.value.status_code == 422
    assert "taxonomy" in str(exc.value.detail)


@pytest.mark.parametrize("category", sorted(get_args(Category)))
async def test_every_real_category_is_accepted(category):
    result = await gt.create_marking(
        "sess1",
        gt.CreateMarkingRequest(status="ADDED", category=category, rev_address=_address()),
    )
    assert result.success
    assert result.data.category == category


# ── a marking with no subject is refused ─────────────────────────────────────────────


async def test_a_marking_addressing_no_entity_is_refused():
    """The failure this whole feature exists not to repeat.

    The marker already shipping in the product (`CanvasContextMenu` -> `custom_marker_*`)
    records `category: 'Manual Marker'`, `affected_entities: []` and a bare coordinate. It says
    a human pointed at a place and nothing about what they saw there, which is exactly why
    nothing can learn from it — `build_feature_row`'s primary feature is `text_combined`, and
    with no entity there is no text.

    Storing that shape here would fill the dataset with rows that look like data and are not.
    """
    with pytest.raises(HTTPException) as exc:
        await gt.create_marking(
            "sess1", gt.CreateMarkingRequest(status="MATCHED", category="drawing_views")
        )
    assert exc.value.status_code == 422
    assert "must address at least one entity" in str(exc.value.detail)


# ── side is derived from the addresses, never trusted from the client ────────────────


@pytest.mark.parametrize(
    "ref, rev, expected",
    [
        (True, True, "both"),
        (True, False, "ref"),
        (False, True, "rev"),
    ],
)
async def test_side_is_derived_from_which_addresses_exist(ref, rev, expected):
    result = await gt.create_marking(
        "sess1",
        gt.CreateMarkingRequest(
            status="CHANGED" if ref and rev else "ADDED",
            category="drawing_views",
            ref_address=_address(handle="REF1") if ref else None,
            rev_address=_address(handle="REV1") if rev else None,
        ),
    )
    assert result.data.side == expected


async def test_a_changed_pair_keeps_both_coordinates_separately():
    """The degenerate mirror must not be inherited.

    `CanvasContextMenu` sets `coordinates` and `ref_coordinates` to the *same* point from one
    click, which is correct only where the two sheets share a coordinate frame and meaningless
    on a re-traced revision. A CHANGED marking comes from two clicks and must keep both.
    """
    ref = gt.EntityAddressPayload(
        drawing_id="ref1", entity_type="text", text="20", coordinates=[1.0, 2.0]
    )
    rev = gt.EntityAddressPayload(
        drawing_id="rev1", entity_type="text", text="25", coordinates=[900.0, 800.0]
    )
    result = await gt.create_marking(
        "sess1",
        gt.CreateMarkingRequest(
            status="CHANGED",
            category="drawing_views",
            ref_address=ref,
            rev_address=rev,
            ref_text="20",
            rev_text="25",
        ),
    )
    assert result.data.ref_coordinates == [1.0, 2.0]
    assert result.data.rev_coordinates == [900.0, 800.0]
    assert result.data.ref_coordinates != result.data.rev_coordinates


# ── retraction marks; it never deletes ───────────────────────────────────────────────


async def test_retraction_marks_rather_than_deletes(monkeypatch):
    """This collection is both the dataset and the record of who asserted what.

    A row that silently vanishes is unauditable, and the retraction is itself information: it
    says a human changed their mind, which a later consumer may want to weigh differently from a
    decision that was never made. Same reasoning as `AuditFeedbackDocument.retracted_at`.
    """
    marking = GroundTruthMarking(
        session_id="sess1",
        side="rev",
        rev_address=EntityAddress(drawing_id="drw1", entity_type="text", text="60"),
        status="ADDED",
        category="drawing_views",
        annotator="imrysn",
    )
    delete = AsyncMock()
    monkeypatch.setattr(gt.GroundTruthMarking, "delete", delete, raising=False)
    monkeypatch.setattr(gt, "get_or_404", AsyncMock(return_value=marking))
    monkeypatch.setattr(gt.ManualCheckSession, "get", AsyncMock(return_value=None), raising=False)

    result = await gt.retract_marking("m1")

    assert result.data.retracted_at is not None
    assert marking.retracted_at is not None
    delete.assert_not_awaited()


async def test_retracting_twice_keeps_the_first_timestamp(monkeypatch):
    """Idempotent. A double-click must not rewrite when the engineer changed their mind."""
    first = datetime(2026, 8, 1, tzinfo=UTC)
    marking = GroundTruthMarking(
        session_id="sess1",
        side="rev",
        rev_address=EntityAddress(drawing_id="drw1", entity_type="text"),
        status="ADDED",
        category="drawing_views",
        annotator="imrysn",
        retracted_at=first,
    )
    monkeypatch.setattr(gt, "get_or_404", AsyncMock(return_value=marking))

    result = await gt.retract_marking("m1")
    assert result.data.retracted_at == first


# ── an address is not editable ───────────────────────────────────────────────────────


def test_update_cannot_change_which_entity_a_marking_describes():
    """`UpdateMarkingRequest` deliberately has no address field.

    Editing an address in place would convert a marking into a statement about an entity the
    annotator never looked at, while leaving every timestamp and author field intact. There
    would be no trace. Re-stamping is the supported path.
    """
    fields = set(gt.UpdateMarkingRequest.model_fields)
    assert not fields & {"ref_address", "rev_address", "side"}
    assert "category" in fields and "status" in fields


async def test_update_only_writes_the_fields_that_were_sent(monkeypatch):
    marking = GroundTruthMarking(
        session_id="sess1",
        side="rev",
        rev_address=EntityAddress(drawing_id="drw1", entity_type="text"),
        status="ADDED",
        category="drawing_views",
        notes="original reasoning",
        annotator="imrysn",
    )
    monkeypatch.setattr(gt, "get_or_404", AsyncMock(return_value=marking))

    await gt.update_marking("m1", gt.UpdateMarkingRequest(category="notes_section"))

    assert marking.category == "notes_section"
    assert marking.notes == "original reasoning", "unsent fields must be left alone"
    assert marking.status == "ADDED"


# ── submit finalises; it is not when the data first exists ───────────────────────────


async def test_submit_finalises_a_session_that_already_holds_its_markings(monkeypatch):
    """Markings are saved as they are stamped, so submit is a status change, not a write.

    A submit-shaped API loses an hour of work to one crash — `M745230A01` carries 68
    addressable rows — and an annotator who has lost an hour does not come back.
    """
    session = _session()
    monkeypatch.setattr(gt, "get_or_404", AsyncMock(return_value=session))

    result = await gt.submit_session("sess1")

    assert result.data.status == "submitted"
    assert session.submitted_at is not None
    gt._recount.assert_awaited()


async def test_markings_persist_before_submit_is_ever_called():
    """The incremental guarantee, stated as a test rather than as a comment."""
    await gt.create_marking(
        "sess1",
        gt.CreateMarkingRequest(status="ADDED", category="notes_section", rev_address=_address()),
    )
    gt.GroundTruthMarking.save.assert_awaited()
