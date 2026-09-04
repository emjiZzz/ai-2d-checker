"""Re-addressing a label after a re-export, and — mostly — refusing to.

A label pointed at the wrong entity still SCORES. It is compared against something nobody looked
at, and the recall figure that comes out is wrong with no symptom anywhere. A missing label is a
visible gap; a mis-addressed one is an invisible lie. So almost every test here is about the
refusal rather than the repair.
"""

from tools.migrate_label_addresses import repair


def _entity(text: str = "", handle: str | None = None) -> dict:
    return {
        "entity_type": "text",
        "properties": {"text": text, **({"handle": handle} if handle else {})},
        "geometry": {},
    }


def _finding(**over) -> dict:
    return {
        "entity_handle": "REV#2",
        "category": "drawing_views",
        "status": "CHANGED",
        "ref_text": "60",
        "rev_text": "70",
        "notes": "",
        "is_bulk": False,
        **over,
    }


# ── payload addresses, which a re-export invalidates ─────────────────────────────────


def test_an_address_that_still_points_at_its_text_is_left_alone():
    """No churn. A re-export moves most lines and not all, and rewriting an address that is
    already correct is a write with a chance of being wrong and no chance of being useful."""
    rev = [_entity("a"), _entity("b"), _entity("70")]
    outcome, _ = repair(_finding(), [], rev)
    assert outcome == "ok"


def test_a_moved_entity_is_re_addressed_from_the_label_own_text():
    # The repair the tool exists for: the payload shifted, the text did not.
    rev = [_entity("70"), _entity("a"), _entity("b")]
    finding = _finding()
    outcome, detail = repair(finding, [], rev)
    assert outcome == "rewritten"
    assert finding["entity_handle"] == "REV#0"
    assert "REV#2 -> REV#0" in detail


def test_two_entities_with_the_same_text_is_a_refusal():
    """The case that decides whether this tool is safe to run unattended.

    Nothing here can say which of the two the annotator meant, and picking one would produce a
    label that scores against an entity they never looked at.
    """
    # The address must be BROKEN for ambiguity to matter: an address still pointing at the right
    # text is left alone whatever else the payload contains, which is the no-churn rule above.
    rev = [_entity("70"), _entity("x"), _entity("70")]
    finding = _finding(entity_handle="REV#1")
    outcome, detail = repair(finding, [], rev)
    assert outcome == "unresolved"
    assert finding["entity_handle"] == "REV#1", "an ambiguous finding must not be rewritten"
    assert "ambiguous" in detail


def test_text_that_appears_nowhere_is_a_refusal():
    # The entity was deleted, or the extractor now renders its text differently. Either way the
    # annotator has to look; a nearest match would be a guess wearing a label's authority.
    finding = _finding()
    outcome, _ = repair(finding, [], [_entity("something else")])
    assert outcome == "unresolved"
    assert finding["entity_handle"] == "REV#2"


def test_a_label_with_no_text_for_its_side_cannot_be_repaired():
    """Two real labels in the corpus are in this state (`REV#508`, `REV#526`, measured
    2026-08-19). Text is the only bridge across a re-export, so these need a human."""
    finding = _finding(rev_text="")
    outcome, detail = repair(finding, [], [_entity("70")])
    assert outcome == "unresolved"
    assert "records no text" in detail


# ── the side prefix decides which payload and which text ─────────────────────────────


def test_a_ref_address_is_resolved_against_the_reference_payload():
    # Getting this backwards would rewrite addresses against the wrong drawing entirely — and
    # the result would still look like a valid label.
    ref = [_entity("zzz"), _entity("60")]
    rev = [_entity("60")]
    finding = _finding(entity_handle="REF#9", status="REMOVED")
    outcome, _ = repair(finding, ref, rev)
    assert outcome == "rewritten"
    assert finding["entity_handle"] == "REF#1"


def test_a_ref_address_matches_on_ref_text_not_rev_text():
    # `ref_text` and `rev_text` differ on every CHANGED, which is most of the corpus. Matching a
    # REF address on the revision's text would silently address the wrong entity.
    ref = [_entity("70"), _entity("60")]
    finding = _finding(entity_handle="REF#9", status="REMOVED")
    outcome, _ = repair(finding, ref, [])
    assert outcome == "rewritten"
    assert finding["entity_handle"] == "REF#1", "should match ref_text '60', not rev_text '70'"


# ── handles, which are supposed to survive ───────────────────────────────────────────


def test_a_handle_that_still_resolves_is_left_alone():
    rev = [_entity("70", handle="1B2A")]
    outcome, _ = repair(_finding(entity_handle="REV-1B2A"), [], rev)
    assert outcome == "ok"


def test_a_handle_that_vanished_is_reported_rather_than_assumed_fine():
    """"Handles survive a re-extraction" is a claim about ezdxf and about block explosion, not a
    guarantee. If one stops resolving, that is a corpus defect and somebody has to know."""
    outcome, detail = repair(_finding(entity_handle="REV-1B2A"), [], [_entity("70")])
    assert outcome == "unresolved"
    assert "no longer in the payload" in detail


def test_a_handle_is_read_from_either_place_the_payload_puts_it():
    # `ExpectedFinding.resolve` uses `getattr`, which finds nothing on the plain dicts a JSONL
    # payload loads as — so every handle would look unresolvable. This is why the lookup is
    # restated dict-aware instead of reused.
    rev = [{"properties": {"handle": "9F"}, "geometry": {}}]
    outcome, _ = repair(_finding(entity_handle="REV-9F"), [], rev)
    assert outcome == "ok"


# ── the text comparison itself ───────────────────────────────────────────────────────


def test_text_is_compared_after_trimming_and_from_either_field():
    # The payload puts text under `properties.text` or `geometry.text` depending on entity type,
    # and exporters leave stray whitespace. Neither is a difference an annotator asserted.
    rev = [{"properties": {}, "geometry": {"text": "  70 "}}]
    finding = _finding(entity_handle="REV#9")
    outcome, _ = repair(finding, [], rev)
    assert outcome == "rewritten"
    assert finding["entity_handle"] == "REV#0"


def test_matching_is_exact_not_fuzzy():
    """`70` must not match `70.0` or `170`. The corpus's whole value is that a label means one
    entity; a normalising match here would quietly merge findings the annotator kept apart."""
    finding = _finding()
    outcome, _ = repair(finding, [], [_entity("70.0"), _entity("170")])
    assert outcome == "unresolved"
