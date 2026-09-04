"""Phase 4: the queryable entity index.

The substrate for two things: entity-grounded AI findings (the model cites a handle
instead of a normalized visual bbox that has to be back-projected and sanity-checked),
and a future deterministic rules engine (predicates over the same entities).
"""

import pytest

from services.backend.infrastructure.audit.entity_index import (
    DEFAULT_MANIFEST_LIMIT,
    SIDE_REFERENCE,
    SIDE_REVISION,
    EntityIndex,
    Region,
    build_comparison_indexes,
    entity_handle,
    entity_text,
)


class FakeEntity:
    """Mirrors the ExtractedEntity surface the index reads."""

    def __init__(self, handle=None, entity_type="text", layer="0", text="", insert=(0.0, 0.0), bbox=None, promoted=True):
        self.entity_type = entity_type
        self.layer = layer
        self.geometry = {"insert": [insert[0], insert[1], 0.0]}
        self.properties = {"text": text, "height": 3.0}
        if handle:
            self.properties["handle"] = handle
            if promoted:
                # Phase 1 promoted `handle` to an indexed top-level field.
                self.handle = handle
        if bbox:
            self.properties["bbox"] = bbox


@pytest.fixture
def index() -> EntityIndex:
    return EntityIndex(
        [
            FakeEntity("A1", "text", "TITLE", "DWG-12345", (10, 10)),
            FakeEntity("A2", "text", "TITLE", "SCALE 1:10", (10, 20)),
            FakeEntity("B1", "dimension", "DIM", "45.5", (100, 100)),
            FakeEntity("B2", "dimension", "DIM", "R3", (120, 100)),
            FakeEntity("C1", "line", "GEOM", "", (50, 50)),
            FakeEntity("C2", "circle", "GEOM", "", (60, 60)),
            FakeEntity(None, "text", "NOTES", "no handle here", (5, 5)),
        ],
        side=SIDE_REVISION,
    )


# --------------------------------------------------------------------------
# Handle addressing
# --------------------------------------------------------------------------

def test_handle_resolves_with_or_without_prefix(index):
    """The model is asked to cite `REV-A1`; other paths pass a bare `A1`. Both work --
    that normalisation currently lives inline in two places in coordinate_resolver."""
    assert index.by_handle("REV-A1") is not None
    assert index.by_handle("A1") is index.by_handle("REV-A1")
    assert entity_text(index.by_handle("A1")) == "DWG-12345"


def test_wrong_side_prefix_does_not_resolve(index):
    """A REF handle must not silently resolve against the revision drawing. A
    comparison holds two drawings at once, so a bare handle is ambiguous between
    them -- that ambiguity is exactly why handles are namespaced."""
    assert index.by_handle("REF-A1") is None


def test_missing_and_malformed_handles(index):
    assert index.by_handle(None) is None
    assert index.by_handle("") is None
    assert index.by_handle("NOPE") is None


def test_handles_are_namespaced_by_side(index):
    assert "REV-A1" in index.handles
    assert "REF-A1" not in index.handles


def test_entity_handle_reads_promoted_field_or_properties():
    promoted = FakeEntity("X1", promoted=True)
    legacy = FakeEntity("X2", promoted=False)
    assert entity_handle(promoted) == "X1"
    assert entity_handle(legacy) == "X2", "must fall back to the properties blob"
    assert entity_handle(FakeEntity(None)) is None


def test_build_comparison_indexes_namespaces_both_sides():
    ref, rev = build_comparison_indexes([FakeEntity("A1")], [FakeEntity("A1")])
    assert ref.side == SIDE_REFERENCE and rev.side == SIDE_REVISION
    assert ref.by_handle("A1") is not None
    assert rev.by_handle("A1") is not None
    assert ref.by_handle("A1") is not rev.by_handle("A1"), "sides must not collide"


def test_duplicate_handles_do_not_raise():
    """Exploded block children legitimately reuse their source handle."""
    idx = EntityIndex([FakeEntity("D1", text="first"), FakeEntity("D1", text="second")])
    assert len(idx) == 2
    assert idx.by_handle("D1") is not None


# --------------------------------------------------------------------------
# Query surface -- what a rules engine would run predicates through
# --------------------------------------------------------------------------

def test_query_by_entity_type(index):
    assert len(index.query(entity_type="dimension")) == 2
    assert len(index.query(entity_type=["text", "dimension"])) == 5


def test_query_by_layer(index):
    assert len(index.query(layer="TITLE")) == 2
    assert len(index.query(layer=["TITLE", "DIM"])) == 4


def test_query_by_text(index):
    assert len(index.query(text_contains="scale")) == 1, "should be case-insensitive"
    assert len(index.query(text_regex=r"^R\d+$")) == 1


def test_invalid_regex_is_ignored_not_fatal(index):
    assert index.query(text_regex="[unclosed") == index.query()


def test_query_by_region(index):
    near_origin = index.query(region=(0, 0, 30, 30))
    assert all(e.layer in ("TITLE", "NOTES") for e in near_origin)
    assert not index.query(region=(1000, 1000, 2000, 2000))


def test_query_criteria_combine_as_and(index):
    result = index.query(entity_type="dimension", layer="DIM", text_regex=r"^\d")
    assert len(result) == 1
    assert entity_text(result[0]) == "45.5"


def test_text_bearing_only_excludes_geometry(index):
    result = index.query(text_bearing_only=True)
    types = {e.entity_type for e in result}
    assert "line" not in types and "circle" not in types
    assert "dimension" in types and "text" in types


def test_query_limit(index):
    assert len(index.query(limit=2)) == 2


def test_region_accepts_both_bbox_shapes():
    assert Region.from_bbox([0, 0, 10, 10]) == Region(0, 0, 10, 10)
    assert Region.from_bbox([[0, 0], [10, 10]]) == Region(0, 0, 10, 10)
    assert Region.from_bbox(None) is None
    assert Region.from_bbox("nonsense") is None
    assert Region.from_bbox([1, 2]) is None


# --------------------------------------------------------------------------
# Prompt manifest
# --------------------------------------------------------------------------

def test_manifest_leads_with_the_handle_to_cite(index):
    manifest = index.to_manifest()
    assert "[ID: REV-A1]" in manifest
    assert "DWG-12345" in manifest
    assert "layer=TITLE" in manifest


def test_manifest_omits_geometry_and_handleless_entities(index):
    manifest = index.to_manifest()
    # A finding cites the dimension text, not the arc beneath it.
    assert "GEOM" not in manifest
    # An entity with no handle cannot be cited, so listing it would invite a
    # reference the resolver can never resolve.
    assert "no handle here" not in manifest


def test_manifest_reports_truncation_in_band():
    """Silently truncating would let the model believe it saw the whole drawing."""
    many = [FakeEntity(f"H{i}", "text", "L", f"value {i}", (i, i)) for i in range(50)]
    manifest = EntityIndex(many).to_manifest(limit=10)
    lines = manifest.splitlines()
    assert len(lines) == 11
    assert "40 further addressable entities omitted" in lines[-1]
    assert "showing 10 of 50" in lines[-1]


def test_manifest_respects_a_region(index):
    manifest = index.to_manifest(region=(0, 0, 30, 30))
    assert "DWG-12345" in manifest
    assert "45.5" not in manifest


def test_manifest_truncates_long_text():
    idx = EntityIndex([FakeEntity("L1", "text", "L", "x" * 500, (0, 0))])
    line = idx.to_manifest()
    assert "..." in line
    assert len(line) < 200


def test_manifest_is_empty_for_no_entities():
    assert EntityIndex([]).to_manifest() == ""


def test_manifest_coordinates_can_be_suppressed(index):
    assert "@(" in index.to_manifest()
    assert "@(" not in index.to_manifest(include_coordinates=False)


def test_default_manifest_limit_is_sane():
    assert 50 <= DEFAULT_MANIFEST_LIMIT <= 2000


# --------------------------------------------------------------------------
# Anchors
# --------------------------------------------------------------------------

def test_anchor_for_handle_matches_the_canonical_formula(index):
    """Anchors delegate to coordinate_resolver.calc_anchor so the two cannot drift."""
    from services.backend.infrastructure.audit.comparison.coordinate_resolver import calc_anchor

    entity = index.by_handle("A1")
    assert index.anchor_for("A1") == calc_anchor(entity)
    assert index.anchor_for("NOPE") is None


def test_anchor_uses_bbox_when_present():
    """The anchor is the CENTRE of the bbox — the marker glyph is drawn centred on it, so an
    anchor past the right edge puts the tick clear of the text it marks (anchors.py)."""
    idx = EntityIndex([FakeEntity("B9", "text", "L", "v", (0, 0), bbox=[[10, 20], [30, 40]])])
    assert idx.anchor_for("B9") == [20.0, 30.0]
