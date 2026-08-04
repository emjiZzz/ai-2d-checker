"""Tests for geometry diffing in the deterministic engine.

`SpatialDiffer.diff_views` pools on `entity_type == 'text'`, so lines, circles, arcs,
ellipses and splines were never compared. A feature carrying no text did not exist as far as
the audit was concerned.

The case that forced this: the M7452A0N01 revision carries an isometric view the reference
does not — 70 entities, mostly ellipses — and the comparison reported nothing at all. Worse,
`diff_views` returns [] the moment either pool is empty, so a wholly-added zone was
*guaranteed* zero findings.
"""
from types import SimpleNamespace

import pytest

from services.backend.infrastructure.audit.comparison.geometry_differ import (
    MIN_CLUSTER_ENTITIES,
    MAX_CLUSTERS_PER_SIDE,
    diff_geometry,
)

# Two drawings of the same sheet at different scales, as in the real corpus pair.
REF_BOUNDS = [-52.5, -37.125, 1102.5, 779.625]      # 1155.00 x 816.75, model space
REV_BOUNDS = [-21.0, -14.85, 441.0, 311.85]         # 462.00 x 326.70, paper space
SCALE = 462.0 / 1155.0                               # exactly 0.4


def _ellipse(x, y, r=3.0, handle="E"):
    return SimpleNamespace(
        entity_type="ellipse", layer="0", properties={"handle": handle},
        geometry={"center": [x, y], "major_axis": [r, 0.0],
                  "points": [[x - r, y - r], [x + r, y + r]]},
    )


def _line(x1, y1, x2, y2, handle="L"):
    return SimpleNamespace(
        entity_type="line", layer="0", properties={"handle": handle},
        geometry={"start": [x1, y1], "end": [x2, y2]},
    )


def _text(x, y, txt="T"):
    return SimpleNamespace(
        entity_type="text", layer="0", properties={"text": txt, "handle": "T"},
        geometry={"insert": [x, y]},
    )


def _to_rev(x, y):
    """Same feature, expressed in the revision's coordinate space."""
    rx = (x - REF_BOUNDS[0]) / 1155.0 * 462.0 + REV_BOUNDS[0]
    ry = (y - REF_BOUNDS[1]) / 816.75 * 326.70 + REV_BOUNDS[1]
    return rx, ry


def _cluster_at(x, y, n=8, spread=6.0, rev=False):
    """A tight blob of ellipses, i.e. an isometric-view-like feature."""
    out = []
    for i in range(n):
        px, py = (x + (i % 4) * spread, y + (i // 4) * spread)
        if rev:
            px, py = _to_rev(px, py)
        out.append(_ellipse(px, py, r=3.0 * (SCALE if rev else 1.0), handle=f"E{i}"))
    return out


def _statuses(markings):
    out = {}
    for m in markings:
        out.setdefault(m["status"], []).append(m)
    return out


# ---------------------------------------------------------------------------
# The motivating case
# ---------------------------------------------------------------------------

def test_a_zone_present_only_in_the_revision_is_reported():
    """The reference has no isometric view at all, so its pool is empty. diff_views returns
    [] in that situation; this must not."""
    markings = diff_geometry(
        [], _cluster_at(400.0, 400.0, n=10, rev=True), category="isometric_view",
        ref_bounds=REF_BOUNDS, rev_bounds=REV_BOUNDS,
    )

    added = _statuses(markings).get("ADDED", [])
    assert len(added) == 1, "an added isometric view must produce exactly one finding"
    assert added[0]["category"] == "isometric_view"
    assert "ellipse" in added[0]["text_content"]
    assert added[0]["feature"] == "geometry"


def test_a_zone_present_only_in_the_reference_is_reported():
    markings = diff_geometry(
        _cluster_at(400.0, 400.0, n=10), [], category="isometric_view",
        ref_bounds=REF_BOUNDS, rev_bounds=REV_BOUNDS,
    )

    assert len(_statuses(markings).get("REMOVED", [])) == 1


def test_both_sides_empty_is_silent():
    assert diff_geometry([], [], ref_bounds=REF_BOUNDS, rev_bounds=REV_BOUNDS) == []


# ---------------------------------------------------------------------------
# Matching must survive the scale difference
# ---------------------------------------------------------------------------

def test_the_same_feature_at_two_scales_matches():
    """The two drawings are 2.5x apart. Without normalization every entity would be
    unmatched and the whole sheet would report as replaced."""
    ref = _cluster_at(400.0, 400.0, n=10)
    rev = _cluster_at(400.0, 400.0, n=10, rev=True)

    markings = diff_geometry(ref, rev, ref_bounds=REF_BOUNDS, rev_bounds=REV_BOUNDS)

    assert markings == [], f"unchanged geometry reported as changed: {markings}"


def test_unchanged_geometry_produces_no_matched_noise():
    """Silence means matched. One finding per matched line would bury the text findings."""
    ref = [_line(100 + i * 10, 200, 110 + i * 10, 210, handle=f"L{i}") for i in range(20)]
    rev = []
    for i in range(20):
        x1, y1 = _to_rev(100 + i * 10, 200)
        x2, y2 = _to_rev(110 + i * 10, 210)
        rev.append(_line(x1, y1, x2, y2, handle=f"M{i}"))

    assert diff_geometry(ref, rev, ref_bounds=REF_BOUNDS, rev_bounds=REV_BOUNDS) == []


# ---------------------------------------------------------------------------
# Noise control
# ---------------------------------------------------------------------------

def test_a_stray_entity_is_not_a_finding():
    """A lone unmatched line is a centre-line tick or hatch fragment, not a feature."""
    markings = diff_geometry(
        [], [_ellipse(*_to_rev(400.0, 400.0))],
        ref_bounds=REF_BOUNDS, rev_bounds=REV_BOUNDS,
    )
    assert markings == []


def test_cluster_threshold_is_respected():
    just_under = diff_geometry(
        [], _cluster_at(400.0, 400.0, n=MIN_CLUSTER_ENTITIES - 1, rev=True),
        ref_bounds=REF_BOUNDS, rev_bounds=REV_BOUNDS,
    )
    at_threshold = diff_geometry(
        [], _cluster_at(400.0, 400.0, n=MIN_CLUSTER_ENTITIES, rev=True),
        ref_bounds=REF_BOUNDS, rev_bounds=REV_BOUNDS,
    )
    assert just_under == []
    assert len(at_threshold) == 1


def test_separate_regions_become_separate_findings():
    rev = (_cluster_at(150.0, 150.0, n=8, rev=True)
           + _cluster_at(900.0, 650.0, n=8, rev=True))

    markings = diff_geometry([], rev, ref_bounds=REF_BOUNDS, rev_bounds=REV_BOUNDS)

    assert len(markings) == 2, "distant regions must not merge into one finding"


def test_findings_are_capped_so_a_redraw_cannot_flood_the_checklist():
    rev = []
    for i in range(MAX_CLUSTERS_PER_SIDE + 4):
        # Spread far enough apart that each is its own cluster.
        rev += _cluster_at(80.0 + i * 95.0, 120.0 + (i % 3) * 210.0, n=6, rev=True)

    markings = diff_geometry([], rev, ref_bounds=REF_BOUNDS, rev_bounds=REV_BOUNDS)

    assert len(markings) <= MAX_CLUSTERS_PER_SIDE


def test_text_entities_are_ignored():
    """Text is the other differ's job; comparing it here would double-report everything."""
    markings = diff_geometry(
        [], [_text(*_to_rev(400.0 + i * 5, 400.0)) for i in range(20)],
        ref_bounds=REF_BOUNDS, rev_bounds=REV_BOUNDS,
    )
    assert markings == []


def test_dimensions_and_leaders_are_ignored():
    """Annotation whose meaning is its text, and whose geometry moves with what it points at."""
    ann = [
        SimpleNamespace(entity_type="dimension", layer="0", properties={"handle": f"D{i}"},
                        geometry={"def_point": list(_to_rev(400.0 + i * 5, 400.0))})
        for i in range(20)
    ]
    assert diff_geometry([], ann, ref_bounds=REF_BOUNDS, rev_bounds=REV_BOUNDS) == []


# ---------------------------------------------------------------------------
# Output shape
# ---------------------------------------------------------------------------

def test_finding_carries_a_cad_coordinate_not_a_normalized_one():
    markings = diff_geometry(
        [], _cluster_at(400.0, 400.0, n=10, rev=True),
        ref_bounds=REF_BOUNDS, rev_bounds=REV_BOUNDS,
    )
    coord = markings[0]["coordinates"]
    # Normalized values live in 0..1; real revision CAD coords here are far larger.
    assert max(abs(coord[0]), abs(coord[1])) > 1.5
    assert REV_BOUNDS[0] <= coord[0] <= REV_BOUNDS[2]
    assert REV_BOUNDS[1] <= coord[1] <= REV_BOUNDS[3]


def test_removed_finding_carries_the_reference_coordinate():
    markings = diff_geometry(
        _cluster_at(400.0, 400.0, n=10), [],
        ref_bounds=REF_BOUNDS, rev_bounds=REV_BOUNDS,
    )
    assert "ref_coordinates" in markings[0]
    assert REF_BOUNDS[0] <= markings[0]["ref_coordinates"][0] <= REF_BOUNDS[2]


def test_description_counts_entity_kinds():
    rev = _cluster_at(400.0, 400.0, n=8, rev=True)
    rev.append(_line(*_to_rev(400.0, 400.0), *_to_rev(420.0, 420.0), handle="LX"))

    markings = diff_geometry([], rev, ref_bounds=REF_BOUNDS, rev_bounds=REV_BOUNDS)

    assert "8 ellipse" in markings[0]["text_content"]
    assert "1 line" in markings[0]["text_content"]


def test_status_values_are_schema_legal():
    """CanvasMarking.status is a Literal; an invalid value fails response validation."""
    markings = diff_geometry(
        _cluster_at(150.0, 150.0, n=8), _cluster_at(900.0, 650.0, n=8, rev=True),
        ref_bounds=REF_BOUNDS, rev_bounds=REV_BOUNDS,
    )
    assert markings
    for m in markings:
        assert m["status"] in {"MATCHED", "CHANGED", "ADDED", "REMOVED", "CONFLICT"}
        assert m["category"] in {
            "drawing_views", "notes_section", "bill_of_materials",
            "title_block", "isometric_view", "other_engineering_references",
        }
        assert isinstance(m["text_content"], str) and m["text_content"]
        assert isinstance(m["details"], str) and m["details"]


def test_missing_bounds_degrades_instead_of_crashing():
    ref = _cluster_at(400.0, 400.0, n=8)
    rev = _cluster_at(400.0, 400.0, n=8)
    # No bounds: matching falls back to raw units, which is correct only when the two
    # drawings share a coordinate space -- here they do.
    assert diff_geometry(ref, rev) == []
