"""Geometry diffing for the deterministic engine.

`SpatialDiffer.diff_views` builds its pools from `entity_type == 'text'` only, so lines,
circles, arcs, polylines, ellipses and splines were never compared at all. A feature that
carries no text simply did not exist as far as the audit was concerned.

The case that forced this: the M7452A0N01 revision carries an isometric view the reference
does not have — 70 entities, mostly ellipses — and the comparison reported **nothing**. Worse,
`diff_views` returns `[]` early when either side's pool is empty, so a wholly-added zone was
guaranteed to report zero findings rather than "everything here is new".

## What this reports, and what it deliberately does not

**ADDED / REMOVED clusters only.** Unmatched geometry is grouped spatially and each cluster
becomes ONE finding ("47 entities added in this area: 30 ellipse, 17 line"). The alternative —
a finding per entity — would have produced hundreds of rows on a 528-entity drawing and buried
the text findings that are the checklist's actual content.

**No MATCHED findings.** Emitting one per matched line would be pure noise; silence means
matched, exactly as a human checker would treat it.

**No CHANGED findings.** A circle whose radius moved is a real engineering change, but on a
dimensioned drawing it is also already reported by the text differ as a dimension change
("%%c120" -> "%%c130"). Adding a geometric CHANGED would double-report the common case, and
picking a radius tolerance that separates a real size change from tessellation and rounding
noise is a tuning exercise with no measured basis yet. Left out on purpose rather than
guessed at — record a measurement before adding it.

Matching runs in the normalized frame for the same reason the text differ does: the two
drawings are not necessarily in the same coordinate space. See `spatial_differ`'s module
header.
"""
import math
from typing import Any, Optional

from ..bom.zone_detector import _entity_points
from .spatial_differ import _usable_bounds, SpatialDiffer

# Entity types that carry drawable shape. `dimension`, `leader` and `multileader` are
# excluded: they are annotation whose meaning is their text, which the text differ already
# compares, and their geometry moves whenever the thing they point at moves.
GEOMETRY_TYPES: frozenset = frozenset({
    "line", "circle", "arc", "polyline", "ellipse", "spline",
})

# How close two entities of the same kind must sit, as a fraction of the sheet, to be
# considered the same feature. Deliberately looser than the text differ's strict radius:
# geometry has no string to confirm identity with, so position and size carry the whole
# burden and a tight radius would split matched features into ADDED+REMOVED pairs.
POSITION_TOLERANCE_NORM = 0.012

# Extent may differ by this fraction of the sheet and still match. Absorbs tessellation
# differences (an ellipse sampled at 48 segments vs an arc) without letting a genuinely
# different-sized feature pair up.
SIZE_TOLERANCE_NORM = 0.010

# Single-linkage join distance when grouping unmatched entities into a reportable cluster.
CLUSTER_RADIUS_NORM = 0.05

# Below this, an unmatched cluster is noise -- a stray hatch tick or a lone centre-line
# segment -- not a feature worth a checklist row.
MIN_CLUSTER_ENTITIES = 4

# Hard cap on findings emitted per zone per direction, so a wholesale redraw cannot flood
# the checklist. The largest clusters are kept.
MAX_CLUSTERS_PER_SIDE = 5


def _normalized_extent(entity: Any, bounds) -> Optional[tuple]:
    """(cx, cy, w, h) in match space, or None when the entity has no usable geometry."""
    points = _entity_points(entity)
    if not points:
        return None

    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)

    nx0, ny0 = SpatialDiffer._to_match_space(x0, y0, bounds)
    nx1, ny1 = SpatialDiffer._to_match_space(x1, y1, bounds)
    return ((nx0 + nx1) / 2.0, (ny0 + ny1) / 2.0, abs(nx1 - nx0), abs(ny1 - ny0))


def _collect(entities: list, bounds) -> list:
    out = []
    for e in entities:
        kind = getattr(e, "entity_type", "")
        if kind not in GEOMETRY_TYPES:
            continue
        extent = _normalized_extent(e, bounds)
        if extent is None:
            continue
        cx, cy, w, h = extent
        out.append({
            "kind": kind,
            "cx": cx, "cy": cy, "w": w, "h": h,
            "handle": (getattr(e, "properties", {}) or {}).get("handle", ""),
            "matched": False,
        })
    return out


def _cluster(items: list) -> list:
    """Single-linkage grouping of unmatched entities by centroid proximity."""
    unvisited = set(range(len(items)))
    clusters: list = []
    while unvisited:
        group = [unvisited.pop()]
        queue = list(group)
        while queue:
            i = queue.pop()
            for j in list(unvisited):
                if math.hypot(items[i]["cx"] - items[j]["cx"],
                              items[i]["cy"] - items[j]["cy"]) <= CLUSTER_RADIUS_NORM:
                    unvisited.discard(j)
                    group.append(j)
                    queue.append(j)
        clusters.append([items[i] for i in group])
    return clusters


def _describe(group: list) -> str:
    counts: dict = {}
    for item in group:
        counts[item["kind"]] = counts.get(item["kind"], 0) + 1
    parts = [f"{n} {kind}" for kind, n in sorted(counts.items(), key=lambda kv: -kv[1])]
    return ", ".join(parts)


def _to_cad(group: list, bounds) -> Optional[list]:
    """Cluster centroid back in CAD units, so the finding pins on the canvas."""
    if not bounds or not _usable_bounds(bounds):
        return None
    bx0, by0, bx1, by1 = (float(v) for v in bounds)
    cx = sum(g["cx"] for g in group) / len(group)
    cy = sum(g["cy"] for g in group) / len(group)
    return [bx0 + cx * (bx1 - bx0), by0 + cy * (by1 - by0)]


def diff_geometry(
    ref_entities: list,
    rev_entities: list,
    category: str = "drawing_views",
    ref_bounds=None,
    rev_bounds=None,
) -> list[dict]:
    """Compare drawable geometry and report unmatched clusters.

    Unlike `diff_views` this does NOT return early when one side is empty: a zone present on
    only one drawing is the single most important thing this function exists to report.
    """
    is_normalized = _usable_bounds(ref_bounds) and _usable_bounds(rev_bounds)
    rb = ref_bounds if is_normalized else None
    vb = rev_bounds if is_normalized else None

    ref_items = _collect(ref_entities, rb)
    rev_items = _collect(rev_entities, vb)
    if not ref_items and not rev_items:
        return []

    # Greedy nearest-pair matching, same shape as the text differ: collect every candidate
    # pair inside tolerance, then assign shortest-first so a close pair is never stolen by a
    # more distant one that happened to be considered earlier.
    pairs = []
    for ri, rev in enumerate(rev_items):
        for fi, ref in enumerate(ref_items):
            if rev["kind"] != ref["kind"]:
                continue
            dist = math.hypot(rev["cx"] - ref["cx"], rev["cy"] - ref["cy"])
            if dist > POSITION_TOLERANCE_NORM:
                continue
            if (abs(rev["w"] - ref["w"]) > SIZE_TOLERANCE_NORM
                    or abs(rev["h"] - ref["h"]) > SIZE_TOLERANCE_NORM):
                continue
            pairs.append((dist, ri, fi))

    pairs.sort(key=lambda p: p[0])
    for _dist, ri, fi in pairs:
        if rev_items[ri]["matched"] or ref_items[fi]["matched"]:
            continue
        rev_items[ri]["matched"] = True
        ref_items[fi]["matched"] = True

    markings: list[dict] = []

    for items, status, bounds, coord_key in (
        ([i for i in rev_items if not i["matched"]], "ADDED", vb, "coordinates"),
        ([i for i in ref_items if not i["matched"]], "REMOVED", rb, "ref_coordinates"),
    ):
        if not items:
            continue
        groups = [g for g in _cluster(items) if len(g) >= MIN_CLUSTER_ENTITIES]
        groups.sort(key=len, reverse=True)
        for group in groups[:MAX_CLUSTERS_PER_SIDE]:
            summary = _describe(group)
            verb = "added in the revision" if status == "ADDED" else "missing from the revision"
            marking = {
                "entity_id": None,
                "text_content": f"Geometry: {summary}",
                "status": status,
                "details": (
                    f"{len(group)} drawing entities {verb} with no counterpart on the other "
                    f"sheet ({summary}). Reported as one region rather than per entity."
                ),
                "category": category,
                "feature": "geometry",
            }
            coord = _to_cad(group, bounds)
            if coord:
                marking[coord_key] = coord
            markings.append(marking)

    return markings
