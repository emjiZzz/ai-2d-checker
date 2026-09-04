"""What survives the trip from a Manual Check session to a corpus label, and what must not.

The bridge writes into the eval corpus, which is this project's measurement instrument. A
conversion defect here does not fail — it produces a label file that reads perfectly and is
wrong, and every metric taken afterwards is quietly measured against it. So the tests that
matter are the refusals: a marking that cannot be placed must be *reported*, never guessed at,
and a session that does not describe the pair must be rejected outright.
"""

from types import SimpleNamespace

import pytest

from services.backend.infrastructure.eval.corpus import GUIDELINE_VERSION
from services.backend.infrastructure.eval.manual_check_bridge import (
    build_labels,
    check_session_matches_pair,
)
from services.backend.infrastructure.eval.serialize import EvalEntity


def entity(handle=None, text="", entity_type="text", layer="0", point=(0.0, 0.0)):
    return EvalEntity(
        entity_type=entity_type,
        layer=layer,
        handle=handle,
        properties={"text": text},
        geometry={"insert": [point[0], point[1]]},
    )


def address(handle=None, text="", entity_type="text", layer="0", drawing_id="d1"):
    """A stored `EntityAddress` as Mongo holds it — a dict, which is what the bridge takes."""
    return {
        "drawing_id": drawing_id,
        "handle": handle,
        "parent_handle": None,
        "entity_type": entity_type,
        "layer": layer,
        "text": text,
    }


def marking(status, category="notes_section", **kwargs):
    base = {
        "_id": kwargs.pop("_id", "m1"),
        "status": status,
        "category": category,
        "ref_text": kwargs.pop("ref_text", ""),
        "rev_text": kwargs.pop("rev_text", ""),
        "notes": kwargs.pop("notes", ""),
        "is_bulk": kwargs.pop("is_bulk", False),
        "ref_address": kwargs.pop("ref_address", None),
        "rev_address": kwargs.pop("rev_address", None),
        "retracted_at": kwargs.pop("retracted_at", None),
    }
    base.update(kwargs)
    return base


def build(markings, ref_entities=None, rev_entities=None):
    return build_labels(
        pair_id="P1",
        markings=markings,
        ref_entities=ref_entities or [],
        rev_entities=rev_entities or [],
        annotator="engineer",
        annotated_at="2026-08-19",
    )


# ---------------------------------------------------------------------------------------
# The status mapping
# ---------------------------------------------------------------------------------------

@pytest.mark.parametrize(
    "status,side,expected_prefix",
    [("ADDED", "rev", "REV-"), ("CHANGED", "rev", "REV-"), ("REMOVED", "ref", "REF-")],
)
def test_a_finding_anchors_on_the_side_its_status_implies(status, side, expected_prefix):
    """A REMOVED exists only on the reference; ADDED and CHANGED anchor on the revision, which
    is what `ExpectedFinding.default_side` says. Anchoring a REMOVED on the revision would
    address the one drawing that by definition does not contain it."""
    m = marking(status, **{f"{side}_address": address(handle="1A9", text="x")})
    result = build([m], ref_entities=[entity("1A9", "x")], rev_entities=[entity("1A9", "x")])
    assert len(result.labels.findings) == 1
    finding = result.labels.findings[0]
    assert finding.status == status
    assert finding.entity_handle.startswith(expected_prefix)


@pytest.mark.parametrize("status", ["MATCHED", "NOT_A_FINDING"])
def test_statuses_with_no_corpus_equivalent_become_not_findings(status):
    """`VALID_STATUSES` is {ADDED, REMOVED, CHANGED}. A verified non-change is not a finding —
    but discarding it would throw away the only thing that makes a false positive there
    *attributable* rather than merely counted."""
    m = marking(status, rev_address=address(handle="1A9", text="x"))
    result = build([m], rev_entities=[entity("1A9", "x")])
    assert result.labels.findings == []
    assert len(result.labels.not_findings) == 1
    assert result.labels.not_findings[0].entity_handle == "REV-1A9"


def test_a_retracted_marking_is_dropped_and_counted():
    """A retraction is the engineer withdrawing the statement. 31 of the 38 markings in the
    session that prompted this feature are retracted — converting them would manufacture
    findings a person explicitly took back."""
    live = marking("ADDED", _id="live", rev_address=address(handle="1A9", text="x"))
    dead = marking(
        "ADDED", _id="dead", rev_address=address(handle="1AA", text="y"),
        retracted_at="2026-08-18 01:15:40",
    )
    result = build([live, dead], rev_entities=[entity("1A9", "x"), entity("1AA", "y")])
    assert len(result.labels.findings) == 1
    assert result.retracted_skipped == 1
    assert "1AA" not in result.labels.findings[0].entity_handle


# ---------------------------------------------------------------------------------------
# Addressing — the part that silently corrupts if it guesses
# ---------------------------------------------------------------------------------------

def test_an_entity_without_a_handle_falls_back_to_its_payload_line():
    """Block-exploded entities carry no handle, and on the reference sheets that is nearly all
    of them. The corpus's second address form is the payload line number."""
    m = marking("REMOVED", ref_address=address(text="only-me", handle=None))
    ref = [entity(None, "decoy"), entity(None, "only-me")]
    result = build([m], ref_entities=ref)
    assert result.labels.findings[0].entity_handle == "REF#1"


def test_the_emitted_handle_comes_from_the_resolved_entity_not_the_marking():
    """The marking's stored handle is a claim about the live drawing; a label must address the
    *frozen payload*. Copying the stored value would emit an address that reads fine and
    resolves to nothing."""
    m = marking("ADDED", rev_address=address(handle=None, text="hello"))
    result = build([m], rev_entities=[entity("BEEF", "hello")])
    assert result.labels.findings[0].entity_handle == "REV-BEEF"


def test_a_marking_that_does_not_resolve_is_reported_not_guessed():
    """The whole point. An unresolved marking is a countable gap; a mis-resolved one silently
    attributes a human's judgement to the wrong entity, which nothing downstream can detect."""
    m = marking("ADDED", rev_address=address(handle="NOPE", text="ghost"), rev_text="ghost")
    result = build([m], rev_entities=[entity("1A9", "something else")])
    assert result.labels.findings == []
    assert len(result.unresolved) == 1
    assert "does not resolve" in result.unresolved[0].reason


def test_a_marking_with_no_address_on_the_needed_side_is_reported():
    result = build([marking("ADDED", rev_address=None)])
    assert result.labels.findings == []
    assert "no usable rev_address" in result.unresolved[0].reason


def test_an_unknown_status_is_reported_rather_than_dropped():
    result = build([marking("SOMETHING_NEW", rev_address=address(handle="1A9"))])
    assert result.unresolved and "unknown marking status" in result.unresolved[0].reason


def test_a_category_outside_the_taxonomy_is_reported_rather_than_crashing():
    """`ExpectedFinding` rejects invented categories. That rejection must land in the report,
    not as a traceback that loses every other marking in the session."""
    m = marking("ADDED", category="made_up", rev_address=address(handle="1A9", text="x"))
    result = build([m], rev_entities=[entity("1A9", "x")])
    assert result.labels.findings == []
    assert len(result.unresolved) == 1


# ---------------------------------------------------------------------------------------
# Fields that must survive
# ---------------------------------------------------------------------------------------

def test_texts_notes_and_bulk_survive_the_conversion():
    m = marking(
        "CHANGED",
        category="title_block",
        ref_address=address(handle="1B6", text="old"),
        rev_address=address(handle="1B7", text="new"),
        ref_text="old", rev_text="new", notes="renumbered", is_bulk=True,
    )
    result = build([m], ref_entities=[entity("1B6", "old")], rev_entities=[entity("1B7", "new")])
    finding = result.labels.findings[0]
    assert (finding.ref_text, finding.rev_text) == ("old", "new")
    assert finding.notes == "renumbered"
    assert finding.is_bulk is True
    assert result.labels.bulk_count == 1


def test_a_zone_derived_category_is_tagged_and_counted():
    """`category_source` has no field on `ExpectedFinding`, and it is load-bearing: attribution
    measured over zone-derived categories compares `zone_detector` with itself. Tagging keeps
    the two kinds distinguishable instead of silently folding them together."""
    m = marking(
        "ADDED", rev_address=address(handle="1A9", text="x"), category_source="zone",
        notes="from the zone",
    )
    result = build([m], rev_entities=[entity("1A9", "x")])
    assert result.zone_derived == 1
    assert result.labels.findings[0].notes.startswith("[category:zone]")


def test_a_human_chosen_category_is_not_tagged():
    m = marking("ADDED", rev_address=address(handle="1A9", text="x"), category_source="human")
    result = build([m], rev_entities=[entity("1A9", "x")])
    assert result.zone_derived == 0
    assert "[category:zone]" not in result.labels.findings[0].notes


def test_the_draft_carries_the_current_guideline_version():
    """`label` refuses a draft written against a stale guideline. A bridge that emitted the
    wrong version would fail at the last step, after the review effort was already spent."""
    assert build([]).labels.guideline_version == GUIDELINE_VERSION


# ---------------------------------------------------------------------------------------
# Session/pair identity — the check that prevents labelling the wrong sheet
# ---------------------------------------------------------------------------------------

def pair(ref_id="r1", rev_id="v1", ref_hash="aaa", rev_hash="bbb"):
    return SimpleNamespace(
        ref=SimpleNamespace(drawing_id=ref_id, file_hash=ref_hash, file_name="ref.dxf"),
        rev=SimpleNamespace(drawing_id=rev_id, file_hash=rev_hash, file_name="rev.dxf"),
    )


def test_matching_ids_and_hashes_is_a_clean_match():
    problems, notes = check_session_matches_pair(
        pair(), ref_drawing_id="r1", rev_drawing_id="v1",
        ref_file_hash="aaa", rev_file_hash="bbb",
    )
    assert problems == [] and notes == []


def test_a_re_upload_matches_on_hash_and_is_only_noted():
    """Measured 2026-08-20: the M745230A01 session names drawings `6a829d45`/`6a829dd1` while
    the corpus pair was exported from `6a72ecba`/`6a72ecd0`, and all four hashes match. An id
    check refuses exactly the case this bridge exists to serve."""
    problems, notes = check_session_matches_pair(
        pair(), ref_drawing_id="other-ref", rev_drawing_id="other-rev",
        ref_file_hash="aaa", rev_file_hash="bbb",
    )
    assert problems == []
    assert len(notes) == 2 and "different upload" in notes[0]


def test_a_different_file_is_refused():
    problems, _ = check_session_matches_pair(
        pair(), ref_drawing_id="r1", rev_drawing_id="v1",
        ref_file_hash="aaa", rev_file_hash="zzz",
    )
    assert len(problems) == 1 and "different file" in problems[0]


def test_swapped_sides_are_named_as_swapped():
    """The wrong-pairing a person is most likely to create by hand, and the one whose findings
    would look most nearly plausible."""
    problems, _ = check_session_matches_pair(
        pair(), ref_drawing_id="v1", rev_drawing_id="r1",
        ref_file_hash="bbb", rev_file_hash="aaa",
    )
    assert len(problems) == 2
    assert all("swapped" in p for p in problems)


def test_without_hashes_it_falls_back_to_comparing_ids():
    """A weaker check beats none when the drawing document is gone."""
    ok, _ = check_session_matches_pair(pair(), ref_drawing_id="r1", rev_drawing_id="v1")
    assert ok == []
    bad, _ = check_session_matches_pair(pair(), ref_drawing_id="nope", rev_drawing_id="v1")
    assert len(bad) == 1 and "no file hash was available" in bad[0]


# ── who did the work ─────────────────────────────────────────────────────────────────


class TestRequireNamedAnnotator:
    """`"unknown"` is not a name, and refusing only empties let it into committed ground truth.

    `create_session` writes the literal string `"unknown"` when a manual check is opened with no
    `X-Session-Token` — an app running but not signed in. The conversion's guard tested for
    emptiness, which that passes, so it would land in `labels/*.json` as the annotator with no
    other record of who did the check.
    """

    def test_a_real_name_passes_through_stripped(self):
        from tools.eval_corpus import require_named_annotator

        assert require_named_annotator("  engineer  ", "sess1") == "engineer"

    def test_an_empty_annotator_is_refused(self):
        from tools.eval_corpus import require_named_annotator

        with pytest.raises(SystemExit) as err:
            require_named_annotator("   ", "sess1")
        assert "attributable" in str(err.value)

    def test_the_unknown_fallback_is_refused_by_name(self):
        from tools.eval_corpus import require_named_annotator

        with pytest.raises(SystemExit) as err:
            require_named_annotator("unknown", "sess1")
        assert "sess1" in str(err.value)
        assert "--annotator" in str(err.value)

    def test_the_refusal_is_case_insensitive(self):
        # The router writes it lower-case, but the value also arrives via `--annotator`, where a
        # person typing "Unknown" means exactly the same thing and must not slip through.
        from tools.eval_corpus import require_named_annotator

        with pytest.raises(SystemExit):
            require_named_annotator("Unknown", "sess1")
