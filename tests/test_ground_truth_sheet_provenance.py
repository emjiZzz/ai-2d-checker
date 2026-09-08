"""A marking keeps its sheet name after the drawing it names is gone.

Deleting a room soft-deletes the Room and HARD-deletes both `DrawingDocument` rows, their
entities, jobs and files, while every `GroundTruthMarking` survives untouched. The sheet name used
to be resolved at index time from `DrawingDocument.find_all()`, so exactly those surviving markings
resolved to "" -- losing the sheet from both the indexed text and the citation, which then let
unrelated markings collapse as duplicate texts.

Measured on Atlas on 2026-09-08 before the fix: 8 live markings already pointed at deleted
drawings. See [[Gotcha - A Deleted Room Took Its Markings' Provenance]].
"""
from __future__ import annotations

from services.backend.domain.models.ground_truth import EntityAddress, GroundTruthMarking
from services.backend.infrastructure.retrieval import service as retrieval_service

SHEET = "M7452A0N01_reference.dxf"


def _addr(drawing_id: str = "d1") -> EntityAddress:
    return EntityAddress.model_construct(
        drawing_id=drawing_id, handle="1B2A", entity_type="text", layer="BOM", text="55", point=None
    )


def _marking(**overrides) -> GroundTruthMarking:
    fields = {
        "session_id": "sess-1",
        "room_id": "room-1",
        "side": "ref",
        "ref_address": _addr(),
        "rev_address": None,
        "ref_sheet": "",
        "rev_sheet": "",
        "status": "CHANGED",
        "category": "bill_of_materials",
        "feature": None,
        "ref_text": "SS400 55-15",
        "rev_text": "SS400 55x15",
        "notes": "",
        "annotator": "engineer",
        "is_bulk": False,
        "retracted_at": None,
    }
    fields.update(overrides)
    marking = GroundTruthMarking.model_construct(**fields)
    marking.id = overrides.get("id", "gt-1")
    return marking


def test_the_sheet_survives_its_drawing_being_deleted():
    """The defect itself: an empty lookup is what a purged room leaves behind."""
    record = retrieval_service.ground_truth_record(_marking(ref_sheet=SHEET), {})
    assert SHEET in record.text
    assert SHEET in record.citation()


def test_without_a_stored_sheet_a_deleted_drawing_loses_it():
    """States the cost the field removes, so the fix cannot be quietly reverted."""
    record = retrieval_service.ground_truth_record(_marking(ref_sheet=""), {})
    assert SHEET not in record.text
    assert record.source == "Human ground truth"


def test_rows_written_before_the_field_still_resolve_by_lookup():
    """The fallback has to stay: 210 markings predate this field."""
    record = retrieval_service.ground_truth_record(_marking(ref_sheet=""), {"d1": SHEET})
    assert SHEET in record.text


def test_the_stored_name_wins_over_the_lookup():
    """What the engineer saw, not what the row was later renamed to."""
    record = retrieval_service.ground_truth_record(
        _marking(ref_sheet=SHEET), {"d1": "renamed_afterwards.dxf"}
    )
    assert SHEET in record.text
    assert "renamed_afterwards.dxf" not in record.text


def test_the_sheet_matches_the_side_the_record_addresses():
    """`ref_address` selects `ref_sheet`; reading the other side would mislabel the hit."""
    rev_only = _marking(
        ref_address=None, rev_address=_addr("d2"), ref_sheet="ref.dxf", rev_sheet="rev.dxf"
    )
    address, sheet = rev_only.addressed_sheet()
    assert sheet == "rev.dxf"
    assert address is rev_only.rev_address

    both = _marking(rev_address=_addr("d2"), ref_sheet="ref.dxf", rev_sheet="rev.dxf")
    address, sheet = both.addressed_sheet()
    assert sheet == "ref.dxf"
    assert address is both.ref_address


def test_two_deleted_sheets_still_produce_two_records():
    """The collapse this prevents. `_collapse_duplicate_texts` keys on text alone."""
    a = retrieval_service.ground_truth_record(_marking(id="a", ref_sheet="sheet_a.dxf"), {})
    b = retrieval_service.ground_truth_record(_marking(id="b", ref_sheet="sheet_b.dxf"), {})
    assert a.text != b.text
