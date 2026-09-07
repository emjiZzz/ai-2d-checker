"""Claim only what can be compared — and never release a value nothing will catch.

The owner's rule, verbatim: *"If that value was inside the zone box but no another value to
compare then leave it, some zone box view might be the one who needs it."*

The reason it matters is measured. On `M745227N01` an over-reaching `title_upper_left` box put a
production-count note inside the table, `extract_title_ul_kv` claimed it as a field value, and
that produced TWO false findings: a CHANGED against the revision's genuine `16組`, and an ADDED
for a line the reference plainly has — because claiming a value also feeds
`_collect_structured_text_values`, which suppresses that text sheet-wide and stops the zone that
really owns it from reporting it.

The dangerous half is the release itself. `title_upper_left` is in `VIEWS_EXCLUDED_ZONES`, so
content inside that box is subtracted from the `views` pool and no other pass is scoped to it.
Releasing a value that no other zone covers deletes it from the comparison entirely — a silent
false negative, the one failure mode this system cannot detect. So release is conditional on
another zone's shape actually covering the value.
"""

from services.backend.infrastructure.audit.comparison.orchestrator import partition_ul_pairs


def _p(key, value, coords=(10.0, 20.0)):
    return {"key": key, "value": value, "coords": list(coords)}


NEVER = lambda *_args: False          # noqa: E731 - nothing corroborates / nothing covers
ALWAYS = lambda *_args: True          # noqa: E731


def test_two_sided_values_are_always_comparable():
    matched = [(_p("T. Q'ty", "16組"), _p("T. Q'ty", "16組"))]
    comparable, released = partition_ul_pairs(
        matched, corroborates=NEVER, covered_by_another_zone=NEVER
    )
    assert comparable == matched
    assert released == []


def test_a_one_sided_value_the_other_side_actually_has_stays_comparable():
    """Mis-extracted, not changed. The emit loop's corroboration guard turns this into MATCHED,
    which is a comparison — so it must not be released."""
    matched = [(_p("Unit No.", "45"), None)]
    comparable, released = partition_ul_pairs(
        matched, corroborates=ALWAYS, covered_by_another_zone=ALWAYS
    )
    assert comparable == matched
    assert released == []


def test_an_unpairable_value_another_zone_covers_is_released():
    """The reported case: a note that drifted into the UL box, with `notes` covering it on its
    own side. Released so the notes pass compares it against its real counterpart."""
    note = _p("T. Q'ty / 総製作個数", "4 ロール：12 (2x6台)", coords=(179.23, 767.5))
    comparable, released = partition_ul_pairs(
        [(note, None)], corroborates=NEVER, covered_by_another_zone=ALWAYS
    )
    assert comparable == []
    assert released == [note]


def test_an_unpairable_value_nothing_covers_is_still_reported():
    """The safety property, and the reason this is not just `if unpaired: drop`.

    With no other zone over it, releasing would remove the value from every pool — `views`
    subtracts the UL box and no other pass is scoped to it. A one-sided report is wrong-ish;
    a silent deletion is undetectable. Reporting wins.
    """
    orphan = _p("Stock Q'ty", "0")
    comparable, released = partition_ul_pairs(
        [(orphan, None)], corroborates=NEVER, covered_by_another_zone=NEVER
    )
    assert comparable == [(orphan, None)]
    assert released == []


def test_it_asks_the_side_that_is_missing_the_value():
    """A corroboration search aimed at the side that already has the value would always
    succeed, which would make rung 2 vacuous and nothing would ever be released."""
    asked: list = []

    def record(value, missing_side):
        asked.append((value, missing_side))
        return False

    partition_ul_pairs(
        [(_p("Unit No.", "45"), None), (None, _p("Part No.", "227"))],
        corroborates=record,
        covered_by_another_zone=NEVER,
    )
    assert asked == [("45", "rev"), ("227", "ref")]


def test_it_checks_coverage_on_the_side_the_value_came_from():
    """The two sheets have different zone geometry — different exporters, ~3x apart in
    coordinate scale — so asking the wrong side's regions is asking about a different sheet."""
    seen: list = []

    def record(coords, side):
        seen.append((tuple(coords or ()), side))
        return False

    partition_ul_pairs(
        [(_p("A", "x", coords=(1.0, 2.0)), None), (None, _p("B", "y", coords=(3.0, 4.0)))],
        corroborates=NEVER,
        covered_by_another_zone=record,
    )
    assert seen == [((1.0, 2.0), "ref"), ((3.0, 4.0), "rev")]


def test_a_pair_with_no_value_on_either_side_is_left_alone():
    comparable, released = partition_ul_pairs(
        [(_p("Empty", ""), _p("Empty", None))],
        corroborates=NEVER, covered_by_another_zone=ALWAYS,
    )
    assert len(comparable) == 1
    assert released == []


def test_mixed_batch_keeps_the_comparable_ones_and_their_order():
    both = (_p("T. Q'ty", "16組"), _p("T. Q'ty", "16組"))
    # Distinct coordinates, because the coverage question is asked about a POINT: giving these
    # two the same default made the discriminator below match both and released the orphan.
    note = _p("T. Q'ty / 総製作個数", "4 ロール：12 (2x6台)", coords=(179.23, 767.5))
    orphan = _p("Stock Q'ty", "0", coords=(283.29, 822.0))
    comparable, released = partition_ul_pairs(
        [both, (note, None), (orphan, None)],
        corroborates=NEVER,
        covered_by_another_zone=lambda coords, side: coords == note["coords"],
    )
    assert comparable == [both, (orphan, None)]
    assert released == [note]
