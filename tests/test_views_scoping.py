"""
Strict `views`-box scoping for the drawing_views comparison pool.

`drawing_views` used to be the residual — everything on the sheet minus the other zones and
margins — so content inside no zone box was still compared, and the pinned `views` box was
ignored for scoping. `scope_entities_to_views` makes the views box the definitive boundary:
only entities whose centroid sits inside it (minus sibling zones) are compared, and a sheet
with no views box compares nothing there (strict, no residual fallback).

The subtle part these tests pin: geometry (lines/arcs) has no text `insert` point, so
containment is computed from `_entity_points` centroids, not `insert` alone — otherwise all
drawable geometry would be silently dropped from the pool.
"""
from types import SimpleNamespace

from services.backend.infrastructure.audit.bom.zone_detector import scope_entities_to_views

VIEWS = (0.0, 0.0, 50.0, 50.0)


def _text(x, y):
    """A text entity — coordinates live under `insert`."""
    return SimpleNamespace(entity_type="text", geometry={"insert": [x, y]})


def _line(x1, y1, x2, y2):
    """A line — no `insert`; coordinates live under `start`/`end`. Centroid is the midpoint."""
    return SimpleNamespace(entity_type="line", geometry={"start": [x1, y1], "end": [x2, y2]})


def test_text_inside_kept_outside_dropped():
    inside, outside = _text(25, 25), _text(100, 100)
    assert scope_entities_to_views([inside, outside], VIEWS, []) == [inside]


def test_sibling_exclusion_drops_entity_inside_views():
    # Inside the views box but inside a sibling zone (e.g. a title block overlapping a pinned
    # full-area views rectangle) → excluded, so it isn't double-compared as a drawing view.
    inside_sibling = _text(25, 25)
    assert scope_entities_to_views([inside_sibling], VIEWS, [(20, 20, 30, 30)]) == []


def test_geometry_line_located_by_points_not_insert():
    # The wrinkle: a line has no `insert`. It must still be located by its start/end centroid,
    # or all drawable geometry would vanish from drawing_views.
    inside_line = _line(10, 10, 30, 30)      # centroid (20, 20) — inside
    outside_line = _line(90, 90, 110, 110)   # centroid (100, 100) — outside
    assert scope_entities_to_views([inside_line, outside_line], VIEWS, []) == [inside_line]


def test_no_views_box_returns_empty_no_fallback():
    # Strict scoping: no views box → nothing compared, not a fallback to the whole sheet.
    ents = [_text(25, 25), _line(10, 10, 30, 30)]
    assert scope_entities_to_views(ents, None, []) == []


def test_entity_without_geometry_is_skipped():
    assert scope_entities_to_views([SimpleNamespace(geometry={})], VIEWS, []) == []


def test_centroid_on_the_boundary_is_inside():
    # Inclusive bounds — a centroid exactly on an edge/corner belongs to the box.
    e = _text(0, 50)
    assert scope_entities_to_views([e], VIEWS, []) == [e]
