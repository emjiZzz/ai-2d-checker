"""Worksheet triage — grouping annotation rows by the guideline rule that covers them.

`tools/eval_corpus.py worksheet` used to hand the annotator two flat lists of every unmatched
string. Measured over the six loadable human pairs that is **507 rows, of which 322 can never be
findings** under the annotation guideline's own "What is *not* a finding" section — 82% of one
pair's list was surface-roughness reference data sitting in the `tolerance` safe zone.

The triage groups those under the rule that excludes them. The danger it introduces is the reason
for this file: a row wrongly grouped as "not a finding" is a miss the annotator never looks at,
and unmeasured misses are the exact quantity the corpus exists to produce. So the invariant is
one-directional — **triage may never exclude on uncertainty.**

Pure-function tests by design: the eval payloads are gitignored (see the `/storage/eval/` note in
`.gitignore`), so anything requiring a real pair cannot run in CI.
"""
import pytest

from tools.eval_corpus import (
    BUCKET_NO_ZONE,
    BUCKET_REVIEW,
    BUCKET_SAFE,
    SAFE_ZONES,
    triage_row,
    zone_containing,
    zones_containing,
)

# Modelled on the live REF template of M745203N01, including its real defect: `views` ends at
# y=268.0 and `bom` starts at y=275.8, leaving a ~7.8-unit unzoned sliver. A genuine dimensional
# change (`4.5x40x48` -> `4.5×40×52` at y=268.3) sits in that gap on the reference side while its
# counterpart lands inside `bom` on the revision side.
BOXES = {
    "title": (151.8, 10.1, 409.8, 54.6),
    "views": (37.2, 61.8, 400.5, 268.0),
    "tolerance": (25.1, 10.0, 151.9, 53.0),
    "bom": (199.7, 275.8, 409.5, 298.0),
}


def test_a_row_in_the_views_box_needs_review():
    assert triage_row(BOXES, [200.0, 150.0]) == (BUCKET_REVIEW, "views")


def test_a_row_in_a_safe_zone_is_grouped_out():
    """The guideline: "Safe zones are never compared… a difference inside one is not a finding.\""""
    bucket, zone = triage_row(BOXES, [40.0, 30.0])
    assert (bucket, zone) == (BUCKET_SAFE, "tolerance")
    assert zone in SAFE_ZONES


def test_a_row_in_no_zone_is_its_own_bucket_not_a_safe_one():
    """Out of scope, but for a different reason and with a different instruction.

    The guideline sends these to a zone-detection bug report rather than a label, so they must
    not be merged into the safe-zone pile — that pile is "confirm the grouping and move on",
    and this one is "look, because a mis-drawn template hides real changes here."
    """
    assert triage_row(BOXES, [241.1, 268.3])[0] == BUCKET_NO_ZONE


def test_no_template_sends_everything_to_review():
    """A pair whose template never got captured must be shown in full, not silently emptied."""
    assert triage_row({}, [40.0, 30.0]) == (BUCKET_REVIEW, None)


@pytest.mark.parametrize("anchor", [[], [5.0], None or []])
def test_an_unplaceable_entity_is_reviewed_not_excluded(anchor):
    """Uncertainty resolves toward the annotator, always.

    An entity with no usable coordinate cannot be shown to be in a safe zone, and "cannot be
    shown to be excluded" must never render as "excluded".
    """
    assert triage_row(BOXES, anchor) == (BUCKET_REVIEW, None)


def test_boxes_are_read_corner_order_agnostically():
    """The two sides of a pair resolve their fractions against different render_bounds, and a
    reference sheet may be stored in another coordinate space entirely, so corner order is not
    something this may assume."""
    flipped = {"tolerance": (152.0, 51.0, 25.0, 10.0)}
    assert zone_containing(flipped, [40.0, 30.0]) == "tolerance"


def test_boundaries_are_inclusive_so_an_edge_row_is_not_orphaned():
    assert zone_containing(BOXES, [25.1, 10.0]) == "tolerance"
    assert zone_containing(BOXES, [100.0, 53.0]) == "tolerance"


def test_overlapping_a_safe_zone_does_not_excuse_a_row_in_a_scored_one():
    """Hand-drawn zones overlap: on the live corpus `tolerance` ends at x=151.9 and `title`
    begins at x=151.8. Resolving that sliver by dict order would decide whether a row is
    excluded or reviewed on nothing at all, so a scored zone always wins."""
    overlap = [151.85, 30.0]
    assert set(zones_containing(BOXES, overlap)) == {"tolerance", "title"}
    assert triage_row(BOXES, overlap) == (BUCKET_REVIEW, "title")


def test_every_row_lands_in_exactly_one_bucket():
    """The no-loss invariant. The worksheet prints all three buckets, so a row reaching none of
    them would vanish from the annotator's document entirely."""
    anchors = [
        [200.0, 150.0], [40.0, 30.0], [241.1, 268.3], [300.0, 280.0],
        [200.0, 30.0], [-5.0, -5.0], [151.85, 30.0],
    ]
    buckets = {BUCKET_REVIEW, BUCKET_SAFE, BUCKET_NO_ZONE}
    seen = [triage_row(BOXES, a)[0] for a in anchors]
    assert all(b in buckets for b in seen)
    assert len(seen) == len(anchors)


def test_safe_zones_is_a_deliberate_allowlist():
    """`views`/`bom`/`title` must never join SAFE_ZONES — those carry the findings. This pins the
    set so widening it is a decision someone makes on purpose, against the guideline."""
    assert SAFE_ZONES == frozenset({"tolerance"})
