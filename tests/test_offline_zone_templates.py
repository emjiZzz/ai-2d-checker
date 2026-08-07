"""An offline run applies the corpus's zone template instead of degrading to detection.

`extract_dynamic_regions_async` resolves hand-aligned zone templates from Mongo. An offline
eval run has no Beanie session, so the lookup raised and the handler degraded to plain
detection -- right for an audit, wrong for a measurement, because the run then scored against
different zone boxes than the app uses and nothing said so.

The seam is the `zone_template` parameter, and its three states are what these tests pin:

    None -> resolve from Mongo   (the app; unchanged)
    {}   -> no pinned zones      (a captured answer, NOT a fall-through)
    {..} -> apply exactly these  (offline, no database)

See docs/vault/06 - .../Gotcha - Zone Templates Vanish in Offline Eval.
"""
import pytest

import services.backend.infrastructure.audit.bom.table_extractor as te
from services.backend.infrastructure.audit.bom.zone_template_resolver import (
    fractions_to_absolute_bbox,
    overrides_from_template_zones,
)
from services.backend.infrastructure.eval.corpus import CorpusPair, PairSide

RENDER_BOUNDS = [0.0, 0.0, 1000.0, 1000.0]
DETECTED_NOTES = (10.0, 10.0, 50.0, 50.0)
# Y-DOWN fractions, the way a template stores them.
TEMPLATE_ZONES = {"notes": {"xMin": 0.1, "xMax": 0.4, "yMin": 0.2, "yMax": 0.5}}


def _patch_detection(monkeypatch):
    monkeypatch.setattr(
        te,
        "extract_dynamic_regions",
        lambda entities: {"notes": DETECTED_NOTES, "_zone_confidence": {"notes": "keyword"}},
    )


def _forbid_db(monkeypatch) -> list[str]:
    """Make database resolution raise, the way an offline run does, and record attempts.

    Returns the attempt log. Asserting on it matters: the degradation handler swallows the
    exception and returns detection, so a test that only checks the *result* passes whether
    or not the database was reached. The log is what distinguishes "did not need the DB"
    from "tried the DB and quietly gave up".
    """
    import services.backend.infrastructure.audit.bom.zone_template_resolver as ztr

    attempts: list[str] = []

    async def boom(*_args, **_kwargs):
        attempts.append("db")
        raise RuntimeError("no Beanie session — this is what an offline run hits")

    monkeypatch.setattr(ztr, "resolve_zone_overrides", boom)
    return attempts


@pytest.mark.asyncio
async def test_supplied_template_is_applied_without_a_database(monkeypatch):
    """The whole point: offline, with the DB unreachable, the pinned box still wins."""
    _patch_detection(monkeypatch)
    attempts = _forbid_db(monkeypatch)

    regions = await te.extract_dynamic_regions_async(
        [], render_bounds=RENDER_BOUNDS, zone_template=TEMPLATE_ZONES
    )

    expected = fractions_to_absolute_bbox(TEMPLATE_ZONES["notes"], RENDER_BOUNDS)
    assert tuple(regions["notes"]) == tuple(expected)
    assert tuple(regions["notes"]) != DETECTED_NOTES
    assert attempts == [], "a supplied template must not consult the database at all"


@pytest.mark.asyncio
async def test_empty_template_is_an_answer_not_a_fall_through(monkeypatch):
    """`{}` must NOT send the engine back to the database.

    Collapsing `{}` into `None` (writing `if zone_template:` instead of `is not None`) would
    reintroduce the divergence for exactly the pairs that looked safe — the sheets a capture
    proved have no pinned template.

    The assertion is on the *attempt log*, not the result. Both implementations return the
    detected box here, because the degradation handler swallows the failure — so a
    result-only test would pass against the bug it is meant to catch.
    """
    _patch_detection(monkeypatch)
    attempts = _forbid_db(monkeypatch)

    regions = await te.extract_dynamic_regions_async(
        [], render_bounds=RENDER_BOUNDS, zone_template={}
    )

    assert attempts == [], "`{}` means 'no pinned zones', not 'go and look'"
    assert tuple(regions["notes"]) == DETECTED_NOTES


@pytest.mark.asyncio
async def test_none_still_resolves_from_the_database(monkeypatch):
    """The app's path is untouched: no template supplied means look one up."""
    _patch_detection(monkeypatch)
    called: list[str] = []

    async def fake_resolve(render_bounds, signature=None):
        called.append("db")
        return {"notes": (600.0, 600.0, 700.0, 700.0)}

    monkeypatch.setattr(te, "extract_dynamic_regions", lambda e: {
        "notes": DETECTED_NOTES, "_zone_confidence": {"notes": "keyword"}
    })
    import services.backend.infrastructure.audit.bom.zone_template_resolver as ztr
    monkeypatch.setattr(ztr, "resolve_zone_overrides", fake_resolve)

    regions = await te.extract_dynamic_regions_async([], render_bounds=RENDER_BOUNDS)

    assert called == ["db"], "None must still hit the database — the app depends on it"
    assert tuple(regions["notes"]) == (600.0, 600.0, 700.0, 700.0)


@pytest.mark.asyncio
async def test_a_degraded_lookup_is_still_non_fatal_for_the_app(monkeypatch):
    """An audit must not fail because a template lookup broke. Only the eval seam changed."""
    _patch_detection(monkeypatch)
    attempts = _forbid_db(monkeypatch)

    regions = await te.extract_dynamic_regions_async([], render_bounds=RENDER_BOUNDS)

    assert attempts == ["db"]
    assert tuple(regions["notes"]) == DETECTED_NOTES


def test_the_seam_takes_fractions_so_the_y_flip_stays_under_test():
    """Fractions, not resolved boxes — deliberately.

    Handing the engine pre-resolved boxes would bypass `fractions_to_absolute_bbox`, whose
    failure mode is a plausible-looking vertically mirrored zone. The offline path has to
    exercise the same conversion the app does, or the eval goes blind to a regression in it.
    """
    overrides = overrides_from_template_zones(TEMPLATE_ZONES, RENDER_BOUNDS)
    x0, y0, x1, y1 = overrides["notes"]

    # yMin=0.2 is measured DOWN from the top (y=1000), so the box sits high, not low.
    assert (y0, y1) == (500.0, 800.0), "the Y flip must survive the offline path"
    assert (x0, x1) == (100.0, 400.0)


def test_capture_state_comes_from_the_signature_map_not_a_per_side_copy():
    """A template is a property of the sheet layout, so it is stored once per signature.

    Every pair in this corpus is one layout; a per-side copy wrote the identical block 74
    times and buried a manifest that is required to stay reviewable. Presence in the map is
    the single source of "captured", which is why `{}` (asked, and the answer is none) stays
    distinguishable from absent (never asked) with no second flag to fall out of step.
    """
    raw = {
        "drawing_id": "d", "file_name": "f", "file_hash": "h",
        "drawing_sha256": "", "entities_sha256": "", "entity_count": 0,
        "zone_signature": "aspect-1.414",
    }

    # No map at all -> no capture information -> back to the database.
    assert PairSide.from_dict(raw).zone_template is None
    # A map that does not mention this sheet -> still never captured.
    assert PairSide.from_dict(raw, {"aspect-9.999": TEMPLATE_ZONES}).zone_template is None
    # Captured, and the sheet genuinely has nothing pinned.
    assert PairSide.from_dict(raw, {"aspect-1.414": {}}).zone_template == {}
    # Captured, with zones.
    assert (
        PairSide.from_dict(raw, {"aspect-1.414": TEMPLATE_ZONES}).zone_template
        == TEMPLATE_ZONES
    )

    # The fractions are NOT written back per side — that is what keeps the manifest small.
    assert "zone_template" not in PairSide.from_dict(raw).to_dict()


def test_only_an_uncaptured_side_is_reported_as_a_risk():
    """`verify` must stop warning once a sheet's boxes are reproducible offline."""
    def pair(zone_templates):
        raw = {
            "drawing_id": "d", "file_name": "f", "file_hash": "h",
            "drawing_sha256": "", "entities_sha256": "", "entity_count": 0,
            "zone_signature": "aspect-1.414",
        }
        return CorpusPair(
            pair_id="p", provenance="mutation", held_out=False, label_state="unlabelled",
            ref=PairSide.from_dict(raw, zone_templates),
            rev=PairSide.from_dict(raw, zone_templates),
        )

    assert pair(None).zone_template_risk() == ["aspect-1.414"]
    assert pair(None).uncaptured_zone_sides() == ["ref", "rev"]
    # Proved to have no template: the question was asked and answered, so it is not a risk.
    assert pair({"aspect-1.414": {}}).zone_template_risk() == []
    assert pair({"aspect-1.414": TEMPLATE_ZONES}).zone_template_risk() == []
