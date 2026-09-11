"""The `ground_truth` retrieval collection, and the separation that makes it worth having.

Why the pools are not merged is in
[[Gotcha - The Ground Truth Store the RAG Could Not Read]]. Four properties are pinned, each a way
it goes quietly wrong: the collection is enumerated in `ALL_COLLECTIONS`, no rebuild reads both an
engine-anchored source and ground truth, a retracted marking is not indexed, and a marking's
status reaches the indexed text rather than only its metadata.
"""
from __future__ import annotations

import inspect

import pytest

from services.backend.domain.models.cad_point import CadPoint
from services.backend.domain.models.ground_truth import EntityAddress, GroundTruthMarking
from services.backend.infrastructure.retrieval import evaluate as retrieval_evaluate
from services.backend.infrastructure.retrieval import service as retrieval_service
from services.backend.infrastructure.retrieval.index_builder import (
    CORRECTIONS,
    FINDINGS,
    GROUND_TRUTH,
)


def _addr_on(drawing_id: str) -> EntityAddress:
    return EntityAddress.model_construct(
        drawing_id=drawing_id, handle="1B2A", entity_type="text", layer="0", text="45", point=None
    )


def _marking(**overrides):
    """A minimal marking. `model_construct` skips validation so the suite needs no database."""
    fields = {
        "session_id": "sess-1",
        "side": "both",
        "ref_address": None,
        "rev_address": None,
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


# ---------------------------------------------------------------------------
# 1. The collection is enumerated
# ---------------------------------------------------------------------------

def test_ground_truth_is_in_all_collections():
    """A constant nothing enumerates is a collection that is never built or measured.

    This is the defect this module was written for: `ground_truth_markings` existed, had a UI,
    and accumulated 163 live markings while the retrieval layer indexed seven collections that
    did not include it.
    """
    assert GROUND_TRUTH in retrieval_evaluate.ALL_COLLECTIONS


def test_ground_truth_has_a_registered_rebuilder():
    """`bootstrap_retrieval_indexes` builds what its `builders` map names, and nothing else."""
    source = inspect.getsource(retrieval_service.bootstrap_retrieval_indexes)
    assert "GROUND_TRUTH: rebuild_ground_truth_index" in source


# ---------------------------------------------------------------------------
# 2. The pools stay separate
# ---------------------------------------------------------------------------

def test_no_rebuild_reads_both_an_engine_anchored_source_and_ground_truth():
    """The one place the two pools could merge is a rebuild that reads both models.

    Asserted on the source because the property is which model a rebuild queries; both are async
    and exercising them for real would need a database.
    """
    engine_anchored = ("AuditFeedbackDocument", "AuditViolation")
    for rebuild in (
        retrieval_service.rebuild_corrections_index,
        retrieval_service.rebuild_findings_index,
        retrieval_service.rebuild_ground_truth_index,
    ):
        source = inspect.getsource(rebuild)
        reads_engine = any(model in source for model in engine_anchored)
        reads_ground_truth = "GroundTruthMarking" in source
        assert not (reads_engine and reads_ground_truth), (
            f"{rebuild.__name__} reads both an engine-anchored source and ground truth. "
            f"Pooling them lets a dismissal answer a question about what is on the drawing."
        )


def test_ground_truth_builds_into_its_own_collection():
    source = inspect.getsource(retrieval_service.rebuild_ground_truth_index)
    assert "GROUND_TRUTH" in source
    for other in (CORRECTIONS, FINDINGS):
        assert f'"{other}"' not in source


# ---------------------------------------------------------------------------
# 3. A retracted marking is not indexed
# ---------------------------------------------------------------------------

def test_a_retracted_marking_is_not_indexed():
    """A withdrawn judgement must not be citable back at the next checker.

    The concrete hazard, from [[Gotcha - Two Ground-Truth Stores That Never Met]]: 31 of 38
    markings in one session carried `retracted_at`, and a converter that ignored the field would
    have manufactured 31 findings a person had explicitly taken back.
    """
    from datetime import UTC, datetime

    retracted = _marking(retracted_at=datetime.now(UTC))
    assert retrieval_service.ground_truth_record(retracted) is None


def test_a_live_marking_is_indexed():
    assert retrieval_service.ground_truth_record(_marking()) is not None


def test_a_marking_with_no_text_and_no_notes_is_skipped():
    """A category plus a status is not retrievable by any real query."""
    empty = _marking(ref_text="", rev_text="", notes="")
    assert retrieval_service.ground_truth_record(empty) is None


# ---------------------------------------------------------------------------
# 4. A disagreement survives indexing
# ---------------------------------------------------------------------------

def test_status_is_in_the_indexed_text_not_only_in_metadata():
    """Two passes reaching opposite statuses on one text must not collapse to one record.

    Measured on this corpus: the same BOM cell was marked CHANGED in three repeat passes and
    MATCHED in a fourth. With the status only in metadata both records carry identical text and
    `_collapse_duplicate_texts` keeps one, so the disagreement disappears.
    """
    changed = retrieval_service.ground_truth_record(_marking(status="CHANGED", id="gt-a"))
    matched = retrieval_service.ground_truth_record(_marking(status="MATCHED", id="gt-b"))
    assert changed.text != matched.text
    assert "CHANGED" in changed.text
    assert "MATCHED" in matched.text


def test_the_pattern_carries_what_a_query_can_match_on():
    """A hit has to answer "what kind of thing, where, and what changed", not just the text.

    Entity type and layer are query terms; a corpus that indexes only the changed string cannot
    answer "what have engineers seen on this layer".
    """
    address = EntityAddress.model_construct(
        drawing_id="d1", handle="1B2A", entity_type="dimension", layer="DIM", text="55-15",
        point=CadPoint.model_construct(x=120.5, y=44.0, space="model"),
    )
    record = retrieval_service.ground_truth_record(_marking(ref_address=address))
    assert "dimension" in record.text
    assert "DIM" in record.text


def test_location_is_metadata_not_indexed_text():
    """Coordinates are not query terms; indexing them would be noise in a lexical encoder.

    They still have to survive, or a hit cannot be placed back on the sheet.
    """
    address = EntityAddress.model_construct(
        drawing_id="d1", handle="1B2A", entity_type="text", layer="TITLE", text="x",
        point=CadPoint.model_construct(x=120.5, y=44.0, space="model"),
    )
    record = retrieval_service.ground_truth_record(_marking(ref_address=address))
    assert record.metadata["x"] == 120.5
    assert record.metadata["y"] == 44.0
    assert record.metadata["handle"] == "1B2A"
    assert record.metadata["layer"] == "TITLE"
    assert "120.5" not in record.text


def test_a_marking_with_no_address_still_builds():
    """`ref_address`/`rev_address` are optional on the model, so the record cannot assume one."""
    record = retrieval_service.ground_truth_record(_marking(ref_address=None, rev_address=None))
    assert record is not None
    assert record.metadata["x"] is None


def test_two_sheets_carrying_the_same_value_stay_two_records():
    """`_collapse_duplicate_texts` keys on text alone, so the sheet must be IN the text.

    Sibling sheets from one template hold the same title-block and BOM values, so without this a
    second pair's markings collapse into the first pair's and vanish from the index. Measured
    2026-09-07 on the first two real pairs: 20 of 56 records dropped, and the share grows with
    every pair marked.
    """
    names = {"d1": "M7452A0N01_reference.dxf", "d2": "M7452A1N01_reference.dxf"}
    first = _marking(id="a", ref_address=_addr_on("d1"))
    second = _marking(id="b", ref_address=_addr_on("d2"))

    a = retrieval_service.ground_truth_record(first, names)
    b = retrieval_service.ground_truth_record(second, names)

    assert a.text != b.text
    assert "M7452A0N01_reference.dxf" in a.text
    assert "M7452A1N01_reference.dxf" in b.text


def test_the_citation_names_the_sheet():
    """A hit that cannot say which drawing it came from cannot be checked against it."""
    record = retrieval_service.ground_truth_record(
        _marking(ref_address=_addr_on("d1")), {"d1": "M7452A0N01_reference.dxf"}
    )
    assert "M7452A0N01_reference.dxf" in record.citation()


def test_an_unknown_drawing_still_builds_a_record():
    """A marking whose drawing has been deleted must not drop out of the corpus silently."""
    record = retrieval_service.ground_truth_record(_marking(ref_address=_addr_on("gone")), {})
    assert record is not None
    assert record.source == "Human ground truth"


def test_the_citation_says_the_record_is_ground_truth():
    """A hit that cannot be told apart from a correction invites exactly the wrong reading."""
    record = retrieval_service.ground_truth_record(_marking())
    assert record.source == "Human ground truth"
    assert "Human ground truth" in record.citation()


@pytest.mark.parametrize(
    ("ref_text", "rev_text", "expected"),
    [
        ("A", "B", "A -> B"),
        ("A", "A", "A"),
        ("", "B", "B"),
        ("A", "", "A"),
    ],
)
def test_both_sides_reach_the_indexed_text(ref_text, rev_text, expected):
    """A query naming either side has to be able to find the marking.

    ASCII arrow deliberately: citations are printed and this console is cp932.
    """
    record = retrieval_service.ground_truth_record(
        _marking(ref_text=ref_text, rev_text=rev_text)
    )
    assert expected in record.text
