"""
zone_detector.py
================
Content-Aware Zone Detector for 2D CAD Engineering Drawings.

Instead of relying on layer names or blind percentage grids, this module
identifies drawing zones by finding semantic **anchor text signatures** that
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
import unicodedata
from typing import Any, Optional

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
        "表示外公差",
        "一般公差",
        "普通公差",
        "普通寸法許容差",
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
        "unit no",
        "unit no.",
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
        "仕上げ",
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
}

# How close (in CAD units) another entity must be to an anchor seed
# to be swept into that zone's bounding box
CLUSTER_RADIUS = 200.0

# Safety padding added around the final computed bounding box
BBOX_PADDING = 30.0


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


# ---------------------------------------------------------------------------
# Core: Semantic Anchor Detection
# ---------------------------------------------------------------------------

def _find_anchor_positions(entities: list, zone: str) -> list:
    """
    Scan all text entities for anchor signatures belonging to ``zone``.
    Returns a list of (x, y) positions for each match found.
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
                    hits.append(xy)
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
    return (xmin - padding, ymin - padding,
            xmax + padding, ymax + padding)


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
        
    val = str(e.properties.get("text") or e.properties.get("value") or "").strip()
    is_grid_char = (
        val in {"A", "B", "C", "D", "E", "F", "G", "H"} or
        (val.isdigit() and 1 <= int(val) <= 12) or
        any(char in val for char in "①②③④⑤⑥⑦⑧⑨⑩⑪⑫")
    )
    if not is_grid_char:
        return False
        
    # Grid markers are always located in the outer 6.0% margin of the sheet
    margin_x = w * 0.06
    margin_y = h * 0.06
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

    # Define physical limits for maximum zone size to prevent runaways
    ZONE_MAX_LIMITS = {
        "tolerance": (0.95, 0.30),        # spans nearly the full width of the bottom strip
        "bom": (0.45, 0.65),
        "title": (0.60, 0.35),
        "title_upper_left": (0.40, 0.35),
        "notes": (0.45, 0.65),
        "iso": (0.45, 0.45)
    }

    zones: dict = {}

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
            max_w_frac, max_h_frac = ZONE_MAX_LIMITS.get(zone, (0.5, 0.5))
            
            # Select zone-specific scale-aware cluster radius
            if zone == "title_upper_left":
                radius = max(8.0, sheet_h * 0.02)
            elif zone == "bom":
                # Decouple X/Y radii: wide horizontally to span columns, tight vertically to avoid detail views
                radius = (max(50.0, sheet_w * 0.15), max(15.0, sheet_h * 0.04))
            elif zone == "notes":
                radius = max(15.0, sheet_h * 0.03)
            else:
                radius = CLUSTER_RADIUS
                
            exclude_lines_flag = (zone in ("title_upper_left", "bom", "notes"))
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

    # The "views" zone is derived by exclusion - everything NOT in a safe zone
    zones["views"] = _derive_views_zone(entities, zones)

    # Collect all confirmed safe zones (template blocks that must not be compared)
    # The "tolerance" zone is always safe; BOM header rows and title field labels
    # are also static but the actual VALUES inside BOM rows must still be checked.
    zones["safe_zones"] = [
        v for k, v in zones.items()
        if k == "tolerance" and v is not None
    ]

    return zones


def _derive_views_zone(entities: list, detected: dict) -> Optional[tuple]:
    """
    The views zone is the main drawing area - everything that is NOT
    covered by a tolerance table, BOM, title block, notes section, or ISO view.
    """
    excluded = [v for k, v in detected.items() if v is not None]

    def in_excluded(x: float, y: float) -> bool:
        for bbox in excluded:
            if bbox and bbox[0] <= x <= bbox[2] and bbox[1] <= y <= bbox[3]:
                return True
        return False

    view_xs = []
    view_ys = []

    for e in entities:
        etype = getattr(e, "entity_type", "")
        if etype in ("dimension", "line", "polyline", "text", "mtext"):
            xy = _get_xy(e)
            if xy and not in_excluded(xy[0], xy[1]):
                view_xs.append(xy[0])
                view_ys.append(xy[1])

    if len(view_xs) < 4:
        return None

    view_xs.sort()
    view_ys.sort()
    lo = max(0, int(len(view_xs) * 0.05))
    hi = min(len(view_xs) - 1, int(len(view_xs) * 0.95))

    return (
        view_xs[lo] - BBOX_PADDING,
        view_ys[lo] - BBOX_PADDING,
        view_xs[hi] + BBOX_PADDING,
        view_ys[hi] + BBOX_PADDING,
    )
