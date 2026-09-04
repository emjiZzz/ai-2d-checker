"""
zone_detector.py
================
Content-Aware Zone Detector for 2D CAD Engineering Drawings.

Instead of relying on layer names or blind percentage grids, this module
identifies drawing zones by finding semantic anchor text signatures that
are always present in each zone type, then flood-fills a bounding box
around all content spatially clustered near those anchors.

Zone Anchors (examples):
  tolerance  -> "tolerances unless otherwise specified", "general tolerance"
  bom        -> table header row containing "No.", "Q'ty", "Material"
  title      -> "Scale", "Drawn", "Approved", "Checked"
  notes      -> "NOTES:", "NOTE:", freeform paragraph text
  iso        -> "ISO", isometric view block inserts
  views      -> everything in the main drawing area (derived by exclusion)
"""

from __future__ import annotations

import re
import math
import unicodedata
from typing import Any, Optional
from ...utils.text import strip_mtext, safe_decode
from ..comparison.params import DEFAULT_PARAMS

# ---------------------------------------------------------------------------
# Zone Anchor Signatures
# Each zone has a list of trigger phrases. A single match is enough to
# bootstrap the zone detection because we then expand the bounding box
# by collecting all content spatially near the anchor.
# ---------------------------------------------------------------------------

ZONE_ANCHORS: dict[str, list[str]] = {
    # ------------------------------------------------------------------
    # TOLERANCE / SAFE ZONE (bottom-left template block)
    # These are fixed standard notes that never change between revisions.
    # Once found, the entire surrounding block is marked as a safe zone.
    # ------------------------------------------------------------------
    "tolerance": [
        "tolerances unless otherwise specified",
        "unless otherwise specified",
        "unless otherwise noted",
        "general tolerance",
        "general note",
        "fabrication tolerance",
        "machining tolerance",
        "unless noted",
        "指示外公差",
        "指示無き公差",
        "指示なき公差",
        "表示外公差",
        "一般公差",
        "普通公差",
        "普通寸法許容差",
        "仕上精度",
        "仕上ゲ記号",
        "表面粗さ",
        "roughness range",
        "finish symbol",
        "surface roughness",
    ],

    # ------------------------------------------------------------------
    # BOM (Bill of Materials) - usually top-right, table format
    # Identified by table header row with item number + quantity columns.
    # ------------------------------------------------------------------
    "bom": [
        "parts list",
        "bill of materials",
        "材料明細",
        "部品表",
        "素材重量",
        "仕上重量",
        "finished wt",
        "material wt",
        "finished weight",
        "material weight",
        "material wt (kg)",
        "finished wt (kg)",
    ],

    # ------------------------------------------------------------------
    # TITLE BLOCK (bottom-right) - machine name, drawing number, revisions
    # ------------------------------------------------------------------
    "title": [
        "drawing no",
        "dwg no",
        "dwg. no",
        "drawing number",
        "図面番号",
        "designed",
        "設計",
        "drawn",
        "製図",
        "approved",
        "承認",
        "checked",
        "検図",
        "revision",
        "訂正",
        "job no",
        "工事番号",
    ],

    # ------------------------------------------------------------------
    # TITLE UPPER LEFT (top-left production metadata table)
    # This block typically contains Unit No., Part No., T. Q'ty, Stock Q'ty
    # columns in a 2-row table (headers + values). It must be grouped under
    # Title Block, not Drawing Views.
    # ------------------------------------------------------------------
    "title_upper_left": [
        "map",
        "unit no",
        "unit no.",
        "part no",
        "part no.",
        "part.no",
        "ユニットno",
        "ユニットno.",
        "ユニット no",
        "コードno",
        "コードno.",
        "コード no",
        "t. q'ty",
        "t.q'ty",
        "stock q'ty",
        "在庫棚入庫",
        "総製作個数",
        "共通番号",
        "t. qty",
        "stock qty",
    ],

    # ------------------------------------------------------------------
    # NOTES SECTION (freeform text, typically left or bottom-center)
    # ------------------------------------------------------------------
    #
    # An anchor here must be a phrase that appears ONLY in a note. A term that also occurs in
    # the sheet furniture does not merely add noise — it drags the zone's bounding box across the
    # sheet toward the furniture, and the box then covers neither cluster. `仕上げ` was removed
    # 2026-08-12 for exactly that: it matches `仕上げ記号` ("finish symbol"), a label in the
    # bottom-left tolerance block, on every side of every corpus pair. On `M7452A0N01`'s reference
    # the real notes sit at (606, 552-600) and `仕上げ記号` at (77, 123); the box came out
    # x 105-578, y 120-603 and contained none of the three notes rows. Removing it took notes
    # rows inside the detected box from 16/45 to 27/45 across the corpus, and took the three
    # `M7452A*` reference sides from 0/3 to 3/3.
    #
    # Do NOT add `ロール` to reach the roll-count lines. Measured and rejected: this family's
    # drawing title is `ロールカセット 12"ミル`, so it matches the title block and repeats the same
    # failure. Coverage appears to rise to 39/45, but the gain is the box INFLATING to span from
    # the roll counts down to the title — on the three large pairs' reference sides the resulting
    # notes box sits 100% inside `tolerance`, a safe zone. Coverage alone cannot see that; a
    # box grown to cover the sheet scores perfectly and means nothing. The roll-count lines have
    # no keyword that distinguishes them from the title and need a different signal.
    "notes": [
        "notes:",
        "note:",
        "注記",
        "注意",
        "general notes",
        "fabrication notes",
        "assembly notes",
        "注記事項",
        "注意事項",
        "面取り",
        "なきこと",
        "角部は",
        "キリ粉",
    ],

    # ------------------------------------------------------------------
    # ISOMETRIC VIEW (usually top-right or center-right)
    # ------------------------------------------------------------------
    "iso": [
        "isometric",
        "isometric view",
        "iso view",
        "3d view",
        "立体図",
        "等角図",
    ],

    # ------------------------------------------------------------------
    # SHIM TABLE (シム表) — a small parts table (No./thickness/material/qty)
    # that sits inside the drawing area on some sheets and not others. It is
    # OPTIONAL by design: anchored on its own title only, and deliberately NOT
    # given a percentage fallback in table_extractor.default_pct, so a sheet
    # without a shim table simply has no `shim` zone rather than a phantom box.
    # Anchored on the table title; `_find_anchor_positions` matches on an
    # NFKC-normalised substring, so 'シム表' also catches the revision's
    # decorated 'Ｌ　シム表　ｌ'.
    # ------------------------------------------------------------------
    "shim": [
        "シム表",
    ],
}

# How close (in CAD units) another entity must be to an anchor seed
# to be swept into that zone's bounding box
CLUSTER_RADIUS = DEFAULT_PARAMS.cluster_radius

# ---------------------------------------------------------------------------
# Isometric view detection (geometric, not text-anchored)
#
# `iso` is the one zone that text anchors cannot find: an isometric view routinely
# carries no label at all, so ZONE_ANCHORS["iso"] matched 0 of 6 corpus drawings and
# every `iso` box in the system was a percentage-grid guess. Its 0.0pp positional
# spread read as perfect stability; it was six identical guesses.
#
# Geometry separates it cleanly. A circle viewed at an angle projects to an ELLIPSE,
# so an axonometric view is ellipse-dense, while orthographic views keep their circles
# as CIRCLE/ARC. Measured across the corpus: 38 / 63 / 10 ellipses on the three
# drawings carrying an iso view, and 0 / 0 / 0 on the three without. Complete
# separation, so the threshold needs no tuning and only guards against a stray ellipse
# in an orthographic view (an obliquely-cut cylinder or a slot).
#
# The 30/150-degree line-angle test was tried first and is materially worse: dimension
# and leader arrowheads are drawn near 30 degrees and are scattered sheet-wide, and the
# SX_FinishSymbol_* blocks (surface-finish marks) are too, which smeared the detected
# span across almost the whole sheet. Do not revisit it without new evidence.
MIN_ISO_ELLIPSES = DEFAULT_PARAMS.min_iso_ellipses

# Fraction of the ellipses that must share one block instance before that block's
# extent is trusted as the iso view outright.
ISO_BLOCK_DOMINANCE = DEFAULT_PARAMS.iso_block_dominance

# Single-linkage join distance for the fallback clustering path, as a fraction of the
# sheet diagonal.
ISO_CLUSTER_RADIUS_FRACTION = DEFAULT_PARAMS.iso_cluster_radius_fraction

# Physical limits on zone size, as (width, height) fractions of the sheet, to stop a
# runaway flood-fill swallowing the drawing. Module-level rather than local to
# `detect_zones_by_content` because `table_extractor` needs the same caps when it grows a
# pinned zone against detection -- a cap that only applies on one of the two paths that
# can produce a zone box is not a cap.
ZONE_MAX_LIMITS: dict[str, tuple] = {
    "tolerance": (0.95, 0.30),        # spans nearly the full width of the bottom strip
    "bom": (0.45, 0.65),
    "title": (0.60, 0.35),
    "title_upper_left": (0.40, 0.35),
    "notes": (0.45, 0.65),
    "iso": (0.45, 0.45),
    # The height was 0.35 and that is smaller than the table it caps. Measured on
    # M745227N01's reference: the drawn シム表 is 337.5 units tall on an 891-unit sheet
    # (37.9%). The box came out 311.8 tall — its cap to the unit — with the bottom row
    # `総厚サ 6mm` (y=311.1) finishing 35.8 units below the bottom edge of its own zone,
    # from where it fell through to the `drawing_views` pool and was compared and marked.
    # A SAFE zone's content must never be compared. Raising the cap to 0.45 covers every row
    # on both sides; the box then stops on its own content, not on the limit.
    #
    # The growth loop refuses any point that would push the cluster past the cap
    # (`_expand_bbox`), so a cap below the table's own size does not shrink the box, it
    # excludes real rows from the zone that owns them — silently, and in the direction
    # that creates findings rather than suppressing them.
    "shim": (0.30, 0.45),             # a compact parts table, but see above: 0.35 clipped it
}

# Zones that `views` must subtract.
#
# `views` is defined by exclusion -- it is the drawing area, meaning everything that is not
# sheet furniture or a floating annotation block. When `views` is *detected* that exclusion
# is baked into `_derive_views_zone`. When it is pinned from a template it is a plain
# rectangle covering the whole drawing area, so the exclusion has to be re-applied at the
# point of use or notes/iso/title content inside that rectangle reads as drawing geometry.
VIEWS_EXCLUDED_ZONES: tuple = (
    "title", "title_upper_left", "bom", "tolerance", "notes", "iso", "shim",
)


def views_exclusions(regions: dict, omit: tuple = ()) -> list:
    """Zone shapes that must be subtracted from `views` at the point of use.

    Returns `(bbox, outline)` pairs for the sibling zones present in `regions` — `outline` is
    None for the ordinary rectangular zone and the hand-drawn polygon for a reshaped one.
    Callers that treat `views` as a containment region should skip anything falling inside one
    of these.

    Pairs rather than bare boxes so that a reshaped sibling excludes only what it actually
    covers. Using its bounding box instead would over-exclude — content in the notch the user
    deliberately cut out of, say, the notes zone would be dropped from `views` as well, and
    land in no category at all. That is the silent false-negative direction.

    `omit` drops a zone from the subtraction because the caller is subtracting that zone's
    content by entity identity instead. `notes` is passed there by the comparison
    orchestrator: its pool is now chosen per entity rather than per box, so subtracting the box
    as well would be wrong in both directions — it would drop view geometry that merely sits
    near the notes, and leave a note that fell outside the box in the `views` pool to be
    reported twice. Identity keeps the two pools exactly complementary.
    """
    from .zone_geometry import polygon_for

    return [
        (bbox, polygon_for(regions, key))
        for key, bbox in (regions or {}).items()
        if key in VIEWS_EXCLUDED_ZONES and key not in omit and bbox
    ]


def point_in_any_bbox(x: float, y: float, bboxes) -> bool:
    """True when (x, y) falls inside any of `bboxes`.

    Accepts either bare bboxes or `(bbox, outline)` pairs as returned by `views_exclusions`,
    so existing callers that pass plain boxes keep working unchanged.
    """
    from .zone_geometry import point_in_any_shape

    return point_in_any_shape(x, y, bboxes or ())

# Safety padding added around the final computed bounding box.
#
# Absolute, deliberately. Making this a fraction of sheet height was tried and measured
# across the 6-drawing corpus: it changed cross-sheet positional spread by under half a
# percentage point on the two stable zones and made `views` and `notes` slightly worse, so
# the extra constants were not carried. Absolute padding is conceptually odd on sheets at
# different scales, but it is measurably not what drives zone instability here — see
# docs/zone-template-alignment-implementation-plan.md, Phase D notes, before retrying it.
BBOX_PADDING = DEFAULT_PARAMS.bbox_padding


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _norm(text: str) -> str:
    """Lowercase, NFKC-normalize, collapse whitespace."""
    t = unicodedata.normalize("NFKC", text or "").strip().lower()
    return re.sub(r"\s+", " ", t)


def _get_xy(entity: Any) -> Optional[tuple]:
    """Extract (x, y) from a CAD entity's geometry."""
    geo = getattr(entity, "geometry", {}) or {}
    for key in ("insert", "location", "text_point", "start"):
        pt = geo.get(key)
        if pt and len(pt) >= 2:
            return float(pt[0]), float(pt[1])
    return None


def _text_of(entity: Any) -> str:
    """Extract raw text from a text/mtext entity."""
    props = getattr(entity, "properties", {}) or {}
    return props.get("text", "") or props.get("value", "") or ""


def _is_text_entity(entity: Any) -> bool:
    return getattr(entity, "entity_type", "") in ("text", "mtext", "attrib")


def _ellipse_center(entity: Any) -> Optional[tuple]:
    """Centre of an ELLIPSE.

    Deliberately separate from `_get_xy`, which does not read the `center` key.
    Teaching `_get_xy` about centres would silently pull circles and arcs into
    `detect_subviews` (its entity filter already admits them, but they currently
    resolve to None and are skipped), changing sub-view boxes as a side effect of an
    unrelated fix.
    """
    geo = getattr(entity, "geometry", {}) or {}
    center = geo.get("center")
    if center and len(center) >= 2:
        return float(center[0]), float(center[1])
    return None


def _entity_points(entity: Any) -> list:
    """Every (x, y) an entity contributes, across all geometry shapes.

    Needed because an isometric view is built from ellipses and splines, whose
    coordinates live under keys (`center`, `points`, `control_points`) that the
    text/line-oriented helpers above do not read.
    """
    geo = getattr(entity, "geometry", {}) or {}
    points: list = []

    def add(point: Any) -> None:
        try:
            if point is not None and len(point) >= 2:
                points.append((float(point[0]), float(point[1])))
        except (TypeError, ValueError):
            pass

    for key in ("insert", "location", "text_point", "start", "end", "center", "def_point"):
        add(geo.get(key))

    for key in ("points", "vertices", "control_points", "fit_points", "boundary_points"):
        sequence = geo.get(key)
        if isinstance(sequence, list):
            for point in sequence:
                add(point)

    return points


def entity_anchor(entity: Any) -> Optional[tuple]:
    """The single (x, y) that decides which zone an entity belongs to.

    For most entities this is the centroid of `_entity_points`, so drawable geometry
    (lines/arcs/ellipses, whose coordinates live under start/end/center/points/…) is located
    correctly instead of being dropped for lacking an `insert` point.

    A DIMENSION is the exception, and it has to be. Its points are the measured feature
    (`def_point`) and the value's own position (`text_point`), which on a diameter or a long
    linear dimension sit far apart — their midpoint is a phantom location where nothing is
    drawn. On the M7452A1N01 reference the ⌀260 dimension runs y=228.5 → 358.5 and that
    midpoint (y=293.5) lands inside the tolerance table's safe zone, so the dimension was
    dropped from the drawing_views pool while the revision's ⌀260, whose midpoint cleared the
    zone, survived: an unchanged dimension present on both sheets was reported ADDED with no
    REMOVED counterpart. Whether a dimension gets compared at all must not depend on how far
    its extension lines happen to reach.

    So a dimension is anchored at `text_point` — where its value is drawn, where the checker
    reads it, and where `SpatialDiffer._get_entity_coords` already pins its marker. Zone
    scoping and marker placement now agree instead of being able to name different zones for
    the same dimension.
    """
    geo = getattr(entity, "geometry", {}) or {}
    if getattr(entity, "entity_type", "") == "dimension":
        for key in ("text_point", "def_point", "insert", "location"):
            point = geo.get(key)
            try:
                if point is not None and len(point) >= 2:
                    return float(point[0]), float(point[1])
            except (TypeError, ValueError):
                continue
        return None

    pts = _entity_points(entity)
    if not pts:
        return None
    return sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)


def scope_entities_to_views(
    entities: list, views_bbox, exclude_bboxes=None, views_polygon=None
) -> list:
    """Entities that belong to the `views` zone: anchor inside the views SHAPE and not inside
    any sibling zone in `exclude_bboxes` (pass `views_exclusions(regions)`).

    Returns [] when `views_bbox` is falsy — strict scoping with no residual fallback: a
    sheet with no views box contributes nothing to the drawing_views comparison, by design.
    This is what makes the `views` box the definitive comparison boundary instead of comparing
    everything that falls outside the other zones.

    `views_polygon` is the hand-drawn outline when the user has reshaped the zone by inserting
    nodes on its edges (`zone_geometry.polygon_for(regions, "views")`). Absent, the bbox is the
    shape, which is the case for every zone nobody has reshaped.

    The anchor point comes from `entity_anchor` — a centroid for ordinary entities, the
    `text_point` for dimensions. See there for why dimensions cannot use a centroid.
    """
    from .zone_geometry import point_in_shape

    if not views_bbox:
        return []
    result = []
    for e in entities:
        anchor = entity_anchor(e)
        if anchor is None:
            continue
        cx, cy = anchor
        if not point_in_shape(cx, cy, views_bbox, views_polygon):
            continue
        if point_in_any_bbox(cx, cy, exclude_bboxes):
            continue
        result.append(e)
    return result


def _largest_ellipse_cluster(ellipses: list, bounds: Optional[tuple]) -> list:
    """Single-linkage cluster of ellipse centres; returns the biggest group.

    Fallback for when block grouping is unavailable -- nested INSERTs lose the parent
    handle during explosion, and geometry drawn loose in model space never had one.
    """
    seeds = []
    for entity in ellipses:
        center = _ellipse_center(entity)
        if center:
            seeds.append((center, entity))
    if not seeds:
        return []

    if bounds:
        min_x, min_y, max_x, max_y = bounds
        radius = math.hypot(max_x - min_x, max_y - min_y) * ISO_CLUSTER_RADIUS_FRACTION
    else:
        radius = CLUSTER_RADIUS

    unvisited = set(range(len(seeds)))
    best: list = []
    while unvisited:
        group = [unvisited.pop()]
        queue = list(group)
        while queue:
            (xi, yi), _ = seeds[queue.pop()]
            for j in list(unvisited):
                (xj, yj), _ = seeds[j]
                if math.hypot(xi - xj, yi - yj) <= radius:
                    unvisited.discard(j)
                    group.append(j)
                    queue.append(j)
        if len(group) > len(best):
            best = group

    if len(best) < MIN_ISO_ELLIPSES:
        return []
    return [seeds[i][1] for i in best]


def _detect_iso_zone(entities: list, bounds: Optional[tuple]) -> Optional[tuple]:
    """Locate the isometric view by ellipse density. Returns None when there is none.

    Returning None matters as much as returning a box: roughly half the drawings in
    the corpus genuinely have no isometric view (they are the pre-revision sheets),
    and asserting a percentage-grid box on those is what the old behaviour did.
    """
    ellipses = [e for e in entities if getattr(e, "entity_type", "") == "ellipse"]
    if len(ellipses) < MIN_ISO_ELLIPSES:
        return None

    # Preferred path: an isometric view is normally placed as a single INSERT, so the
    # block instance owning most of the ellipses yields an exact extent with no
    # clustering heuristic, no padding guesswork and no cap.
    by_parent: dict = {}
    for entity in ellipses:
        handle = (getattr(entity, "properties", {}) or {}).get("parent_handle")
        if handle:
            by_parent[handle] = by_parent.get(handle, 0) + 1

    members: list = []
    if by_parent:
        handle, count = max(by_parent.items(), key=lambda kv: kv[1])
        if count >= ISO_BLOCK_DOMINANCE * len(ellipses):
            members = [
                e for e in entities
                if (getattr(e, "properties", {}) or {}).get("parent_handle") == handle
            ]

    if not members:
        members = _largest_ellipse_cluster(ellipses, bounds)

    points = [p for entity in members for p in _entity_points(entity)]
    if len(points) < 4:
        return None

    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return (
        min(xs) - BBOX_PADDING,
        min(ys) - BBOX_PADDING,
        max(xs) + BBOX_PADDING,
        max(ys) + BBOX_PADDING,
    )


# ---------------------------------------------------------------------------
# Core: Semantic Anchor Detection
# ---------------------------------------------------------------------------

def _find_anchor_positions(entities: list, zone: str) -> list:
    """
    Scan all text entities for anchor signatures belonging to ``zone``.
    Returns a list of ``(x, y, anchor)`` for each match found.

    The third element records WHICH anchor phrase matched. `tolerance` carries 23 anchors and
    `title` 17, so "the zone was detected" says nothing about whether the same signature was
    used on two drawings -- and two drawings resolving the same zone through different anchors
    do not really have comparable boxes. Callers index positionally (`p[0]`, `p[1]`), which is
    why this stayed a tuple rather than becoming a dict.
    """
    anchors_to_match = ZONE_ANCHORS.get(zone, [])
    hits = []

    for e in entities:
        if not _is_text_entity(e):
            continue
        raw = _text_of(e)
        if not raw:
            continue
        normed = _norm(raw)
        for anchor in anchors_to_match:
            if _norm(anchor) in normed:
                xy = _get_xy(e)
                if xy:
                    hits.append((xy[0], xy[1], anchor))
                break  # one anchor per entity is enough

    return hits


def _expand_bbox(entities: list, seed_positions: list, radius: Any, max_w: float = 999999.0, max_h: float = 999999.0, exclude_lines: bool = False) -> Optional[tuple]:
    """
    Starting from the seed positions, collect all text and line entities
    within `radius` (float or tuple (rx, ry)) CAD units and return the bounding box.
    Uses iterative flood-fill so the box grows until stable, constrained by max_w/max_h.
    """
    if not seed_positions:
        return None

    if isinstance(radius, tuple):
        radius_x, radius_y = radius
    else:
        radius_x = radius_y = float(radius)

    xs = [p[0] for p in seed_positions]
    ys = [p[1] for p in seed_positions]
    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)

    # Iterative expansion: grow the bbox until no new points are pulled in
    changed = True
    while changed:
        changed = False
        for e in entities:
            etype = getattr(e, "entity_type", "")
            if etype in ("text", "mtext", "attrib"):
                xy = _get_xy(e)
                if not xy:
                    continue
                ex, ey = xy
                if (xmin - radius_x) <= ex <= (xmax + radius_x) and \
                   (ymin - radius_y) <= ey <= (ymax + radius_y):
                    next_xmin = min(xmin, ex)
                    next_xmax = max(xmax, ex)
                    next_ymin = min(ymin, ey)
                    next_ymax = max(ymax, ey)
                    if (next_xmax - next_xmin) <= max_w and (next_ymax - next_ymin) <= max_h:
                        if next_xmin != xmin or next_xmax != xmax or next_ymin != ymin or next_ymax != ymax:
                            xmin, xmax, ymin, ymax = next_xmin, next_xmax, next_ymin, next_ymax
                            changed = True

            elif etype in ("line",) and not exclude_lines:
                geo = getattr(e, "geometry", {}) or {}
                for key in ("start", "end"):
                    pt = geo.get(key)
                    if pt and len(pt) >= 2:
                        lx, ly = float(pt[0]), float(pt[1])
                        if (xmin - radius_x) <= lx <= (xmax + radius_x) and \
                           (ymin - radius_y) <= ly <= (ymax + radius_y):
                            next_xmin = min(xmin, lx)
                            next_xmax = max(xmax, lx)
                            next_ymin = min(ymin, ly)
                            next_ymax = max(ymax, ly)
                            if (next_xmax - next_xmin) <= max_w and (next_ymax - next_ymin) <= max_h:
                                if next_xmin != xmin or next_xmax != xmax or next_ymin != ymin or next_ymax != ymax:
                                    xmin, xmax, ymin, ymax = next_xmin, next_xmax, next_ymin, next_ymax
                                    changed = True

    padding = 5.0 if exclude_lines else BBOX_PADDING

    # Pad, then clamp back inside max_w/max_h.
    #
    # The clamp is the point: the growth loop above refuses any expansion that would breach
    # the caps, but padding used to be added *after* it returned, so the final box was
    # always up to 2*padding larger than the declared limit in each axis and ZONE_MAX_LIMITS
    # was not actually a limit. Measured on M7452A0N01_reference.dxf, `title` grew to 259
    # units (inside its 286-unit cap) and was then padded to 319 — 39.1% of sheet height
    # against a declared 35% ceiling. Shrinking symmetrically keeps the box centred on the
    # cluster that was actually found rather than biasing it toward one edge.
    return _clamp_bbox(
        (xmin - padding, ymin - padding, xmax + padding, ymax + padding), max_w, max_h
    )


def _clamp_bbox(bbox: tuple, max_w: float, max_h: float) -> tuple:
    """Shrink a box symmetrically until it fits within max_w/max_h.

    Symmetric so the box stays centred on the cluster that was actually found rather
    than being biased toward one edge. Shared by `_expand_bbox` and the geometric iso
    detector so the cap invariant pinned by `tests/test_zone_detector_caps.py` holds
    for every producer of a zone box, not just the flood-fill one.
    """
    xmin, ymin, xmax, ymax = bbox

    width = xmax - xmin
    if width > max_w:
        excess = (width - max_w) / 2.0
        xmin += excess
        xmax -= excess

    height = ymax - ymin
    if height > max_h:
        excess = (height - max_h) / 2.0
        ymin += excess
        ymax -= excess

    return (xmin, ymin, xmax, ymax)


# ---------------------------------------------------------------------------
# Public API & Helpers
# ---------------------------------------------------------------------------

def _get_drawing_bounds(entities: list) -> Optional[tuple]:
    """Compute sheet boundaries from lines and polylines without circular imports."""
    lines = []
    for e in entities:
        if getattr(e, "entity_type", "") == "line":
            geo = getattr(e, "geometry", {}) or {}
            if "start" in geo and "end" in geo:
                lines.append((geo["start"], geo["end"]))
        elif getattr(e, "entity_type", "") == "polyline":
            geo = getattr(e, "geometry", {}) or {}
            if "vertices" in geo:
                pts = geo["vertices"]
                for i in range(len(pts) - 1):
                    lines.append((pts[i], pts[i+1]))
            elif "points" in geo:
                pts = geo["points"]
                for i in range(len(pts) - 1):
                    lines.append((pts[i], pts[i+1]))

    if not lines:
        return None

    min_x = min(min(p1[0], p2[0]) for p1, p2 in lines)
    max_x = max(max(p1[0], p2[0]) for p1, p2 in lines)
    min_y = min(min(p1[1], p2[1]) for p1, p2 in lines)
    max_y = max(max(p1[1], p2[1]) for p1, p2 in lines)
    return (min_x, min_y, max_x, max_y)


# Outer band, as a fraction of sheet width/height, within which a lone grid character is
# treated as frame furniture rather than content.
#
# Measured on the KEMCO pair bc17b56d / 63adc691 (2026-07-30): grid labels occupy two
# rings, at 6.27-6.46% and 7.43-8.52% of the sheet dimension. The previous 6.0% cutoff sat
# below *both*, so it excluded nothing on these sheets and the labels stayed in the
# detection pool, where they bridged clusters from one sheet edge to the other -- the
# reference `tolerance` box came out spanning x 8.4->411.6, 21.4% of the sheet.
#
# 9% clears the outer ring by 0.5pp. It is safe to widen this far only because
# `is_grid_char` is a tight predicate: the nearest non-grid text in the same band is
# multi-character ('M745203N01' at 8.28%, 'DWG.No.' at 8.95%) or a CJK single character
# ('行', '号', '発') that no branch below matches. A bare digit 1-12 that is genuine
# content and sits within 9% of an edge would be wrongly dropped; that exposure existed at
# 6% and is widened, not introduced, here.
GRID_LABEL_MARGIN_FRACTION = DEFAULT_PARAMS.grid_label_margin_fraction


def is_margin_grid_text(e, bounds: Optional[tuple]) -> bool:
    """Helper to detect horizontal (1-12) or vertical (A-H) margin reference labels."""
    if not bounds:
        return False
    geom = getattr(e, "geometry", {}) or {}
    if "insert" not in geom or len(geom["insert"]) < 2:
        return False
    x, y = geom["insert"][0], geom["insert"][1]

    min_x, min_y, max_x, max_y = bounds
    w, h = max_x - min_x, max_y - min_y
    if w <= 0 or h <= 0:
        return False

    # NFKC first. This standard draws its frame labels full-width (U+FF21 'Ａ', U+FF11
    # '１'), which compare unequal to the ASCII forms below, so without normalising this
    # function returned False for every grid label on every drawing in the corpus and the
    # filter at its one call site was inert. `orchestrator.is_in_margin` normalised and
    # this did not -- the two had drifted apart, which is why the bug survived.
    val = unicodedata.normalize(
        "NFKC",
        str(e.properties.get("text") or e.properties.get("value") or "").strip(),
    )
    is_grid_char = (
        val in {"A", "B", "C", "D", "E", "F", "G", "H"} or
        (val.isdigit() and 1 <= int(val) <= 12) or
        any(char in val for char in "①②③④⑤⑥⑦⑧⑨⑩⑪⑫")
    )
    if not is_grid_char:
        return False

    margin_x = w * GRID_LABEL_MARGIN_FRACTION
    margin_y = h * GRID_LABEL_MARGIN_FRACTION
    return (x < min_x + margin_x or x > max_x - margin_x or
            y < min_y + margin_y or y > max_y - margin_y)


def detect_zones_by_content(entities: list) -> dict:
    """
    Content-aware zone detection.

    For each known zone type, scans the drawing for semantic anchor texts,
    then flood-fills a tight bounding box around the anchors spatial cluster.

    Returns a dict where each key is a zone name and each value is either:
        - (xmin, ymin, xmax, ymax)  -- confident content-anchored detection
        - None                      -- no anchor found; caller uses fallback

    The special "safe_zones" key returns a list of all non-engineering zones
    that should be EXCLUDED from comparison (tolerance, title, bom header row).
    """
    # Compute sheet bounds for minimum-size validation using drawing lines/boundaries
    bounds = _get_drawing_bounds(entities)
    if bounds:
        min_x, min_y, max_x, max_y = bounds
    else:
        min_x, min_y, max_x, max_y = 0.0, 0.0, 1000.0, 1000.0
    sheet_w = (max_x - min_x) if (max_x - min_x) > 0 else 1000.0
    sheet_h = (max_y - min_y) if (max_y - min_y) > 0 else 1000.0

    # Filter out margin grid texts from the entity search pool to prevent runaway cluster bridging
    filtered_entities = [e for e in entities if not is_margin_grid_text(e, bounds)]

    # A zone must cover at least 3% of the sheet in BOTH dimensions to be trusted.
    # If it's smaller, it means the anchor hit a tiny cluster (e.g. one text entity)
    # and the flood-fill didn't expand properly — discard and fall back to percentage.
    MIN_ZONE_FRACTION = 0.03

    zones: dict = {}
    # Which anchor phrase actually resolved each zone, per drawing. Two drawings can both
    # report a zone as `content_aware` while having matched entirely different signatures --
    # their boxes are then not really comparable, and the zone's measured "instability" is
    # partly a measurement of anchor disagreement rather than of the drawings.
    anchor_matches: dict = {}

    for zone in ZONE_ANCHORS:
        hits = _find_anchor_positions(filtered_entities, zone)

        # Apply quadrant-filtering to anchor hits to prevent keyword/signature collisions
        if hits:
            if zone == "title_upper_left":
                # Top-left quadrant filter
                hits = [p for p in hits if p[0] < min_x + 0.45 * sheet_w and p[1] > min_y + 0.50 * sheet_h]
            elif zone == "title":
                # Bottom-right quadrant filter
                hits = [p for p in hits if p[0] > min_x + 0.45 * sheet_w and p[1] < min_y + 0.45 * sheet_h]
            elif zone == "tolerance":
                # Bottom strip filter
                hits = [p for p in hits if p[1] < min_y + 0.45 * sheet_h]
            elif zone == "bom":
                # Top-right/right region filter
                hits = [p for p in hits if p[0] > min_x + 0.50 * sheet_w and p[1] > min_y + 0.35 * sheet_h]
            elif zone == "iso":
                # General drawing area, typically right/upper-right
                hits = [p for p in hits if p[0] > min_x + 0.30 * sheet_w]
            elif zone == "notes":
                # Keep notes above the bottom tolerance strip block
                hits = [p for p in hits if p[1] > min_y + 0.15 * sheet_h]

        if hits:
            # Recorded after quadrant filtering, so it reflects the anchors that actually
            # seeded the box rather than every phrase that matched somewhere on the sheet.
            anchor_matches[zone] = sorted({p[2] for p in hits if len(p) > 2})

            max_w_frac, max_h_frac = ZONE_MAX_LIMITS.get(zone, (0.5, 0.5))

            # Select zone-specific scale-aware cluster radius
            if zone == "title_upper_left":
                # Decouple X/Y radii: span across table columns horizontally and encompass value row below headers
                radius = (max(80.0, sheet_w * 0.20), max(35.0, sheet_h * 0.08))
            elif zone == "bom":
                # Decouple X/Y radii: wide horizontally to span columns, tight vertically to avoid detail views
                radius = (max(50.0, sheet_w * 0.15), max(15.0, sheet_h * 0.04))
            elif zone == "tolerance":
                # Decouple X/Y radii, same reasoning as `bom`: the tolerance table is a wide,
                # short strip of ruled columns along the bottom of the sheet, so it needs to
                # bridge horizontally across columns but must NOT reach upward into the
                # drawing area.
                #
                # With CLUSTER_RADIUS (200, isotropic) and lines included, the flood-fill blew
                # out to BOTH caps on both drawings of the M7452A1N01 pair -- 0.95w x 0.30h
                # exactly, the signature of runaway growth rather than a detection. It walked
                # the sheet frame and table rules across the full width and ~150 units above
                # the table, swallowing the drawing's own content: the `22.7±0.02` dimension,
                # the `6-6.6キリ11ザグリ深6.5` callout and the section marks. Because
                # `tolerance` is a SAFE zone that `views` subtracts, everything it swallowed
                # was silently dropped from the drawing_views comparison and never checked.
                radius = (max(50.0, sheet_w * 0.15), max(12.0, sheet_h * 0.03))
            elif zone == "notes":
                radius = max(15.0, sheet_h * 0.03)
            elif zone == "shim":
                # Compact table: rows sit a few units apart, so a tight radius still bridges
                # the whole table via single-linkage while keeping surrounding drawing
                # geometry out. CLUSTER_RADIUS (200) would over-sweep the small-coordinate
                # revision, where the whole table is ~57 units wide.
                radius = max(20.0, sheet_h * 0.05)
            else:
                radius = CLUSTER_RADIUS
                
            # Ruled tables: seed from their text, never from their rules. A table's own frame
            # lines are collinear with the sheet border and with the title block's rules, so
            # letting the flood-fill hop along them bridges the box to unrelated furniture and
            # then to the drawing itself. These zones are all dense with text, so text-only
            # growth still covers them (verified on the M7452A1N01 pair: `tolerance` still
            # covers every row of its table while dropping from 30.0% to 14.7% of sheet
            # height, and the ⌀ dimensions above it stay in `views`).
            exclude_lines_flag = (zone in ("title_upper_left", "bom", "notes", "tolerance"))
            bbox = _expand_bbox(
                filtered_entities, hits, radius,
                max_w=sheet_w * max_w_frac,
                max_h=sheet_h * max_h_frac,
                exclude_lines=exclude_lines_flag
            )
            if bbox is not None:
                bw = bbox[2] - bbox[0]
                bh = bbox[3] - bbox[1]

                is_valid_size = False
                if zone in ("title_upper_left", "notes"):
                    # Upper-left title and notes can be narrow or short, allow smaller size
                    is_valid_size = (bw >= 10.0 or bw >= sheet_w * 0.005) and (bh >= 10.0 or bh >= sheet_h * 0.005)
                else:
                    is_valid_size = (bw >= sheet_w * MIN_ZONE_FRACTION) and (bh >= sheet_h * MIN_ZONE_FRACTION)

                if is_valid_size:
                    zones[zone] = bbox
                else:
                    # Too small — degenerate anchor, fall back to percentage default
                    zones[zone] = None
            else:
                zones[zone] = None
        else:
            zones[zone] = None

    # `iso` is resolved geometrically rather than by text anchors, which have never
    # matched it. Runs after the anchor loop so a genuine text hit is only overridden
    # by the stronger signal, and before `views` is derived, because views is defined
    # by exclusion and must see the iso box to exclude it.
    iso_bbox = _detect_iso_zone(filtered_entities, bounds)
    if iso_bbox is not None:
        max_w_frac, max_h_frac = ZONE_MAX_LIMITS["iso"]
        zones["iso"] = _clamp_bbox(iso_bbox, sheet_w * max_w_frac, sheet_h * max_h_frac)

    # `views` is the sheet; the exclusion that defines it lives in `in_views`, not in the box.
    #
    # `bounds`, NOT the (min_x..max_y) effective rect: those fall back to a literal
    # 0..1000 placeholder when the drawing has no measurable frame, and returning that would
    # mark `views` as `content_aware` — claiming a measurement of a sheet that could not be
    # measured. Passing the real bounds lets it stay None and fall through to the percentage
    # grid, which is what every other zone does in that situation.
    zones["views"] = _derive_views_zone(entities, zones, bounds)

    # Collect all confirmed safe zones (template blocks that must not be compared)
    # The "tolerance" and "shim" zones are always safe; BOM header rows and title field
    # labels are also static but the actual VALUES inside BOM rows must still be checked.
    # `shim` (the シム表 assembly-thickness table) is reference data like tolerance, not a
    # field that meaningfully changes between revisions -- excluded from comparison, never
    # diffed as its own category.
    zones["safe_zones"] = [
        v for k, v in zones.items()
        if k in ("tolerance", "shim") and v is not None
    ]

    # Diagnostics, under a reserved underscore key so it cannot be mistaken for a bbox --
    # the same smuggle-an-extra-key pattern as `safe_zones` and `_zone_confidence`.
    # `extract_dynamic_regions` skips underscore keys when copying zones across.
    zones["_anchor_matches"] = anchor_matches

    return zones


def _derive_views_zone(entities: list, detected: dict, sheet: Optional[tuple] = None) -> Optional[tuple]:
    """The drawing area: the sheet. The exclusion lives in `in_views`, not in this box.

    `views` is defined by exclusion — it is whatever is not sheet furniture or a floating
    annotation block — which makes it irregular by construction. It was previously reduced to
    a rectangle by taking the 5–95 percentile of non-excluded content and padding it. Two
    things were wrong with that:

    * It was not a bound. Measured across the corpus on 2026-07-29 the resulting box
      covered 119.7% of the sheet — larger than the drawing — because the percentile is of
      content that extends past the line-derived frame, and then padding is added on top.
    * It was not exact either. Anything in the outer 5% of the drawing area fell outside
      the box, so a containment test produced false negatives at exactly the sheet edges where
      views content legitimately reaches.

    Returning the sheet makes the pair `views` + `views_exclusions()` exact:
    `inside(sheet) AND NOT inside(any other zone)`. `entities` and `detected` are retained in
    the signature because the call site passes them and because a future caller may want to
    fall back to a content extent for a sheet with no measurable frame.

    Every consumer that treats `views` as a containment region MUST subtract the sibling zones
    — use `in_views()`. Consumers that pass it as a search `region_bbox` must pass
    `views_exclusions()` alongside, which `coordinate_resolver` and `detect_subviews` do.
    """
    if sheet and len(sheet) == 4:
        return tuple(float(v) for v in sheet)
    return None


def in_views(x: float, y: float, regions: dict) -> bool:
    """Exact drawing-area test: on the sheet, and inside no other zone.

    This is the predicate `views` actually is. Prefer it over a raw bbox containment check
    against `regions["views"]`, which is only the outer bound and admits every title block,
    BOM row and notes line on the sheet.
    """
    views = (regions or {}).get("views")
    if not views or len(views) != 4:
        return False
    if not (views[0] <= x <= views[2] and views[1] <= y <= views[3]):
        return False
    return not point_in_any_bbox(x, y, views_exclusions(regions))


VIEW_LABEL_PATTERNS = [
    r'(?:section|sec\.|断面|断面図)\s*([a-z0-9\-]+)',
    r'(?:detail|det\.|詳細|詳細図)\s*([a-z0-9\-]+)',
    r'(?:view|矢視|矢視図)\s*([a-z0-9\-]+)',
    r'(?:front|top|side|rear|正面|平面|側面|底面|正面図|平面図|側面図)(?:\s*図)?',
    r'\b(?:s|scale)\s*=\s*\d+\s*[:/]\s*\d+\b'
]

EXCLUDE_VIEW_LABEL_PATTERNS = [
    r'^(?:注\s*\d*|注記|notes?:?|remark:?|title|scale|drawn|approved|checked)',
    r'^[\d\u2460-\u2473\u2474-\u2487]+[\.\)\uff0e\uff09\u30fb:：]?\s*',  # Handles ASCII (1., 1)), Full-Width (１．, １）), & Circled/Parenthesized JIS Numerals (①, ②, ⑴)
]

def detect_subviews(
    entities: list,
    views_bbox: Optional[tuple] = None,
    exclude_bboxes: Optional[list] = None,
) -> list:
    """
    Detects individual view label anchors (SECTION A-A, DETAIL B, TOP VIEW, S=2:1, etc.)
    and clusters surrounding CAD entities to construct tagged sub-view bounding boxes.
    Returns a list of dicts: [{"label": str, "bbox": (xmin, ymin, xmax, ymax), "anchor": (x, y)}]
    If no sub-view anchors exist, returns [] (caller falls back to single views_bbox).

    `exclude_bboxes` carries the exclusion that `views` loses when it comes from a template
    instead of the detector. A pinned `views` is a plain rectangle over the whole drawing
    area, so without this the notes block and title text sitting inside that rectangle get
    clustered into sub-views as though they were drawing geometry. Pass
    `views_exclusions(regions)`.
    """
    import re

    anchors = []
    for e in entities:
        if getattr(e, "entity_type", "") not in ("text", "mtext"):
            continue
        raw_txt = e.properties.get("text", "") if getattr(e, "properties", None) else ""
        if not raw_txt:
            continue
        txt_norm = strip_mtext(safe_decode(raw_txt)).strip()
        txt_lower = txt_norm.lower()

        # Skip note markers, title block fields, and general note callouts
        if any(re.search(pat, txt_lower, re.IGNORECASE) for pat in EXCLUDE_VIEW_LABEL_PATTERNS):
            continue

        for pat in VIEW_LABEL_PATTERNS:
            if re.search(pat, txt_lower, re.IGNORECASE):
                xy = _get_xy(e)
                if xy:
                    # Enforce that the anchor lies within the overall views zone if provided
                    if views_bbox:
                        bx0, by0, bx1, by1 = views_bbox
                        if not (bx0 <= xy[0] <= bx1 and by0 <= xy[1] <= by1):
                            continue
                    if point_in_any_bbox(xy[0], xy[1], exclude_bboxes):
                        continue
                    anchors.append({"label": txt_norm, "anchor": xy, "entities": []})
                    break

    if not anchors:
        return []

    # Compute maximum allowed anchor distance (empirically validated 30% of sheet diagonal) to prevent misassigning boundary entities
    sheet_diag = math.hypot(views_bbox[2] - views_bbox[0], views_bbox[3] - views_bbox[1]) if views_bbox else 1000.0
    max_anchor_dist = sheet_diag * 0.30

    # Filter out text/line entities in the views area and assign to closest anchor (Voronoi clustering with distance cutoff)
    for e in entities:
        etype = getattr(e, "entity_type", "")
        if etype not in ("dimension", "line", "polyline", "text", "mtext", "arc", "circle"):
            continue
        xy = _get_xy(e)
        if not xy:
            continue
        if views_bbox:
            bx0, by0, bx1, by1 = views_bbox
            if not (bx0 <= xy[0] <= bx1 and by0 <= xy[1] <= by1):
                continue
        if point_in_any_bbox(xy[0], xy[1], exclude_bboxes):
            continue

        # Find closest anchor by Euclidean distance
        closest_anchor = min(
            anchors,
            key=lambda a: math.hypot(xy[0] - a["anchor"][0], xy[1] - a["anchor"][1])
        )
        dist = math.hypot(xy[0] - closest_anchor["anchor"][0], xy[1] - closest_anchor["anchor"][1])
        if dist <= max_anchor_dist:
            closest_anchor["entities"].append(xy)

    # Compute bounding boxes for each cluster
    subviews = []
    for a in anchors:
        pts = a["entities"]
        if not pts:
            continue
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        bbox = (
            min(xs) - BBOX_PADDING,
            min(ys) - BBOX_PADDING,
            max(xs) + BBOX_PADDING,
            max(ys) + BBOX_PADDING,
        )
        subviews.append({
            "label": a["label"],
            "bbox": bbox,
            "anchor": a["anchor"]
        })

    return subviews

