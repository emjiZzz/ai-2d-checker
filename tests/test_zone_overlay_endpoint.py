"""
Tests for the zone bounding-box overlay endpoint
(docs/zone-bbox-overlay-implementation-plan.md, Phase 5).

Two of these guard defects found while reviewing the original draft of that plan, both of
which would have shipped silently:

  - test_reserved_keys_are_not_treated_as_zones: extract_dynamic_regions() returns
    "safe_zones" (a list) and "_zone_confidence" (a dict) alongside the seven real zones.
    Iterating the dict instead of whitelisting keys feeds those into a bbox model.

  - test_llm_response_schema_has_no_open_ended_objects: the draft proposed hanging an
    Optional[dict] off PhysicalComparisonResponse, which gemini_client hands to Gemini as
    response_schema. A bare dict emits open-ended additionalProperties, which Gemini
    rejects with 400 INVALID_ARGUMENT on *every* request, not just populated ones.
"""
from types import SimpleNamespace

import pytest

from services.backend.api.routers.drawings import (
    ZONE_KEYS,
    build_zones_response,
)
from services.backend.api.schemas import PhysicalComparisonResponse
from services.backend.infrastructure.audit.bom.table_extractor import extract_dynamic_regions


def _regions(**overrides) -> dict:
    """A realistic extract_dynamic_regions() return value, reserved keys included."""
    base = {
        "views": (0.0, 0.0, 100.0, 100.0),
        "notes": (0.0, 100.0, 50.0, 150.0),
        "bom": (100.0, 100.0, 200.0, 200.0),
        "title": (150.0, 0.0, 200.0, 40.0),
        "tolerance": (0.0, 0.0, 200.0, 20.0),
        "iso": (140.0, 60.0, 200.0, 100.0),
        "title_upper_left": (0.0, 160.0, 60.0, 200.0),
        # Reserved keys: not zones, must never reach the wire model as boxes.
        "safe_zones": [(0.0, 0.0, 10.0, 10.0), (20.0, 20.0, 30.0, 30.0)],
        "_zone_confidence": {k: "content_aware" for k in ZONE_KEYS},
    }
    base.update(overrides)
    return base


def test_all_seven_zones_are_mapped():
    resp = build_zones_response("draw1", _regions(), [0.0, 0.0, 200.0, 200.0])

    for key in ZONE_KEYS:
        assert getattr(resp, key) is not None, f"zone {key} should be populated"
    assert resp.drawing_id == "draw1"
    assert resp.render_bounds == [0.0, 0.0, 200.0, 200.0]
    assert resp.bom.xmin == 100.0 and resp.bom.ymax == 200.0


def test_reserved_keys_are_not_treated_as_zones():
    """safe_zones (a list) and _zone_confidence (a dict) must not surface as boxes."""
    resp = build_zones_response("draw1", _regions(), None)

    serialized = resp.model_dump()
    assert "safe_zones" not in serialized
    assert "_zone_confidence" not in serialized
    # The wire model should expose exactly the seven zones plus the two scalars.
    assert set(serialized) == set(ZONE_KEYS) | {"drawing_id", "render_bounds"}


def test_confidence_is_passed_through_per_zone():
    regions = _regions(
        _zone_confidence={
            "views": "content_aware",
            "notes": "percentage_fallback",
            "bom": "content_aware",
            "title": "content_aware",
            "tolerance": "percentage_fallback",
            "iso": "percentage_fallback",
            "title_upper_left": "content_aware",
        }
    )
    resp = build_zones_response("draw1", regions, None)

    assert resp.views.confidence == "content_aware"
    assert resp.notes.confidence == "percentage_fallback"
    assert resp.iso.confidence == "percentage_fallback"


def test_no_sheet_bounds_confidence_survives_to_the_client():
    """The client refuses to draw on this value, so it must not be collapsed or renamed.

    When compute_drawing_bounds() finds nothing, extract_dynamic_regions() sets every zone
    to the literal (0, 0, 1000, 1000) placeholder. Those boxes describe no drawing at all,
    and rendering them puts seven identical rectangles near the origin — which reads as a
    broken overlay rather than as failed bounds detection. The frontend keys its
    suppression off this exact string.
    """
    placeholder = (0.0, 0.0, 1000.0, 1000.0)
    regions = _regions(
        **{k: placeholder for k in ZONE_KEYS},
        _zone_confidence={k: "percentage_fallback_no_sheet_bounds" for k in ZONE_KEYS},
    )
    resp = build_zones_response("draw1", regions, None)

    for key in ZONE_KEYS:
        assert getattr(resp, key).confidence == "percentage_fallback_no_sheet_bounds"


def test_missing_confidence_defaults_to_unknown():
    regions = _regions()
    del regions["_zone_confidence"]
    resp = build_zones_response("draw1", regions, None)

    assert resp.title.confidence == "unknown"


@pytest.mark.parametrize(
    "bad",
    [
        (1.0, 2.0, 3.0),           # too short
        (1.0, 2.0, 3.0, 4.0, 5.0), # too long
        ("a", "b", "c", "d"),      # not coercible
        None,                      # zone absent
        "not a tuple",
    ],
)
def test_malformed_zone_degrades_to_none_without_killing_the_others(bad):
    resp = build_zones_response("draw1", _regions(bom=bad), None)

    assert resp.bom is None
    assert resp.title is not None, "one bad zone must not take out the rest"


def _text(t: str, x: float, y: float):
    """Duck-typed stand-in for ExtractedEntity.

    zone_detector reads entities via getattr, and instantiating the real beanie Document
    raises CollectionWasNotInitialized without a live Mongo connection.
    """
    return SimpleNamespace(
        entity_type="text", layer="0", properties={"text": t}, geometry={"insert": [x, y]}
    )


def _line(x1: float, y1: float, x2: float, y2: float):
    return SimpleNamespace(
        entity_type="line", layer="0", properties={},
        geometry={"start": [x1, y1], "end": [x2, y2]},
    )


def _a3_sheet_entities() -> list:
    """An A3-ish sheet with enough anchor text for several zones to resolve content-aware."""
    return [
        _line(0, 0, 840, 0), _line(840, 0, 840, 594),
        _line(840, 594, 0, 594), _line(0, 594, 0, 0),
        _text("TOLERANCES UNLESS OTHERWISE SPECIFIED", 120, 40),
        _text("DRAWN BY", 600, 60), _text("SCALE", 660, 40), _text("1:2", 700, 40),
        _text("PARTS LIST", 640, 520), _text("QTY", 700, 500), _text("MATERIAL", 760, 500),
        _text("NOTES", 60, 400), _text("1. ALL DIMENSIONS IN MM", 60, 380),
    ]


def test_real_extract_dynamic_regions_output_maps_cleanly():
    """The whitelist is checked against the real function, not just a hand-built fixture.

    The other tests feed build_zones_response a dict written to look like
    extract_dynamic_regions' output, which only proves the mapping matches an assumption.
    This one runs the actual detector, so it also fails if a future change adds a new
    reserved key alongside safe_zones/_zone_confidence.
    """
    regions = extract_dynamic_regions(_a3_sheet_entities())

    # Sanity-check the assumption the whitelist exists to handle.
    assert "safe_zones" in regions and "_zone_confidence" in regions

    resp = build_zones_response("d1", regions, [0.0, 0.0, 840.0, 594.0])
    serialized = resp.model_dump()

    assert set(serialized) == set(ZONE_KEYS) | {"drawing_id", "render_bounds"}
    for key in ZONE_KEYS:
        assert getattr(resp, key) is not None
    # A realistic sheet resolves some zones by anchor and falls back on others; if every
    # zone reports the same path, the confidence plumbing is more likely broken than the
    # drawing perfect.
    assert {getattr(resp, k).confidence for k in ZONE_KEYS} == {
        "content_aware", "percentage_fallback"
    }


def test_real_detector_with_no_sheet_bounds_flags_every_zone_as_placeholder():
    """Text but no lines -> compute_drawing_bounds returns None -> all seven are (0,0,1000,1000).

    This is the state the frontend must refuse to draw: seven identical rectangles that
    describe no drawing at all. Asserted against the real detector so the client's
    suppression rule stays anchored to actual behavior.
    """
    regions = extract_dynamic_regions([_text("HELLO", 5, 5)])
    resp = build_zones_response("d2", regions, None)

    boxes = {
        (z.xmin, z.ymin, z.xmax, z.ymax)
        for z in (getattr(resp, k) for k in ZONE_KEYS)
    }
    assert boxes == {(0.0, 0.0, 1000.0, 1000.0)}
    assert {getattr(resp, k).confidence for k in ZONE_KEYS} == {
        "percentage_fallback_no_sheet_bounds"
    }


def test_llm_response_schema_has_no_open_ended_objects():
    """PhysicalComparisonResponse is handed to Gemini as response_schema (gemini_client.py).

    Implemented as a structural walk, NOT a substring search. The obvious version --
    `"additionalProperties" not in json.dumps(schema)` -- fails on a perfectly healthy
    schema, because ComparisonDiagnostics' docstring contains the word (explaining this
    very hazard) and pydantic emits docstrings as "description" strings.

    Caveat for anyone trusting a green run: this asserts against pydantic's JSON schema,
    which the Gemini SDK converts further. It is a proxy for what Gemini receives, not
    proof of acceptance.
    """
    schema = PhysicalComparisonResponse.model_json_schema()

    offenders: list[str] = []

    def walk(node, path="$"):
        if isinstance(node, dict):
            if "additionalProperties" in node:
                offenders.append(path)
            for key, value in node.items():
                walk(value, f"{path}.{key}")
        elif isinstance(node, list):
            for i, value in enumerate(node):
                walk(value, f"{path}[{i}]")

    walk(schema)

    assert not offenders, (
        "PhysicalComparisonResponse grew an open-ended object at: "
        f"{offenders}. Gemini rejects additionalProperties schemas with 400 "
        "INVALID_ARGUMENT on every request. Use fixed fields instead of a bare dict."
    )
