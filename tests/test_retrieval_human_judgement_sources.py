"""Stage A — the two human-judgement retrieval sources, and the properties that make them safe.

`corrections` (every non-retracted `AuditFeedbackDocument`) and `findings` (every
`AuditViolation`, reviewed or not) were added on 2026-08-17 to widen the retrieval corpus. The
motivation is arithmetic: `metrics.chance_recall_at_k` is `k/N` over a single collection's own
record count, so at `lessons` = 17 and `standards` = 16 the chance floor sits at 0.29 and 0.31
against a 0.25 maximum — no retrieval score over those collections can be informative regardless
of how good the encoder is. A collection has to be big enough to measure before it can be
measured.

Three properties are pinned here, and each one is a way this could go quietly wrong:

1. `lessons` text must not move. `findings` is a strict superset of `lessons`, so the two
   share `violation_record`. If that generalisation changed the text of an approved violation by
   even one byte, `index_builder._digest` would change, and every label ever authored against
   `lessons` would fail with `LabelDriftError` — which presents as "the encoder regressed".

2. A citation must state its review state. Most of `findings` has never been reviewed by
   anyone. A hit that does not say so is the hazard ADR-008 named for retrieval: *"surfacing
   near-miss rules as authoritative is a recall attack"*.

3. A disagreement must survive indexing. `_collapse_duplicate_texts` drops byte-identical
   texts to protect the chance floor's denominator. If a correction's verb lived only in
   metadata, two corrections that reached *opposite* verdicts on the same entity text would be
   byte-identical and one would be silently dropped — discarding the single most informative
   row in the corpus.
"""
from __future__ import annotations

import inspect
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from services.backend.domain.models.audit_feedback import AuditFeedbackDocument
from services.backend.domain.models.audit_violation import (
    RESOLUTION_APPROVED,
    RESOLUTION_REJECTED,
    AuditViolation,
)
from services.backend.infrastructure import retrieval
from services.backend.infrastructure.retrieval import service as retrieval_service
from services.backend.infrastructure.retrieval.evaluate import ALL_COLLECTIONS
from services.backend.infrastructure.retrieval.index_builder import (
    _collapse_duplicate_texts,
    _record_id,
    chunk_markdown_by_heading,
    records_from_entities,
    records_from_vault_notes,
)
from services.backend.infrastructure.utils.text import strip_mtext
from tools import retrieval_eval


def _violation(
    vid: str = "v1",
    resolution: str | None = None,
    category: str = "notes_section",
    description: str = "[ADDED] 面取り C0.5 のこと",
    remarks: str = "",
) -> AuditViolation:
    violation = AuditViolation.model_construct(
        audit_session_id="session-1",
        severity="high",
        category=category,
        description=description,
        recommendation="Confirm the note against the revision.",
        source="rule_engine",
        resolution_type=resolution,
        is_resolved=resolution == RESOLUTION_APPROVED,
        resolved_at=datetime.now(UTC) if resolution else None,
        checker_remarks=remarks,
    )
    violation.id = vid
    return violation


def _feedback(  # noqa: PLR0913 — each argument is a field the record builder branches on
    fid: str = "f1",
    entity_text: str = "板厚 12",
    corrected_status: str = "dismissed",
    original_status: str = "CHANGED",
    category: str = "drawing_views",
    comment: str = "",
    retracted: bool = False,
    corrected_category: str | None = None,
    corrected_value: str | None = None,
) -> AuditFeedbackDocument:
    doc = AuditFeedbackDocument.model_construct(
        session_id="session-1",
        drawing_id="drawing-1",
        client_name="KEMCO",
        entity_text=entity_text,
        category=category,
        original_status=original_status,
        human_corrected_status=corrected_status,
        human_comment=comment or None,
        corrected_category=corrected_category,
        corrected_value=corrected_value,
        retracted_at=datetime.now(UTC) if retracted else None,
    )
    doc.id = fid
    return doc


# ---------------------------------------------------------------------------
# 1. The lessons text must not move
# ---------------------------------------------------------------------------

def test_an_approved_violation_indexes_exactly_the_text_it_did_before():
    """Pins the `lessons` corpus digest across the `_lesson_record` -> `violation_record` move.

    The join is `category / description / recommendation / checker_remarks`, newline-separated,
    empty parts skipped. Written out literally rather than reconstructed from the object, so this
    fails if the *format* changes even when both sides would agree.
    """
    record = retrieval_service.violation_record(
        _violation(resolution=RESOLUTION_APPROVED, remarks="Confirmed against the revision.")
    )

    assert record is not None
    assert record.text == (
        "notes_section\n"
        "[ADDED] 面取り C0.5 のこと\n"
        "Confirm the note against the revision.\n"
        "Confirmed against the revision."
    )


def test_a_violation_with_no_usable_text_is_still_skipped():
    empty = AuditViolation.model_construct(
        audit_session_id="s", severity="low", category="", description="",
        recommendation="", source="rule_engine", resolution_type=RESOLUTION_APPROVED,
        checker_remarks="",
    )
    empty.id = "v-empty"
    assert retrieval_service.violation_record(empty) is None


def test_lessons_and_findings_are_built_from_the_same_record_function():
    """Two copies of "how a violation becomes text" would drift while both kept working.

    Asserted on the source because the property is *which function is called*; both rebuilds are
    async and hitting them for real would need a database.
    """
    for rebuild in (
        retrieval_service.rebuild_lessons_index,
        retrieval_service.rebuild_findings_index,
    ):
        source = inspect.getsource(rebuild)
        assert "violation_record" in source, (
            f"{rebuild.__name__} does not call violation_record — if it builds its own Record, "
            f"`lessons` and `findings` can disagree about the same violation."
        )


# ---------------------------------------------------------------------------
# 2. A citation must state its review state
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("resolution", "expected_source"),
    [
        (RESOLUTION_APPROVED, "Confirmed finding"),
        (RESOLUTION_REJECTED, "Rejected finding"),
        (None, "Unreviewed finding"),
    ],
)
def test_review_state_is_carried_in_the_citation_not_only_in_metadata(
    resolution, expected_source
):
    record = retrieval_service.violation_record(_violation(resolution=resolution))
    assert record is not None
    assert record.source == expected_source
    assert record.metadata["resolution_type"] == resolution
    # `source` is what `citation()` renders, which is what a consumer shows a human.
    assert expected_source in record.citation()


def test_an_unrecognised_resolution_reads_as_unreviewed_rather_than_confirmed():
    """The safe direction. A value nothing writes today must not inherit "Confirmed"."""
    record = retrieval_service.violation_record(_violation(resolution="SOMETHING_NEW"))
    assert record is not None
    assert record.source == "Unreviewed finding"


# ---------------------------------------------------------------------------
# 3. A disagreement must survive indexing
# ---------------------------------------------------------------------------

def test_opposite_verdicts_on_the_same_entity_text_stay_two_records():
    """The load-bearing test for `corrections`.

    Same entity text, same category, opposite human verdicts. If the verb lived only in metadata
    these two texts would be byte-identical and `_collapse_duplicate_texts` would keep one — so
    the corpus would silently lose exactly the row a checker most needs to see.
    """
    dismissed = retrieval_service.feedback_record(
        _feedback(fid="f1", corrected_status="dismissed")
    )
    confirmed = retrieval_service.feedback_record(
        _feedback(fid="f2", corrected_status="confirmed_valid")
    )
    assert dismissed is not None and confirmed is not None
    assert dismissed.text != confirmed.text

    kept, dropped = _collapse_duplicate_texts("corrections", [dismissed, confirmed])
    assert dropped == 0
    assert [r.id for r in kept] == ["f1", "f2"]


def test_two_identical_corrections_still_collapse_to_one():
    """The other half: the net must still work. Same verdict, same text, one answer."""
    a = retrieval_service.feedback_record(_feedback(fid="f1"))
    b = retrieval_service.feedback_record(_feedback(fid="f2"))
    kept, dropped = _collapse_duplicate_texts("corrections", [a, b])
    assert dropped == 1
    assert len(kept) == 1


def test_a_retracted_correction_is_never_indexed():
    """Same rule `trainer.build_bundle` applies: a correction taken back teaches nothing.

    The row survives in Mongo as the audit trail of who taught the model what; indexing it would
    let a withdrawn judgement be cited back at the next checker as though it still stood.
    """
    assert retrieval_service.feedback_record(_feedback(retracted=True)) is None
    assert retrieval_service.feedback_record(_feedback(retracted=False)) is not None


def test_a_correction_with_neither_entity_text_nor_comment_is_not_indexed():
    assert retrieval_service.feedback_record(_feedback(entity_text="", comment="")) is None
    # A comment alone is enough — it is the part a human actually wrote.
    assert retrieval_service.feedback_record(
        _feedback(entity_text="", comment="The BOM row was renumbered, not changed.")
    ) is not None


def test_the_human_comment_reaches_the_indexed_text():
    """It is the most valuable part of the record and the reason this collection is worth having."""
    record = retrieval_service.feedback_record(
        _feedback(comment="Re-trace, not a real thickness change.")
    )
    assert record is not None
    assert "Re-trace, not a real thickness change." in record.text


@pytest.mark.parametrize(
    ("kwargs", "fragment"),
    [
        ({"corrected_category": "notes_section"}, "Recategorised as notes_section"),
        ({"corrected_value": "14"}, "Corrected value: 14"),
    ],
)
def test_the_correction_target_is_indexed_for_the_verbs_that_carry_one(kwargs, fragment):
    record = retrieval_service.feedback_record(_feedback(**kwargs))
    assert record is not None
    assert fragment in record.text


def test_the_client_is_recorded_so_a_consumer_can_scope_on_it():
    """Nothing here filters by client; a consumer that turns a hit into a rule must.

    Cross-client contamination via a learned rule is a defect this repo has already fixed once,
    in `AutoDocEngine`. Retrieval does not reintroduce it — it writes no rules — but the field
    has to be present for a caller to do the right thing.
    """
    record = retrieval_service.feedback_record(_feedback())
    assert record is not None
    assert record.metadata["client_name"] == "KEMCO"


# ---------------------------------------------------------------------------
# Registry wiring
# ---------------------------------------------------------------------------

def test_the_new_collections_are_registered_everywhere_that_enumerates_collections():
    """`ALL_COLLECTIONS` drives the census, the CLI's `--collection` choices and the baseline.

    A collection that exists but is not registered is invisible to every measurement, which is
    the failure mode this whole stage exists to remove.
    """
    assert retrieval.CORRECTIONS in ALL_COLLECTIONS
    assert retrieval.FINDINGS in ALL_COLLECTIONS
    # `__all__` carries the exported *names*; the constants carry the collection *values*.
    assert "CORRECTIONS" in retrieval.__all__
    assert "FINDINGS" in retrieval.__all__


def test_both_new_collections_are_bootstrapped_at_startup():
    source = inspect.getsource(retrieval_service.bootstrap_retrieval_indexes)
    assert "CORRECTIONS" in source and "FINDINGS" in source


# ---------------------------------------------------------------------------
# Stage A, second pass — vault and entities
# ---------------------------------------------------------------------------

def test_a_heading_repeated_in_one_note_produces_distinct_record_ids():
    """`AI Maturity Ladder — Staged Plan` carries six `Exit criterion` sections, one per stage.

    All six hashed to a single id before 2026-08-17, so twelve of the vault's 990 chunks shared
    four ids. Nothing pins a chunk id today, which is why it was invisible — and
    `RetrievalLabel.relevant_ids` names chunk ids, so it would have become a silent mislabelling
    the moment Stage C started.
    """
    note = (
        "## Stage 0a\nSomething about the first stage that is long enough to index.\n"
        "### Exit criterion\nThe first stage is done when the working set is clean.\n"
        "## Stage 0b\nSomething about the second stage that is long enough to index.\n"
        "### Exit criterion\nThe second stage is done when eight pairs are labelled.\n"
    )
    records = chunk_markdown_by_heading(note, source="Staged Plan")

    assert [r.section for r in records] == [
        "Stage 0a", "Exit criterion", "Stage 0b", "Exit criterion",
    ]
    exit_criteria = [r for r in records if r.section == "Exit criterion"]
    assert exit_criteria[0].text != exit_criteria[1].text
    assert exit_criteria[0].id != exit_criteria[1].id, (
        "two different texts under one id means a relevance label cannot address either"
    )
    assert len({r.id for r in records}) == len(records)


def test_a_note_with_unique_headings_keeps_its_original_ids():
    """The collision fix must not move ids that were never colliding.

    `domain_rules` is built by the same chunker and its ids are the addressing scheme for any
    label authored against it. Only *repeats* are suffixed, so the common case is untouched —
    the id below is the plain `sha256("Note::Heading")[:16]` the function has always produced.
    """
    note = "## Alpha\nBody text long enough to clear the minimum chunk size.\n"
    (record,) = chunk_markdown_by_heading(note, source="Note")
    assert record.id == _record_id("Note", "Alpha")


def test_entity_text_is_read_and_normalised_the_way_the_engine_reads_it():
    """`properties["text"] or properties["value"]`, through `strip_mtext`.

    Reading the raw property here would let this collection disagree with the comparison engine
    about what an entity *says* — see `candidate_generator.py:462`.
    """
    raw = r"\A1;%%c120"
    entity = SimpleNamespace(
        id="e1", drawing_id="d1", layer="DIM", entity_type="dimension",
        handle="1B2A", properties={"text": raw},
    )
    (record,) = records_from_entities([entity], {"d1": "M745230A01.dxf"})
    assert record.text == strip_mtext(raw).strip()
    assert record.source == "M745230A01.dxf"
    assert record.section == "DIM"
    assert record.metadata["handle"] == "1B2A"


def test_an_entity_falls_back_to_the_value_property():
    entity = SimpleNamespace(
        id="e2", drawing_id="d1", layer="0", entity_type="text",
        handle=None, properties={"value": "バリ取りのこと"},
    )
    (record,) = records_from_entities([entity], {})
    assert record.text == "バリ取りのこと"


@pytest.mark.parametrize("text", ["", "  ", "A", "12"])
def test_entity_text_below_the_floor_is_not_indexed(text):
    """A stray character or a bare number is not something a real query retrieves."""
    entity = SimpleNamespace(
        id="e3", drawing_id="d1", layer="0", entity_type="text",
        handle=None, properties={"text": text},
    )
    assert records_from_entities([entity], {}) == []


def test_an_entity_with_no_known_drawing_name_cites_its_id_rather_than_nothing():
    entity = SimpleNamespace(
        id="e4", drawing_id="d-unknown", layer="0", entity_type="text",
        handle=None, properties={"text": "面取り C0.5"},
    )
    (record,) = records_from_entities([entity], {})
    assert record.source == "d-unknown"


def test_the_vault_source_excludes_the_directories_its_caller_names(tmp_path):
    """The client-rules directory is already `domain_rules`; indexing it twice would put the
    same text in two collections whose trust levels differ."""
    (tmp_path / "Note.md").write_text(
        "## Alpha\nBody text long enough to clear the minimum chunk size.\n", encoding="utf-8"
    )
    secret = tmp_path / "08 - Client Domain & CAD Rules"
    secret.mkdir()
    (secret / "Client.md").write_text(
        "## Beta\nClient body text long enough to clear the minimum.\n", encoding="utf-8"
    )

    everything = records_from_vault_notes(tmp_path)
    filtered = records_from_vault_notes(tmp_path, frozenset({"08 - Client Domain & CAD Rules"}))

    assert {r.section for r in everything} == {"Alpha", "Beta"}
    assert {r.section for r in filtered} == {"Alpha"}


def test_a_missing_vault_is_normal_operation_not_an_error(tmp_path):
    assert records_from_vault_notes(tmp_path / "nope") == []


def test_the_vault_is_not_marked_client_local():
    """It is git-tracked and identical on every install at a given commit, so a committed
    baseline value for it is valid rather than machine-specific."""
    assert retrieval.VAULT not in retrieval_eval.CLIENT_LOCAL_COLLECTIONS


def test_the_mongo_sourced_collections_are_marked_client_local():
    """A committed baseline must not pin a count that varies per install.

    `corrections` and `findings` come from the local database, so their record counts and digests
    are machine-specific. Pinning them would make every other install read a normal difference as
    a regression — the reason `domain_rules` was already excluded.
    """
    assert retrieval.CORRECTIONS in retrieval_eval.CLIENT_LOCAL_COLLECTIONS
    assert retrieval.FINDINGS in retrieval_eval.CLIENT_LOCAL_COLLECTIONS
