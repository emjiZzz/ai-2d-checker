"""The `ground_truth` retrieval collection, and the separation that makes it worth having.

Added 2026-09-07, when `ground_truth_markings` turned out to be the one human-judgement store
the retrieval layer did not index. Why that matters, and why the pools are not merged, is in
[[Gotcha - The Ground Truth Store the RAG Could Not Read]]; the short version is that
`corrections` and `findings` are anchored to engine output and so cannot contain a finding the
engine never reported, while a Manual Check marking can.

Four properties are pinned, each a way this goes quietly wrong: the collection is enumerated in
`ALL_COLLECTIONS`, no rebuild reads both an engine-anchored source and ground truth, a retracted
marking is not indexed, and a marking's status reaches the indexed text rather than only its
metadata.
"""
from __future__ import annotations

import inspect

import pytest

from services.backend.domain.models.ground_truth import GroundTruthMarking
from services.backend.infrastructure.retrieval import evaluate as retrieval_evaluate
from services.backend.infrastructure.retrieval import service as retrieval_service
from services.backend.infrastructure.retrieval.index_builder import (
    CORRECTIONS,
    FINDINGS,
    GROUND_TRUTH,
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
