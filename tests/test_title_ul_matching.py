"""Tests for title-upper-left field matching across a drawing pair.

The upper-left metadata table (Unit No. / Part No. / T. Q'ty / Stock Q'ty) has stacked
English + Japanese header labels. `extract_title_ul_kv` bands the table rows by a fixed
y-threshold, so a large-coordinate drawing splits the two header rows into separate bands
(key becomes 'Unit No. / ユニットNo.') while a small-coordinate one merges them (key becomes
just 'Unit No.'). The same field then carried DIFFERENT combined keys on the two drawings, and
the old exact-combined-key match reported every identical value as REMOVED + ADDED at once.
`match_title_ul_pairs` pairs the field on any shared header token instead.
"""
from services.backend.infrastructure.audit.comparison.orchestrator import (
    _title_ul_tokens,
    match_title_ul_pairs,
)


def _pair(key, value):
    return {"key": key, "value": value, "coords": [0.0, 0.0]}


def test_tokens_split_combined_key_on_slash():
    assert _title_ul_tokens("Unit No. / ユニットNo.") == {"unit no.", "ユニットno."}
    assert _title_ul_tokens("Unit No.") == {"unit no."}


def test_same_field_pairs_despite_different_combined_keys():
    """The measured KEMCO case: the reference carries both stacked labels, the revision only
    one, for every field. Each must pair, so identical values compare MATCHED, not REMOVED +
    ADDED. Stock Q'ty is the case where the revision kept the *Japanese* label."""
    ref = [
        _pair("Unit No. / ユニットNo.", "45"),
        _pair("Part No. / コードNo.", "227"),
        _pair("T. Q'ty / 総製作個数", "16組"),
        _pair("Stock Q'ty / 在庫棚入庫", "0"),
    ]
    rev = [
        _pair("Unit No.", "45"),
        _pair("Part No.", "227"),
        _pair("T. Q'ty", "16組"),
        _pair("在庫棚入庫", "0"),  # revision kept the Japanese label for this one
    ]

    matched = match_title_ul_pairs(ref, rev)

    # Every field pairs two-sided; nothing is left one-sided.
    assert len(matched) == 4
    assert all(r is not None and v is not None for r, v in matched)
    for r, v in matched:
        assert r["value"] == v["value"]


def test_genuinely_added_field_stays_one_sided():
    """A field present only on the revision must remain unmatched (a real ADDED), not be
    force-paired to an unrelated reference field."""
    ref = [_pair("Unit No. / ユニットNo.", "45")]
    rev = [_pair("Unit No.", "45"), _pair("Stock Q'ty", "0")]

    matched = match_title_ul_pairs(ref, rev)

    unit = [(r, v) for r, v in matched if v and v["value"] == "45"][0]
    assert unit[0] is not None  # paired
    stock = [(r, v) for r, v in matched if v and v["value"] == "0"][0]
    assert stock[0] is None  # one-sided -> genuinely added


def test_unrelated_fields_do_not_cross_match():
    """Different fields share no header token, so they never pair with each other."""
    ref = [_pair("Unit No.", "45")]
    rev = [_pair("Part No.", "99")]

    matched = match_title_ul_pairs(ref, rev)

    assert len(matched) == 2  # one ref-only, one rev-only
    assert all((r is None) != (v is None) for r, v in matched)  # each strictly one-sided
