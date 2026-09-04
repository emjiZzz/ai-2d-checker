"""Title-upper-left fields must pair across a bilingual header split.

Reported live: one column of the UL metadata table produced two checklist cards for a value
that had not changed —

    コードNO.   ORIGINAL 230   REVISION NONE   MATCHED
    PART NO.   ORIGINAL NONE  REVISION 230    MATCHED

while the canvas correctly showed a single MATCHED marker on `230`.

This is a recurrence of [[Gotcha - Title Upper-Left Double-Reported by Scale]], which
`match_title_ul_pairs` was written to fix. That fix pairs fields sharing a normalized header
token, which works when one drawing keeps both stacked labels (`Unit No. / ユニットNo.`) and the
other keeps one of them. It cannot work when the two drawings keep different halves — the
reference kept the Japanese label and the revision the English one, so the two keys shared no
token at all.

The two MATCHED badges are the bilateral corroboration guard doing its job on a broken input:
finding `230` in the other drawing's UL region, it correctly refuses to call either row a real
REMOVED/ADDED. So the duplicate stopped looking alarming without ever being fixed — worth
remembering, because that guard will mask the next variant of this too.
"""

import pytest

from services.backend.infrastructure.audit.comparison.orchestrator import (
    _TITLE_UL_SYNONYMS,
    _title_ul_tokens,
    _ul_canonical,
    match_title_ul_pairs,
)


def _pair(key, value):
    return {"key": key, "value": value, "coords": [0.0, 0.0]}


def test_the_reported_case_pairs_into_one_row():
    """The exact keys from the screenshot."""
    matched = match_title_ul_pairs([_pair("コードNO.", "230")], [_pair("PART NO.", "230")])

    assert len(matched) == 1, (
        f"expected one paired row, got {len(matched)} — an unpaired UL field becomes two "
        f"checklist cards for one unchanged value"
    )
    ref_p, rev_p = matched[0]
    assert ref_p is not None and rev_p is not None
    assert (ref_p["value"], rev_p["value"]) == ("230", "230")


@pytest.mark.parametrize(
    ("ref_key", "rev_key"),
    [
        ("ユニットNo.", "Unit No."),
        ("コードNo.", "Part No."),
        ("総製作個数", "T. Q'ty"),
        ("在庫棚入庫", "Stock Q'ty"),
        # and the other way round — the reference is not always the Japanese side
        ("Unit No.", "ユニットNo."),
        ("PART NO.", "コードNO."),
    ],
)
def test_every_bilingual_header_pair_matches_in_both_directions(ref_key, rev_key):
    matched = match_title_ul_pairs([_pair(ref_key, "1")], [_pair(rev_key, "1")])
    assert len(matched) == 1 and all(p is not None for p in matched[0])


def test_a_shared_token_still_wins_over_a_synonym():
    """The literal match must be tried first. With `Unit No. / ユニットNo.` on one side, the
    right partner is the one sharing a token, not merely one in the same synonym group."""
    ref = [_pair("Unit No. / ユニットNo.", "45")]
    rev = [_pair("コードNo.", "230"), _pair("ユニットNo.", "45")]

    matched = match_title_ul_pairs(ref, rev)
    paired = [(a, b) for a, b in matched if a and b]

    assert len(paired) == 1
    assert paired[0][1]["value"] == "45", "paired with the wrong column"


def test_unrelated_fields_still_do_not_cross_match():
    """The synonym table must not become a way for any two UL fields to pair. A field present
    on only one side is a genuine ADDED/REMOVED and has to stay one-sided."""
    matched = match_title_ul_pairs([_pair("ユニットNo.", "45")], [_pair("在庫棚入庫", "0")])

    assert len(matched) == 2
    assert all((a is None) != (b is None) for a, b in matched)


def test_canonicalisation_absorbs_punctuation_and_case():
    for variant in ("Part No.", "PART NO", "part  no.", "Ｐａｒｔ Ｎｏ."):
        token = next(iter(_title_ul_tokens(variant)))
        assert _ul_canonical(token) == "partno", f"{variant!r} did not canonicalise"


def test_synonym_groups_are_disjoint():
    """Overlapping groups would let two different columns pair through a shared member."""
    seen: set[str] = set()
    for group in _TITLE_UL_SYNONYMS:
        assert not (seen & group), f"{group} overlaps an earlier synonym group"
        seen |= group
