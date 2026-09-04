"""The test that decides whether ground-truth markings are worth collecting.

A marking outlives the extraction it was made against. `ExtractionPipeline.run` deletes and
re-inserts a drawing's entities (`extraction_pipeline.py`, "Re-extraction: cleared N existing
entities"), so every `ExtractedEntity` gets a fresh ObjectId on re-extraction —
`EXTRACTION_SCHEMA_VERSION` is at 6, meaning that has already happened six times for reasons
having nothing to do with this feature.

So a marking that stored an entity id would dangle the first time anyone ran
`POST /drawings/{id}/reextract`, and it would dangle silently: the marking still reads
perfectly, it just no longer points at anything. Nobody would find out until the dataset was
used, by which point the labelling effort is unrecoverable.

Every test below simulates a re-extraction the only way that matters — by building a *second,
entirely separate* set of entity objects and resolving the address captured from the first
against it. If the resolver can still find the entity, the address is durable. If it cannot,
the data collected by this feature has a shelf life, and that is worth knowing on day one.

The second theme here is the one that makes a dataset *wrong* rather than merely incomplete:
the resolver must never guess. An unresolved marking is a countable gap. A mis-resolved one
attributes a human's judgement to the wrong entity, and nothing downstream can detect it. The
`_never_guesses` tests pin that boundary from both sides.
"""

import pytest

from services.backend.domain.models.ground_truth import EntityAddress
from services.backend.infrastructure.ground_truth.address_resolver import (
    COORDINATE_TOLERANCE,
    MatchTier,
    resolve,
)


class FakeEntity:
    """An `ExtractedEntity` as the resolver sees it.

    Deliberately not the Beanie document: the resolver takes a plain sequence so it can be
    tested without a database, and constructing the real `Document` here would test Beanie
    rather than the resolution rules. The attribute names are copied from
    `domain/models/extracted_entity.py` and `test_extracted_entity_shape_is_mirrored` below
    fails if they drift apart.
    """

    def __init__(
        self,
        entity_type="text",
        layer="0",
        handle=None,
        parent_handle=None,
        text="",
        point=(0.0, 0.0),
        geometry_key="insert",
    ):
        self.entity_type = entity_type
        self.layer = layer
        self.handle = handle
        self.parent_handle = parent_handle
        self.properties = {"text": text} if text else {}
        self.geometry = {geometry_key: [point[0], point[1], 0.0]} if point else {}


def address(**kwargs) -> EntityAddress:
    base = dict(drawing_id="drw1", entity_type="text", layer="0", text="")
    point = kwargs.pop("point", None)
    base.update(kwargs)
    addr = EntityAddress(**base)
    if point is not None:
        addr = EntityAddress(**{**base, "point": {"x": point[0], "y": point[1]}})
    return addr


# ── the round trip: mark, re-extract, resolve ────────────────────────────────────────


def test_a_handle_survives_re_extraction():
    """The easy case, and the reason `handle` is tier 1.

    A DXF handle is written by the CAD application into the source file, so re-parsing the same
    file yields the same handle on a completely new document. This is the only tier that is
    *guaranteed* rather than merely probable.
    """
    before = [FakeEntity(handle="1B2A", text="60", point=(10.0, 20.0))]
    addr = address(handle="1B2A", text="60", point=(10.0, 20.0))

    # Re-extraction: new objects, no shared identity with `before` at all.
    after = [
        FakeEntity(handle="9FF", text="unrelated", point=(1.0, 1.0)),
        FakeEntity(handle="1B2A", text="60", point=(10.0, 20.0)),
    ]

    assert resolve(addr, before).tier is MatchTier.HANDLE
    result = resolve(addr, after)
    assert result.ok
    assert result.tier is MatchTier.HANDLE
    assert result.entity is after[1]


def test_a_block_exploded_child_resolves_by_parent_handle():
    """The case that actually decides this feature's viability.

    Handle and `parent_handle` are mutually exclusive — anything exploded out of a block carries
    no handle of its own — and this client's *reference* sheets keep almost everything inside
    blocks. Text-entity handle coverage there is 0.8–13%, and the reference side is where a
    REMOVED must anchor. If this test fails, most REMOVED markings are unaddressable.
    """
    addr = address(parent_handle="AA1", text="0.67", point=(5.0, 5.0))

    after = [
        FakeEntity(parent_handle="BB2", text="0.67", point=(5.0, 5.0)),  # same text, other block
        FakeEntity(parent_handle="AA1", text="0.71", point=(6.0, 5.0)),  # same block, other text
        FakeEntity(parent_handle="AA1", text="0.67", point=(5.0, 5.0)),  # the one
    ]

    result = resolve(addr, after)
    assert result.ok
    assert result.tier is MatchTier.PARENT_HANDLE
    assert result.entity is after[2]


def test_text_alone_resolves_when_it_is_unambiguous():
    addr = address(text="指示なき角部は糸面取りのこと", point=(100.0, 200.0))
    after = [
        FakeEntity(text="完成時、バリ、キリ粉はなきこと", point=(100.0, 190.0)),
        FakeEntity(text="指示なき角部は糸面取りのこと", point=(100.0, 200.0)),
    ]

    result = resolve(addr, after)
    assert result.ok
    assert result.tier is MatchTier.TEXT
    assert result.entity is after[1]


def test_geometry_with_no_text_resolves_by_coordinate():
    """A line inside an isometric view — the case the corpus most needs and text cannot serve.

    Both human pairs in the eval corpus add an isometric view, and both hold zero text or
    dimension entities in the `iso` box. The only thing an engineer can anchor such a finding to
    is geometry, which carries no text at all.
    """
    addr = address(entity_type="line", text="", point=(42.0, 17.0))
    after = [
        FakeEntity(entity_type="line", text="", point=(80.0, 80.0), geometry_key="start"),
        FakeEntity(entity_type="line", text="", point=(42.0, 17.0), geometry_key="start"),
    ]

    result = resolve(addr, after)
    assert result.ok
    assert result.tier is MatchTier.COORDINATE
    assert result.entity is after[1]


def test_normalisation_matches_the_engine_not_a_second_opinion():
    """Full-width and half-width forms of one string are the same entity.

    The resolver calls `SpatialDiffer._normalize_text` rather than restating the rule. Committed
    labels are full of exactly this: `M745230A01.json` carries `"３－９キリ１４ザグリ深サ１０"`
    beside half-width text on the other side. A second normalisation here would produce
    unresolvable markings that look identical to genuinely-removed entities.
    """
    addr = address(text="Dia 25", point=(0.0, 0.0))
    after = [FakeEntity(text="ø25", point=(0.0, 0.0))]

    result = resolve(addr, after)
    assert result.ok, "engine normalisation folds 'Dia 25' and 'ø25'; the resolver must agree"
    assert result.tier is MatchTier.TEXT


# ── the resolver must never guess ────────────────────────────────────────────────────


def test_never_guesses_when_text_is_ambiguous_and_position_is_far():
    """Two entities share the text and neither is near the stored point. Report nothing.

    Returning either one would attribute the engineer's judgement to an entity they never
    looked at, and no downstream consumer could tell. Losing the marking is the cheaper failure.
    """
    addr = address(text="20", point=(0.0, 0.0))
    far = COORDINATE_TOLERANCE * 100
    after = [
        FakeEntity(text="20", point=(far, far)),
        FakeEntity(text="20", point=(far + 1, far)),
    ]

    result = resolve(addr, after)
    assert not result.ok
    assert result.tier is MatchTier.UNRESOLVED


def test_ambiguous_text_is_broken_by_position_when_position_is_close():
    """The other side of the same boundary: a tie *is* resolvable when the point decides it."""
    addr = address(text="20", point=(50.0, 50.0))
    after = [
        FakeEntity(text="20", point=(50.0, 50.0)),
        FakeEntity(text="20", point=(900.0, 900.0)),
    ]

    result = resolve(addr, after)
    assert result.ok
    assert result.tier is MatchTier.COORDINATE
    assert result.entity is after[0]


def test_a_missing_handle_means_removed_not_stale():
    """A stored handle absent from the drawing must not fall through to text matching.

    The entity is genuinely gone — that is what a REMOVED *means*, and it is a legitimate state
    for a marking to be in. Searching on by text would find a different entity that happens to
    share the string and silently rebind the marking to it.
    """
    addr = address(handle="1B2A", text="60", point=(10.0, 20.0))
    after = [FakeEntity(handle="C0FF", text="60", point=(10.0, 20.0))]

    result = resolve(addr, after)
    assert not result.ok
    assert result.tier is MatchTier.UNRESOLVED


def test_type_and_layer_must_agree():
    """Same text on a different layer, or as a different type, is a different entity."""
    addr = address(text="60", layer="DIMS", point=(0.0, 0.0))
    after = [
        FakeEntity(text="60", layer="NOTES", point=(0.0, 0.0)),
        FakeEntity(text="60", layer="DIMS", entity_type="dimension", point=(0.0, 0.0)),
    ]

    assert not resolve(addr, after).ok


def test_an_empty_drawing_resolves_nothing_rather_than_raising():
    assert resolve(address(handle="1B2A"), []).tier is MatchTier.UNRESOLVED


# ── the fake must not drift from the real document ───────────────────────────────────


def test_extracted_entity_shape_is_mirrored():
    """`FakeEntity` stands in for `ExtractedEntity`; pin that it still can.

    A test double that has quietly stopped matching the real model tests nothing. This repo has
    already paid for exactly that once — a `MockEntity` lacking `layer` kept two OCR-grounding
    tests failing for months under a "pre-existing" label.
    """
    from services.backend.domain.models.extracted_entity import ExtractedEntity

    fields = set(ExtractedEntity.model_fields)
    for attr in ("entity_type", "layer", "handle", "parent_handle", "properties", "geometry"):
        assert attr in fields, f"FakeEntity mirrors `{attr}`, which ExtractedEntity no longer has"
        assert hasattr(FakeEntity(), attr), f"FakeEntity has stopped mirroring `{attr}`"


# -- the click is not the anchor ------------------------------------------------------


def _line(start, end, layer="0"):
    """A LINE with both endpoints, which `FakeEntity`'s single-point geometry cannot express."""
    entity = FakeEntity(entity_type="line", text="", point=None)
    entity.geometry = {"start": [start[0], start[1], 0.0], "end": [end[0], end[1], 0.0]}
    return entity


def _circle(center, radius, layer="0"):
    entity = FakeEntity(entity_type="circle", text="", point=None)
    entity.geometry = {"center": [center[0], center[1], 0.0], "radius": radius}
    return entity


def test_a_click_on_a_line_resolves_to_that_line_not_to_a_stranger_near_its_anchor():
    """The defect this pins is a *confidently* wrong answer, which is the worst kind here.

    `EntityAddress.point` is where the engineer clicked -- `useEntityPicking` sends the pointer
    position verbatim. Tier 4 used to compare that against `_entity_point`, the entity's
    canonical ANCHOR (`start` for a line). Those are different quantities, and for a line they
    diverge without limit.

    So clicking the middle of a long line put the click 400 units from that line's own `start`:
    the entity the engineer actually picked failed `COORDINATE_TOLERANCE` and was not even a
    candidate, while `stranger` -- an unrelated line that merely begins near the click -- was
    returned instead. Measured on the real corpus 2026-08-20, one such click resolved to the
    wrong line at distance 0.0, the strongest possible match.

    Distance is now measured to the geometry the entity DRAWS, so a click lands on what it
    selected, which is what selecting something means.
    """
    clicked = _line((0.0, 0.0), (800.0, 0.0))
    stranger = _line((400.5, 0.5), (400.5, 100.0))
    far = _line((0.0, 500.0), (800.0, 500.0))

    result = resolve(address(entity_type="line", text="", point=(400.0, 0.0)),
                     [stranger, far, clicked])

    assert result.ok
    assert result.tier is MatchTier.COORDINATE
    assert result.entity is clicked, "resolved to the line whose anchor was near the click"


def test_a_click_on_a_circle_measures_to_its_outline_not_its_centre():
    """You select a circle by clicking the curve; its centre is empty paper.

    Anchoring on `center` meant a large circle's own click point was `radius` away from its
    anchor -- out of tolerance -- while anything sitting at the centre won instead.
    """
    clicked = _circle((0.0, 0.0), 50.0)
    at_the_centre = _circle((50.0, 0.0), 200.0)

    result = resolve(address(entity_type="circle", text="", point=(50.0, 0.0)),
                     [at_the_centre, clicked])

    assert result.ok
    assert result.entity is clicked


def test_coincident_geometry_is_refused_rather_than_broken_by_payload_order():
    """Two entities the address cannot tell apart must resolve to nothing.

    Ranking by `<` alone returned whichever came first in the payload -- a guess wearing the
    costume of a measurement, and one that no downstream check could detect. Measured across
    the eight human pairs: 101 of 1737 coordinate-tier resolutions were ambiguous and order
    got 44 of them wrong.

    Refusing also costs the ones order happened to get right. That is the trade
    `address_resolver`'s module docstring already committed to.
    """
    # Both lines BEGIN at the click, so they are indistinguishable under the old anchor rule
    # and under the new geometry rule alike -- which is the point. The address carries nothing
    # that separates them, so there is no answer to give.
    result = resolve(
        address(entity_type="line", text="", point=(400.0, 0.0)),
        [_line((400.0, 0.0), (800.0, 0.0)), _line((400.0, 0.0), (400.0, 900.0))],
    )

    assert not result.ok
    assert result.tier is MatchTier.UNRESOLVED


def test_a_click_beyond_tolerance_still_resolves_to_nothing():
    """Measuring to the geometry widens what tier 4 can *reach*; it must not widen how far.

    Without this, "distance to the drawn geometry" could quietly turn `COORDINATE_TOLERANCE`
    into a hit radius around an entire 800-unit line rather than around a point.
    """
    result = resolve(
        address(entity_type="line", text="", point=(400.0, COORDINATE_TOLERANCE * 10)),
        [_line((0.0, 0.0), (800.0, 0.0))],
    )

    assert not result.ok


@pytest.mark.parametrize("tier", list(MatchTier))
def test_every_tier_is_reachable_in_this_file(tier):
    """A tier nothing exercises is a tier nothing checks.

    `PARENT_HANDLE`, `TEXT`, `COORDINATE`, `HANDLE` and `UNRESOLVED` each have a test above; this
    fails loudly if a new tier is added to the resolver without one.
    """
    covered = {
        MatchTier.HANDLE,
        MatchTier.PARENT_HANDLE,
        MatchTier.TEXT,
        MatchTier.COORDINATE,
        MatchTier.UNRESOLVED,
    }
    assert tier in covered, f"{tier} has no test in this file"
