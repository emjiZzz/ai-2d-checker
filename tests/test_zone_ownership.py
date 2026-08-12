"""Zone ownership arbitration — who owns an entity when two zone boxes overlap.

Zones overlap by construction: `iso`'s quadrant prior (`x > 0.30w`, no y bound) strictly contains
`bom`'s, and `notes`' (`y > 0.15h`, no x bound) spans `title_upper_left`'s. Before
`zone_ownership.py` the answer lived in four separate exclusion lists and `notes` vs `iso` had no
rule at all.
"""

from services.backend.infrastructure.audit.bom.zone_detector import VIEWS_EXCLUDED_ZONES
from services.backend.infrastructure.audit.bom.zone_ownership import (
    ZONE_ORDER,
    ZONE_PRECEDENCE,
    exclusions_for,
    is_owned_by_other,
    owner_of,
    rank_of,
)


def _regions(**boxes):
    return dict(boxes)


# --- the order itself -------------------------------------------------------


def test_every_views_excluded_zone_is_arbitrated():
    """Anything `views` yields to must have a rank, or the two systems disagree silently."""
    assert set(VIEWS_EXCLUDED_ZONES) <= set(ZONE_ORDER)


def test_views_is_last_despite_having_the_best_drawn_border():
    """`views` scores the highest ruled-border IoU (0.97) and still loses to everyone: it is the
    drawing AREA, defined by exclusion, not a block."""
    assert ZONE_PRECEDENCE[-1] == ("views",)
    assert rank_of("views") == max(rank_of(z) for z in ZONE_ORDER)


def test_ruled_tables_outrank_the_zones_with_no_drawn_box():
    for strong in ("title", "tolerance", "bom", "shim"):
        for weak in ("title_upper_left", "notes", "iso"):
            assert rank_of(strong) < rank_of(weak), f"{strong} must outrank {weak}"


def test_title_upper_left_does_not_outrank_notes():
    """Regression on a measured mistake. Ranked above `notes` on its 0.62 border ceiling, its
    DETECTED box swallowed the notes block whole (31 texts at frac 1.00 over 6 of 12 corpus
    sides) and vetoing on it dropped notes_section recall to 0.54."""
    assert rank_of("title_upper_left") == rank_of("notes")


def test_an_unknown_key_is_not_a_zone():
    """`regions` carries reserved keys like `_zone_polygons`; none may become an owner."""
    assert rank_of("_zone_polygons") is None
    assert owner_of(5, 5, {"_zone_polygons": (0, 0, 10, 10)}) is None


# --- owner_of ---------------------------------------------------------------


def test_the_stronger_zone_owns_the_intersection():
    regions = _regions(tolerance=(0, 0, 10, 10), notes=(5, 5, 15, 15))
    assert owner_of(7, 7, regions) == "tolerance"
    assert owner_of(12, 12, regions) == "notes"
    assert owner_of(2, 2, regions) == "tolerance"


def test_a_point_in_no_zone_has_no_owner():
    assert owner_of(99, 99, _regions(notes=(0, 0, 10, 10))) is None


def test_candidates_narrows_the_search():
    regions = _regions(tolerance=(0, 0, 10, 10), notes=(0, 0, 10, 10))
    assert owner_of(5, 5, regions) == "tolerance"
    assert owner_of(5, 5, regions, candidates=["notes"]) == "notes"


def test_a_reshaped_zone_claims_only_what_its_outline_covers():
    """Content in a notch the user cut out of a zone must not be claimed by it — on the bounding
    box it would be excluded from the other pool too and land in no category at all."""
    regions = {
        "tolerance": (0, 0, 10, 10),
        "_zone_polygons": {"tolerance": [(0, 0), (10, 0), (10, 4), (0, 4)]},
        "notes": (0, 0, 10, 10),
    }
    assert owner_of(5, 2, regions) == "tolerance"
    assert owner_of(5, 8, regions) == "notes"


# --- peers ------------------------------------------------------------------


def test_notes_and_iso_do_not_evict_each_other():
    """The pair that had no rule anywhere. They tie because geometry genuinely cannot rank them
    — neither has a drawn box (IoU 0.08 / 0.06) — so the tie falls to content."""
    regions = _regions(notes=(0, 0, 10, 10), iso=(5, 5, 15, 15))
    assert not is_owned_by_other(7, 7, regions, "notes")
    assert not is_owned_by_other(7, 7, regions, "iso")


def test_title_upper_left_does_not_evict_a_note():
    regions = _regions(title_upper_left=(0, 0, 100, 100), notes=(0, 0, 10, 10))
    assert not is_owned_by_other(5, 5, regions, "notes")


def test_tolerance_does_evict_a_note():
    """The one case the notes classifier cannot decide on content: the tolerance block contains
    `必要な場合は、粗さ区分を記入のこと`, an instruction in the same form as a real note."""
    regions = _regions(tolerance=(0, 0, 100, 100), notes=(0, 0, 10, 10))
    assert is_owned_by_other(5, 5, regions, "notes")


def test_an_unranked_zone_is_never_evicted():
    assert not is_owned_by_other(5, 5, _regions(title=(0, 0, 10, 10)), "not_a_zone")


# --- exclusions_for ---------------------------------------------------------


def test_exclusions_are_the_zones_that_outrank_it_and_nothing_else():
    regions = _regions(
        title=(0, 0, 1, 1), tolerance=(1, 1, 2, 2), bom=(2, 2, 3, 3),
        title_upper_left=(3, 3, 4, 4), notes=(4, 4, 5, 5), iso=(5, 5, 6, 6),
        views=(0, 0, 9, 9),
    )
    boxes = {b for b, _outline in exclusions_for("notes", regions)}
    assert boxes == {(0, 0, 1, 1), (1, 1, 2, 2), (2, 2, 3, 3)}


def test_a_zone_never_excludes_itself_or_a_peer():
    regions = _regions(notes=(0, 0, 1, 1), iso=(1, 1, 2, 2), title_upper_left=(2, 2, 3, 3))
    assert exclusions_for("notes", regions) == []


def test_views_excludes_everything_present():
    regions = _regions(title=(0, 0, 1, 1), notes=(1, 1, 2, 2), iso=(2, 2, 3, 3))
    assert len(exclusions_for("views", regions)) == 3


def test_exclusions_carry_the_outline_alongside_the_box():
    regions = {
        "tolerance": (0, 0, 10, 10),
        "_zone_polygons": {"tolerance": [(0, 0), (10, 0), (10, 4), (0, 4)]},
    }
    (bbox, outline), = exclusions_for("notes", regions)
    assert bbox == (0, 0, 10, 10)
    assert outline == [(0, 0), (10, 0), (10, 4), (0, 4)]


def test_missing_zones_are_simply_absent():
    assert exclusions_for("notes", {}) == []
    assert exclusions_for("notes", None) == []


# --- subtract only what you will compare ------------------------------------


def test_a_zone_can_be_omitted_from_the_views_subtraction():
    """`views_exclusions(omit=...)` is how a zone stops subtracting its whole BOX from the
    shared pool, so it can subtract only the entities it actually claimed instead.

    Reported by the owner on M745227N01: `４ロール：１２（２×６台）` came out ADDED with no
    REMOVED counterpart on a sheet carrying it on both sides. The reference's copy sits 4.5
    units inside the `title_upper_left` box, which is subtracted from `views` — while the UL
    extractor had already rejected that row as not-a-values-row and never claimed it as a field.
    Claimed by the zone for exclusion, unclaimed by it for comparison, compared by nobody.

    **The rule: a zone may only take content out of the shared pool if it is going to compare
    it.** Everything else falls through to `views`, the drawing area, which is the right home
    for content no specialised pass wanted.
    """
    from services.backend.infrastructure.audit.bom.zone_detector import views_exclusions

    regions = _regions(
        title=(0, 0, 1, 1), notes=(1, 1, 2, 2), title_upper_left=(2, 2, 3, 3),
    )
    assert len(views_exclusions(regions)) == 3
    kept = {b for b, _outline in views_exclusions(regions, omit=("notes", "title_upper_left"))}
    assert kept == {(0, 0, 1, 1)}
