"""The deterministic comparison engine: every candidate finding, and the rules that filter them.

Split out of `orchestrator.py`, which had grown to 2049 lines around a single 1334-line
function with 21 nested closures. The closures were promoted to module level first and the
whole sequence measured byte-identical against `tools/eval.py --baseline` at each step -- see
[[Gotcha - A Swept Constant Must Be Bound To The Module That Reads It]] for the one thing that
move could have broken silently.

`orchestrator.py` now holds only `perform_drawing_comparison`: the cache check, the
AuditSession/AuditViolation writes, and the post-cache learned-correction pass. It imports
`generate_deterministic_candidates` from here and calls it by its bare module-global name, so
`monkeypatch.setattr(orchestrator, "generate_deterministic_candidates", ...)` still intercepts
it -- `tests/test_comparison_architecture.py` depends on that.

> [!WARNING] `MIN_STRUCTURED_VALUE_LENGTH` lives here, not in `orchestrator`, because this is
> the module that READS it. `params._BINDINGS` is bound to this module accordingly, and
> `tests/test_comparison_params.py::test_the_bound_module_is_the_one_that_reads_the_constant`
> fails if the two ever drift. A binding naming the declaring module rather than the reading
> one makes `sweep_override` rebind a constant nothing consumes -- the sweep then reports the
> parameter as having no effect, which is indistinguishable from a real negative result.
"""

import os
import re
import json
import asyncio
import unicodedata
from google.genai import types

from ....domain.models.drawing_document import DrawingDocument
from ....domain.models.extracted_entity import ExtractedEntity
from ....logger import logger
from ....config import settings
from ...storage.path_resolver import get_storage_root
from ...utils.text import (
    extract_semantic_text_groups,
    build_title_block_table,
    compare_values
)
from ..bom_analyzer import BOMAnalyzer
from .params import DEFAULT_PARAMS
from .revision_resolver import resolve_revisions

# Shortest structured title-block/BOM value allowed to suppress its text-twins elsewhere on the
# sheet. Module-level and bound into `params._BINDINGS` so `sweep_override` can rebind it; read
# inside `generate_deterministic_candidates` at call time, never captured at import.
# See the block above `_collect_structured_text_values` for why a floor is needed at all.
MIN_STRUCTURED_VALUE_LENGTH = DEFAULT_PARAMS.min_structured_value_length
from .hallucination_guardrails import (
    is_title_block_category,
    is_bom_category,
    is_admin_bom_marking
)
from .marking_builder import (
    inject_title_block_markings,
    inject_bom_markings,
    inject_ballooning_markings,
    generate_auto_matched_markings
)
from .coordinate_resolver import resolve_marking_coordinates, harden_value_only_coordinates
from .line_attribute_differ import diff_line_attributes
from .marking_reconciler import reconcile_relocated_markings
from .schemas import Coordinate2D, BoundingBox2D
from .cache_manager import ComparisonCacheManager
from .candidate import ComparisonCandidate
from . import taxonomy
from .feature_classifier import (
    classify_drawing_view_feature,
    classify_notes_feature,
    classify_iso_feature,
    refine_view_labels,
    classify_title_ul_feature,
)
from .notes_classifier import classify_notes
from ..bom.zone_ownership import owner_of


# Column headers of the amendment / revision-history table, matched EXACTLY against
# NFKC-normalised lowercase text.
#
# This table is title-block furniture, but it is not reliably *inside* the detected
# `title` box. Measured on the KEMCO pair bc17b56d / 63adc691 (2026-07-30): on the
# revision it sits at x 338-402, inside `title`; on the reference the same table sits
# bottom-left at x 28-129 while `title` starts at x 152. `title`'s bottom-right quadrant
# filter excludes bottom-left anchors by design, and widening `title` to reach across
# would breach its 0.60 width cap and swallow the sheet's bottom strip. So the headers are
# excluded by text, which is position-independent and survives the two sheets disagreeing
# about where the table lives.
#
# Headers only. The table's *values* (old drawing numbers, dates, amendment codes) are
# real content and a genuine revision changes them -- '2491FSRS' and 'M745203N01' stay in
# the comparison. Exact match, never substring: 'name' is short enough that substring
# matching would suppress unrelated text.
# Drop section-callout labels (`Ａ－Ａ` and the lone `Ａ` at each cut arrow) from the
# drawing_views checklist. Identified by `feature_classifier.refine_view_labels`, which uses
# drawing context rather than text alone -- a lone letter only counts when that drawing also
# carries the matching `X-X` designation.
#
# This suppresses a finding that is factually CORRECT. On the M7452A1N01 pair the reference has
# no section callout at all (its only `Ａ` texts are two frame grid labels on layer WAKU, and no
# block carries it as an ATTRIB) and the revision genuinely adds one, so it is a real
# difference. It is excluded because the section IDENTIFIER is draughting furniture: which
# letter names a cut says nothing about the part, and it re-letters freely between revisions.
# The section's actual content -- the dimensions, callouts and symbols inside the view it names
# -- is compared exactly as before, so nothing about the geometry goes unchecked.
#
# The cost, stated plainly: a revision that adds or removes a section view now reports the
# change in that view's contents but not the callout itself. Set this False to get it back.
DROP_SECTION_CALLOUT_LABELS: bool = True

REVISION_TABLE_HEADERS: frozenset = frozenset({
    "amd.", "amd",
    "design chg no.", "design chg no",
    "previous dwg. no,", "previous dwg. no.", "previous dwg no",
    "y/m/d",
    "name",
    "旧図面番号",
    "旧工事番号",
    "訂正符号",
    "設計訂正書no.", "設計訂正書no",
    "年月日",
    "担当",
    "符号",
})


# Layer-name substrings that mark an entity as sheet furniture (frame / title block / tolerance
# table / BOM labels) rather than drawing content, so drawing_views must not diff it. "waku" is
# the romanization of 枠 (frame/border): KMTI AutoCAD sheets put ALL furniture on a layer named
# "WAKU", and the kanji check alone never fired because the layer name is romaji. SolidWorks-
# derived sheets have no such named layer (everything is NoLayerName_00x) and rely on the
# geometric zone boxes instead — this predicate only helps the AutoCAD side, which is where a
# clean furniture layer actually exists. Module-level and pure so it is unit-testable without
# standing up the whole comparison pipeline.
FURNITURE_LAYER_TOKENS: tuple = ("tol", "tolerance", "公差", "枠", "waku")


def is_furniture_layer(layer: str) -> bool:
    """True when the layer name marks an entity as sheet furniture, not drawing content."""
    layer_lc = (layer or "").lower()
    return any(tok in layer_lc for tok in FURNITURE_LAYER_TOKENS)


def _point_in_bbox(insert, bbox) -> bool:
    """True if an entity insert point (x, y[, z]) falls inside bbox (xmin, ymin, xmax, ymax)."""
    if not bbox or not insert or len(insert) < 2:
        return False
    return bbox[0] <= insert[0] <= bbox[2] and bbox[1] <= insert[1] <= bbox[3]


def keep_for_title_extraction(entity, tolerance_bbox, title_bbox, title_ul_bbox=None) -> bool:
    """Whether to feed `entity` to the title-block extractor.

    Two zones are excluded, for the same reason: both are read by their OWN extractor, and
    anything the title-block field search finds inside them is a second reading of a cell that
    is already reported.

    * **Tolerance table** — its numeric cells were being misread as title fields.
    * **Upper-left table** — `extract_title_ul_kv` owns it. The bottom title block's `QTY`
      field searches for the labels ``T. Q'ty`` / ``総製作個数``, which is precisely the
      upper-left table's own column header, so the proximity search walked hundreds of units
      up the sheet and read that table's cell. The value then surfaced twice in one checklist:
      as `QTY (QUANTITY)` from the title-block extractor and as `T. Q'TY / 総製作個数` from the
      upper-left extractor, both grounded to the same marker.

    Guard, for both: drop an entity only when it is in the excluded box AND NOT in the title
    box. The detected/pinned tolerance box is frequently OVER-WIDE — spanning the full bottom
    strip — and then it also covers the bottom-right title block, so a naive
    `not is_in_bbox(e, tolerance_bbox)` deletes the real title fields and every one reads NONE
    (DRAWN/SCALE/DESIGNED/TITLE). The same protection is extended to the upper-left box so a
    mis-detected one cannot blank the title block either, and so a sheet whose bottom title
    block carries its *own* quantity cell keeps it.
    """
    geom = getattr(entity, "geometry", {}) or {}
    insert = geom.get("insert")
    in_excluded = _point_in_bbox(insert, tolerance_bbox) or _point_in_bbox(insert, title_ul_bbox)
    in_title = _point_in_bbox(insert, title_bbox)
    return not (in_excluded and not in_title)


def _amendment_norm(t) -> str:
    """NFKC + strip + lowercase, matching orchestrator's _normalize_value_text."""
    import unicodedata
    return unicodedata.normalize("NFKC", str(t or "")).strip().lower()


def amendment_table_bboxes(entities: list, global_bounds: tuple | None) -> list:
    """Bounding boxes of the amendment / revision-history table(s) on one drawing.

    The table is title-block furniture but has no fixed position -- on the measured KEMCO
    pair it sits bottom-left on the reference (x 28-129, outside the `title` box) and inside
    `title` on the revision. So it is located by clustering its own column-header anchors
    (REVISION_TABLE_HEADERS), not by a quadrant like the ZONE_ANCHORS zones.

    The boxes are used ONLY to reclassify drawing_views findings to title_block, never to
    exclude entities from comparison. A loose or wrong cluster therefore mislabels a finding
    at worst and can never drop one -- which is why the padding and join constants here can
    be approximate without risking a false negative, the one number this system does not yet
    measure. Guards: a cluster needs >= 2 headers (a lone 'Name' in a note is not a table),
    and any box exceeding 20% of the sheet is discarded rather than allowed to relabel a
    fifth of the drawing.
    """
    def _pt(e):
        g = getattr(e, "geometry", {}) or {}
        loc = g.get("insert") or g.get("location") or g.get("text_point")
        return (loc[0], loc[1]) if loc and len(loc) >= 2 else None

    pts = []
    for e in entities:
        props = getattr(e, "properties", {}) or {}
        if _amendment_norm(props.get("text") or props.get("value") or "") in REVISION_TABLE_HEADERS:
            p = _pt(e)
            if p:
                pts.append(p)
    if len(pts) < 2:
        return []

    if global_bounds:
        gw = global_bounds[2] - global_bounds[0]
        gh = global_bounds[3] - global_bounds[1]
        diag = (gw * gw + gh * gh) ** 0.5
    else:
        gw = gh = 0.0
        diag = 1000.0
    join = diag * 0.06  # a table's headers sit within a row or two of each other

    clusters: list = []
    for p in pts:
        for c in clusters:
            if any(((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2) ** 0.5 <= join for q in c):
                c.append(p)
                break
        else:
            clusters.append([p])

    boxes = []
    for c in clusters:
        if len(c) < 2:
            continue
        xs = [q[0] for q in c]
        ys = [q[1] for q in c]
        x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
        # Pad to take in the value cells and the amendment row-letter column, which run
        # beyond the header row (the row letters sit ABOVE the headers on the reference,
        # hence the larger vertical pad).
        pad_x = max(20.0, (x1 - x0) * 0.25)
        pad_y = max(30.0, (y1 - y0) * 0.50)
        bx = (x0 - pad_x, y0 - pad_y, x1 + pad_x, y1 + pad_y)
        if gw > 0 and gh > 0:
            if ((bx[2] - bx[0]) * (bx[3] - bx[1])) / (gw * gh) > 0.20:
                continue
        boxes.append(bx)
    return boxes


# Title-upper-left pairing now lives in `title_matcher.py`. Re-exported here because this
# module is the historical import site: `tests/test_title_ul_matching.py`,
# `test_title_ul_release.py`, `test_title_ul_value_band.py`, `test_title_ul_bilingual_pairing.py`
# and `test_title_input_filter.py` all import these names from `orchestrator`.
# Unused *here* on purpose — every name below is re-exported for an existing importer, so
# the per-line `noqa` is the marker that this is a deliberate public surface and not dead
# weight. (`X as X` would say the same thing to F401 but trips PLC0414, which this repo
# enables via `select = [... "PL"]`.)
from .title_matcher import (  # noqa: E402
    UL_BAND_GAP_OUTLIER_FACTOR,  # noqa: F401
    UL_COLUMN_SPLIT_RATIO,  # noqa: F401
    _TITLE_UL_SYNONYMS,  # noqa: F401
    _title_ul_tokens,  # noqa: F401
    _ul_canonical,  # noqa: F401
    _ul_columns,  # noqa: F401
    _ul_synonym_groups,  # noqa: F401
    extract_title_ul_kv,
    match_title_ul_pairs,  # noqa: F401
    partition_ul_pairs,  # noqa: F401
    ul_value_band_index,  # noqa: F401
)


def build_marking_table(markings: list, category_filter: str | None = None) -> str:
    """
    Build a pipe-table summary from a list of marking dicts for the checklist panel.

    Module-level (hoisted out of generate_deterministic_candidates, where it started as
    a nested closure — it doesn't close over anything, so the move is behavior-neutral)
    so the removed `hybrid` orchestrator could rebuild category tables from its final
    reconciled list rather than Generator A's raw output. That caller is gone (ADR-006);
    the hoist stays because it is behaviour-neutral and re-nesting it would be churn.
    """
    rows = [m for m in markings if category_filter is None or m.get("category") == category_filter]
    if not rows:
        return ""
    header = f"{'ANNOTATION':<36}| {'ORIGINAL':<24}| {'REVISION':<24}| STATUS"
    sep = "-" * len(header)
    lines = [header, sep]
    for m in rows:
        text = (m.get("text_content") or "")[:34]
        status = m.get("status", "MATCHED")
        if status == "ADDED":
            orig = "NONE"
            rev = (m.get("text_content") or "")[:22]
        elif status in ("DELETED", "REMOVED"):
            orig = (m.get("original_value") or m.get("text_content") or "")[:22]
            rev = "NONE"
        else:
            orig = (m.get("original_value") or m.get("text_content") or "")[:22]
            rev = (m.get("text_content") or "")[:22]
        lines.append(f"{text:<36}| {orig:<24}| {rev:<24}| {status}")
    return "\n".join(lines)


# ─── helpers lifted out of generate_deterministic_candidates ──────────────────────────
#
# These captured nothing from the enclosing scope (verified with `symtable`: zero free
# variables), so promoting them is a pure relocation — every call site still resolves the
# same bare name, now as a module global rather than a closure cell.
#
# They are lifted first because the function they came from is 1334 lines, and a helper
# that is unreachable from a test is a helper whose behaviour is asserted only through the
# whole engine. Nothing else about the call sites changes.


# Zone membership lives in `bom/zone_geometry.py` next to `point_in_shape`, so the
# comparison layer and `title_matcher` share one answer to "is this entity in this zone".
# Re-exported here because this module is the historical import site.
from ..bom.zone_geometry import is_in_bbox  # noqa: E402


def is_in_margin(entity, bounds: tuple) -> bool:
    if not bounds: return False
    geom = getattr(entity, 'geometry', {})
    if not geom or 'insert' not in geom or len(geom['insert']) < 2: return False
    x, y = geom['insert'][0], geom['insert'][1]

    min_x, min_y, max_x, max_y = bounds
    width, height = max_x - min_x, max_y - min_y
    if width <= 0 or height <= 0: return False

    # Sheet-frame grid labels are delegated rather than re-implemented. This function
    # and zone_detector.is_margin_grid_text were duplicates that had silently drifted:
    # only this copy normalised NFKC, so full-width labels were dropped here and kept
    # during zone detection, where they bridged clusters across the sheet. One
    # definition, one threshold.
    from ..bom.zone_detector import is_margin_grid_text
    if is_margin_grid_text(entity, bounds):
        return True

    margin_x = width * 0.025
    margin_y = height * 0.025

    return (x < min_x + margin_x or x > max_x - margin_x or
            y < min_y + margin_y or y > max_y - margin_y)


def _bbox_covers_too_much(bbox: tuple | None, global_bounds: tuple | None, max_fraction: float = 0.70) -> bool:
    """Return True if bbox is so large it covers more than max_fraction of the drawing sheet.
    That is a sign of a failed zone detection — we must NOT use it for exclusion."""
    if not bbox or not global_bounds:
        return False
    bw = bbox[2] - bbox[0]
    bh = bbox[3] - bbox[1]
    gw = global_bounds[2] - global_bounds[0]
    gh = global_bounds[3] - global_bounds[1]
    if gw <= 0 or gh <= 0:
        return False
    area_fraction = (bw * bh) / (gw * gh)
    return area_fraction > max_fraction


def _learned_rules_for(category: str) -> list:
    """Learned dismissals a human confirmed *in this category*, and nowhere else.

    Returns [] on any failure: a vault that cannot be read must not stop a comparison, and
    the failure is already logged once by the drawing_views call site.
    """
    try:
        from ...knowledge.vault_sync import VaultSyncManager
        return VaultSyncManager.get_instance().get_learned_dismissal_rules(category=category)
    except Exception:
        return []


def _is_bom_layer(l: str) -> bool:
    return any(x in l.lower() for x in ("bom", "parts", "material", "partslist", "materials"))


def _is_title_layer(l: str) -> bool:
    return any(x in l.lower() for x in ("title", "border", "stamp", "attr", "admin", "block", "header", "logo", "dwg", "rev", "approved", "checked", "designed", "drawn", "scale"))


def _is_tolerance_layer_or_text(e) -> bool:
    # Frame/furniture layer name (incl. romanized "WAKU" = 枠) — see is_furniture_layer.
    if is_furniture_layer(getattr(e, "layer", "")):
        return True
    raw_t = str(getattr(e, "properties", {}).get("text") or getattr(e, "properties", {}).get("value") or "").strip()
    if not raw_t:
        return False

    # Live dynamic Vault rules (Pillar 1: Vault-to-Runtime Sync)
    from ...knowledge.vault_sync import VaultSyncManager
    vault_sync = VaultSyncManager.get_instance()
    vault_patterns = vault_sync.get_surface_roughness_patterns()
    vault_keywords = vault_sync.get_tolerance_keywords()

    for pat in vault_patterns:
        if re.search(pat, raw_t, re.IGNORECASE):
            return True
    norm_t = raw_t.lower().replace(" ", "")
    return any(k in norm_t for k in vault_keywords)


def _pos_in_bboxes(pos, bboxes) -> bool:
    if not pos or len(pos) < 2 or not bboxes:
        return False
    return any(b[0] <= pos[0] <= b[2] and b[1] <= pos[1] <= b[3] for b in bboxes)


def _normalize_value_text(t) -> str:
    return unicodedata.normalize("NFKC", str(t or "")).strip().lower()


def _collect_structured_text_values(*sources) -> set:
    """Structured title-block/BOM values, normalised, for the suppression net.

    ⚠ `MIN_STRUCTURED_VALUE_LENGTH` is read **inside the body, on every call** — never as a
    default argument and never captured at def time. `params.sweep_override` rebinds the
    module global, so a value frozen at definition would make the sweep report this
    parameter as having no effect while the engine quietly ran on the old number.
    `tests/test_comparison_params.py::test_the_bound_module_is_the_one_that_reads_the_constant`
    pins that the read stays in this module; nothing pins *when* it happens but this comment.
    """
    min_structured_len = MIN_STRUCTURED_VALUE_LENGTH
    values: set = set()

    def _add(val) -> None:
        if not val or str(val).strip().upper() == "NONE":
            return
        normalized = _normalize_value_text(val)
        # Too short to identify the entity it would suppress. Dropped from the net rather
        # than from the drawing: the value is still reported by the structured extractor
        # that produced it, so this only stops it silencing an unrelated twin elsewhere.
        if len(normalized) < min_structured_len:
            return
        values.add(normalized)

    for source in sources:
        if isinstance(source, dict):
            # title-field-style: {field_key: {"value": ...} | str}
            for obj in source.values():
                _add(obj.get("value") if isinstance(obj, dict) else obj)
        elif isinstance(source, list):
            # BOM-row-style: [{col_key: {"value": ...} | str, ...}, ...]
            for row in source:
                if not isinstance(row, dict):
                    continue
                for obj in row.values():
                    _add(obj.get("value") if isinstance(obj, dict) else obj)
    return values


def _is_revision_table_header(e) -> bool:
    """Amendment-table column headers, wherever the table sits on the sheet."""
    text = e.properties.get("text") or e.properties.get("value") or ""
    return _normalize_value_text(text) in REVISION_TABLE_HEADERS


def _ul_corroborates(
    value: str,
    missing_side: str,
    ref_entities: list,
    rev_entities: list,
    ref_title_ul_bbox_raw,
    rev_title_ul_bbox_raw,
) -> bool:
    """Is `value` present in the UL box of the side that did not extract it?

    The two entity pools and the two raw UL boxes are passed rather than captured, so this is
    reachable from a test without standing up a whole comparison. `partition_ul_pairs` calls
    its `corroborates` hook with `(value, missing_side)` only, so the call site adapts.
    """
    entities = rev_entities if missing_side == "rev" else ref_entities
    bbox = rev_title_ul_bbox_raw if missing_side == "rev" else ref_title_ul_bbox_raw
    found = BOMAnalyzer.find_drawing_text_coordinates(
        entities, value, category="title_block", region_bbox=bbox, match_level=2,
    )
    return bool(found and found.get("coords"))


# Zones whose content is reference data, not drawing content: a finding inside one is
# suppressed rather than reported. See the safe-zone net's comment at its call site — it is a
# NET, not a fix, and anything it drops is a bug upstream, which is why each drop is logged.
_SAFE_ZONES = ("shim", "tolerance")


def _safe_zone_owner(m: dict, ref_regions: dict, rev_regions: dict) -> str | None:
    """The SAFE zone owning this marking on either side, or None."""
    for pos, regions in (
        (m.get("ref_coordinates"), ref_regions),
        (m.get("coordinates"), rev_regions),
    ):
        if not pos or len(pos) < 2 or pos[0] is None or pos[1] is None:
            continue
        owner = owner_of(pos[0], pos[1], regions)
        if owner in _SAFE_ZONES:
            return owner
    return None


def _other_zone_covers(coords, regions: dict) -> bool:
    """Does any zone OTHER than the upper-left table cover this point?"""
    from ..bom.zone_detector import point_in_any_bbox as _point_in_any_bbox
    if not coords or len(coords) < 2 or not regions:
        return False
    others = [
        (bbox, None)
        for key, bbox in regions.items()
        if key != "title_upper_left" and bbox
    ]
    return _point_in_any_bbox(coords[0], coords[1], others)


def extract_zone_entities(entities: list, bbox: tuple | None, global_bounds: tuple | None, exclude_bboxes: list | None = None, exclude_values: set | None = None, learned_category: str | None = None) -> list:
    if not bbox or _bbox_covers_too_much(bbox, global_bounds):
        return []

    # Scoped learned dismissals. Before this the notes and isometric pools saw NO learned
    # patterns at all — every one of them was applied to drawing_views regardless of the
    # category a human dismissed it in — so the active-learning flywheel closed for exactly
    # one of the three generic zones.
    learned_rules = _learned_rules_for(learned_category) if learned_category else []

    result = []
    for e in entities:
        if is_in_bbox(e, bbox) and not is_in_margin(e, global_bounds):
            should_exclude = False
            if exclude_bboxes:
                for ex_bbox in exclude_bboxes:
                    if is_in_bbox(e, ex_bbox):
                        should_exclude = True
                        break
            if not should_exclude and exclude_values:
                text = str(e.properties.get("text") or e.properties.get("value") or "")
                if _normalize_value_text(text) in exclude_values:
                    should_exclude = True
            if not should_exclude and learned_rules:
                text = str(e.properties.get("text") or e.properties.get("value") or "")
                if any(rule.matches(text) for rule in learned_rules):
                    should_exclude = True
            if not should_exclude:
                result.append(e)
    return result


def extract_note_entities(
    entities: list,
    global_bounds: tuple | None,
    regions: dict,
    exclude_values: set | None = None,
) -> list:
    """The notes pool, chosen by what each text IS rather than by which box it fell in.

    Same noise filters as `extract_zone_entities` — margin, structured-value suppression,
    scoped learned dismissals — but membership comes from `notes_classifier.classify_notes`.

    This exists because the notes box is not a usable feature. It has no drawn boundary on
    these sheets (best-IoU ceiling 0.08), it is grown from text anchors, and the two sides of
    a comparison are detected independently — so on `M7452A0N01-rev-mut005` the same four
    notes rows at identical coordinates land inside the reference's box and outside the
    revision's, and report as seven false `REMOVED`s. A content predicate is side-independent
    by construction, which is the entire point. See notes_classifier's module docstring.
    """
    learned_rules = _learned_rules_for("notes_section")

    candidates: list = []
    items: list[tuple[str, float, float]] = []
    for e in entities:
        if getattr(e, "entity_type", "") not in ("text", "mtext", "attrib"):
            continue
        if is_in_margin(e, global_bounds):
            continue
        geom = getattr(e, "geometry", {}) or {}
        insert = geom.get("insert") or []
        if len(insert) < 2:
            continue
        text = str(e.properties.get("text") or e.properties.get("value") or "")
        if not text.strip():
            continue
        candidates.append(e)
        items.append((text, float(insert[0]), float(insert[1])))

    span = 0.0
    if global_bounds and len(global_bounds) == 4:
        span = max(global_bounds[2] - global_bounds[0], global_bounds[3] - global_bounds[1])

    result = []
    for idx in classify_notes(items, regions, sheet_span=span):
        e = candidates[idx]
        text = items[idx][0]
        if exclude_values and _normalize_value_text(text) in exclude_values:
            continue
        if learned_rules and any(rule.matches(text) for rule in learned_rules):
            continue
        result.append(e)
    return result


def safe_filter(entities: list, bom_bbox, title_bbox, tol_bbox, notes_bbox, iso_bbox, title_ul_bbox, global_bounds, exclude_values: set | None = None, shim_bbox=None, polygons: dict | None = None) -> list:
    """Apply the drawing_views noise filters to an already views-scoped entity set.

    `entities` here is the views-scoped pool (scope_entities_to_views), NOT the whole sheet.
    This strips margin/frame labels, sibling-zone furniture that overlaps the views box,
    title/BOM/tolerance layers, revision-table headers, learned dismissals, and values
    already captured by structured extraction. The sibling-bbox exclusions are now largely
    defensive (scope_entities_to_views already dropped centroid-in-sibling entities), kept
    because they also catch entities that straddle a boundary. Never uses a bbox that covers
    too much of the drawing for exclusion.

    `polygons` maps a zone key to its hand-drawn outline for zones reshaped in the editor
    (`regions[_zone_polygons]`). Exclusion honours the outline rather than the bounding box,
    so content sitting in a notch the user cut out of a sibling zone stays in the pool. On
    the bounding box it would be dropped here and picked up by nothing."""
    poly = polygons or {}
    use_bom      = bom_bbox      and not _bbox_covers_too_much(bom_bbox,      global_bounds)
    use_title    = title_bbox    and not _bbox_covers_too_much(title_bbox,    global_bounds)
    use_tol      = tol_bbox      and not _bbox_covers_too_much(tol_bbox,      global_bounds)
    use_notes    = notes_bbox    and not _bbox_covers_too_much(notes_bbox,    global_bounds)
    use_iso      = iso_bbox      and not _bbox_covers_too_much(iso_bbox,      global_bounds)
    use_title_ul = title_ul_bbox and not _bbox_covers_too_much(title_ul_bbox, global_bounds)
    # The shim table (シム表) is a SAFE zone like tolerance: exclude its reference-data rows
    # from the drawing_views pool so they are not diffed as drawing dimensions. It is not
    # compared as its own category -- the rows never leave this filter.
    use_shim     = shim_bbox     and not _bbox_covers_too_much(shim_bbox,     global_bounds)

    result = [
        e for e in entities
        if not (
            (use_bom      and is_in_bbox(e, bom_bbox,      poly.get("bom")))              or
            (use_title    and is_in_bbox(e, title_bbox,    poly.get("title")))            or
            (use_tol      and is_in_bbox(e, tol_bbox,      poly.get("tolerance")))        or
            (use_notes    and is_in_bbox(e, notes_bbox,    poly.get("notes")))            or
            (use_iso      and is_in_bbox(e, iso_bbox,      poly.get("iso")))              or
            (use_title_ul and is_in_bbox(e, title_ul_bbox, poly.get("title_upper_left"))) or
            (use_shim     and is_in_bbox(e, shim_bbox,     poly.get("shim")))             or
            is_in_margin(e, global_bounds)
        )
    ]

    # Additional safety net: explicitly exclude entities based on layer keywords to guarantee 
    # they are not double-processed by diff_views even if their coordinates slip outside the bbox.
    def _is_revision_table_header(e) -> bool:
        """Amendment-table column headers, wherever the table sits on the sheet."""
        text = e.properties.get("text") or e.properties.get("value") or ""
        return _normalize_value_text(text) in REVISION_TABLE_HEADERS

    result = [
        e for e in result
        if not _is_bom_layer(getattr(e, "layer", "") or "")
        and not _is_title_layer(getattr(e, "layer", "") or "")
        and not _is_tolerance_layer_or_text(e)
        and not _is_revision_table_header(e)
    ]

    # Pillar 3 -> Pillar 1: patterns a human has dismissed >= 3 times, written to the vault
    # by AutoDocEngine. Until now nothing read those notes back, so the active-learning
    # flywheel did not close and a repeatedly-dismissed callout kept being reported.
    #
    # Matched EXACTLY, never as a substring. These are precise `entity_text` values and
    # several are short ("1", "2A0"); substring matching would silently suppress unrelated
    # content, and nothing in this system measures its own false-negative rate.
    #
    # SCOPED to drawing_views. This filter builds the drawing_views pool, so only patterns
    # a human dismissed *in* drawing_views are evidence here. Previously every category's
    # patterns were flattened into one set and applied here, which meant a `title_block`
    # dismissal silently suppressed drawing geometry — a suppression nothing measures.
    # The notes and isometric pools get the same treatment at their own extraction sites.
    try:
        from ...knowledge.vault_sync import VaultSyncManager
        learned_rules = VaultSyncManager.get_instance().get_learned_dismissal_rules(
            category="drawing_views"
        )
    except Exception as err:
        logger.warning(f"Learned dismissal rules unavailable, continuing without: {err}")
        learned_rules = []

    if learned_rules:
        before_learned = len(result)
        result = [
            e for e in result
            if not any(
                rule.matches(e.properties.get("text") or e.properties.get("value") or "")
                for rule in learned_rules
            )
        ]
        if len(result) != before_learned:
            # Logged, not silent: this is the one filter driven by stored human decisions
            # rather than by the drawing, so it must be visible when it fires.
            logger.info(
                f"Learned dismissal rules excluded {before_learned - len(result)} "
                f"entit(ies) from {len(learned_rules)} human-confirmed drawing_views "
                f"pattern(s)."
            )

    # Third safety net: exclude entities whose text exactly matches a value already
    # captured by structured title-block/BOM extraction — see
    # _collect_structured_text_values above for why this is needed in addition to
    # the bbox- and layer-based exclusions.
    if exclude_values:
        result = [
            e for e in result
            if _normalize_value_text(e.properties.get("text") or e.properties.get("value") or "") not in exclude_values
        ]

    # Safety valve: if the noise filters wiped everything out, fall back to margin-only
    # exclusion. `entities` is the views-scoped pool, so this stays inside the views box —
    # it can't reintroduce out-of-box content. An empty views pool (no views box) has
    # len(entities) == 0, so the valve never fires and drawing_views stays empty as intended.
    if len(result) == 0 and len(entities) > 0:
        logger.warning("Entity filter produced empty set — falling back to margin-only exclusion within views scope.")
        result = [e for e in entities if not is_in_margin(e, global_bounds)]

    return result




async def generate_deterministic_candidates(
    ref_drawing: DrawingDocument,
    rev_drawing: DrawingDocument,
    ref_entities: list,
    rev_entities: list,
    refresh_ocr: bool = False,
    progress_callback=None,
    zone_templates: tuple[dict | None, dict | None] | None = None,
) -> tuple[list[ComparisonCandidate], dict, list[str]]:
    """
    Generator A (deterministic): runs SpatialDiffer + BOMAnalyzer end to end and returns
    candidate findings instead of a final PhysicalComparisonResponse. Extracted from
    perform_drawing_comparison() (docs/hybrid-comparison-engine-implementation-plan.md,
    Phase 2) so the same deterministic pass can feed both the `rag` method (via the thin
    wrapper below, output unchanged) and the `hybrid` method's reconciliation step. No
    diffing/extraction logic changed by this move — only where the result goes.

    Returns:
        candidates: individual finding-level results (the old `clean_markings`), each
            tagged origin="deterministic" and resolution_method reflecting whether
            coordinate_resolver found an exact entity-handle match.
        category_rollups: dict keyed by the 6 CategoryComparison categories, each a dict
            with status/difference_summary/reference_content/revision_content/
            engineering_discrepancy_details — everything the response needs besides
            canvas_markings itself. (Still carries a vestigial "canvas_markings" key,
            same as the original `parsed` dict did — harmless, callers only read the
            6 category keys by name.)
        zone_detection_warnings: unchanged from today's diagnostics.

    progress_callback, when supplied, is awaited at each coarse stage boundary so the SSE
    endpoint can stream real progress. It stays optional: the eval runner calls this directly
    and passes None, and the removed `hybrid` orchestrator did too (ADR-006).
    """
    if progress_callback:
        await progress_callback("extracting", 20, "Extracting drawing entities & BOM/title data")

    # Resolve titles and revisions
    ref_rev, rev_rev, ref_title, rev_title = resolve_revisions(
        ref_entities,
        rev_entities,
        ref_drawing.file_hash,
        rev_drawing.file_hash,
        ref_drawing.file_name,
        rev_drawing.file_name
    )

    ref_groups = extract_semantic_text_groups(ref_entities, prefix="REF")
    rev_groups = extract_semantic_text_groups(rev_entities, prefix="REV")
    
    ref_geom = ref_groups["geometry_annotations"]
    rev_geom = rev_groups["geometry_annotations"]
    
    ref_notes = ref_groups["notes_zone_text"]
    rev_notes = rev_groups["notes_zone_text"]
    
    ref_bom = ref_groups["bom_zone_text"]
    rev_bom = rev_groups["bom_zone_text"]
    
    ref_title_data = f"Title: {ref_title} | Rev: {ref_rev} | {ref_groups['title_block_data']}"
    rev_title_data = f"Title: {rev_title} | Rev: {rev_rev} | {rev_groups['title_block_data']}"

    # Bypassing the LLM for Phase 1 to achieve deterministic 100% mathematical accuracy.
    from .spatial_differ import SpatialDiffer

    # Compute bounding boxes for visual overlap warnings and spatial constraints
    from ..bom.table_extractor import extract_dynamic_regions_async, summarize_zone_detection_confidence
    # render_bounds is what hand-aligned zone fractions are stored relative to, and the
    # sheet signature is derived from it. `layout_signature` was read here previously but is
    # never written anywhere, so it was always None.
    ref_bounds = (ref_drawing.metadata or {}).get("render_bounds")
    rev_bounds = (rev_drawing.metadata or {}).get("render_bounds")

    # `zone_templates` is the offline eval seam and is None everywhere in the app, which
    # leaves the Mongo lookup below exactly as it was. An offline run supplies the fractions
    # it captured at export so the zone boxes are a property of the corpus rather than of
    # whichever machine ran it. See extract_dynamic_regions_async for why None and {} differ.
    ref_template, rev_template = zone_templates or (None, None)

    ref_regions = await extract_dynamic_regions_async(
        ref_entities, render_bounds=ref_bounds, zone_template=ref_template
    )
    rev_regions = await extract_dynamic_regions_async(
        rev_entities, render_bounds=rev_bounds, zone_template=rev_template
    )
    zone_detection_warnings = summarize_zone_detection_confidence(ref_regions, rev_regions)
    if zone_detection_warnings:
        logger.info(f"Zone detection confidence warnings: {zone_detection_warnings}")

    ref_bom_bbox_raw = ref_regions.get("bom")
    rev_bom_bbox_raw = rev_regions.get("bom")
    ref_title_bbox_raw = ref_regions.get("title")
    rev_title_bbox_raw = rev_regions.get("title")
    ref_notes_bbox_raw = ref_regions.get("notes")
    rev_notes_bbox_raw = rev_regions.get("notes")
    ref_iso_bbox_raw = ref_regions.get("iso")
    rev_iso_bbox_raw = rev_regions.get("iso")
    ref_views_bbox_raw = ref_regions.get("views")
    rev_views_bbox_raw = rev_regions.get("views")
    ref_title_ul_bbox_raw = ref_regions.get("title_upper_left")
    rev_title_ul_bbox_raw = rev_regions.get("title_upper_left")
    ref_tolerance_bbox_raw = ref_regions.get("tolerance")
    rev_tolerance_bbox_raw = rev_regions.get("tolerance")
    # `shim` is optional (only present when the シム表 anchor fires) -- .get() returns None on
    # sheets without a shim table, which flows through as "no shim zone" everywhere below.
    ref_shim_bbox_raw = ref_regions.get("shim")
    rev_shim_bbox_raw = rev_regions.get("shim")

    # Validate regions via BoundingBox2D DTOs
    ref_bom_bbox = BoundingBox2D.from_tuple(ref_bom_bbox_raw).to_tuple() if ref_bom_bbox_raw else None
    rev_bom_bbox = BoundingBox2D.from_tuple(rev_bom_bbox_raw).to_tuple() if rev_bom_bbox_raw else None
    ref_title_bbox = BoundingBox2D.from_tuple(ref_title_bbox_raw).to_tuple() if ref_title_bbox_raw else None
    rev_title_bbox = BoundingBox2D.from_tuple(rev_title_bbox_raw).to_tuple() if rev_title_bbox_raw else None
    ref_notes_bbox = BoundingBox2D.from_tuple(ref_notes_bbox_raw).to_tuple() if ref_notes_bbox_raw else None
    rev_notes_bbox = BoundingBox2D.from_tuple(rev_notes_bbox_raw).to_tuple() if rev_notes_bbox_raw else None
    ref_iso_bbox = BoundingBox2D.from_tuple(ref_iso_bbox_raw).to_tuple() if ref_iso_bbox_raw else None
    rev_iso_bbox = BoundingBox2D.from_tuple(rev_iso_bbox_raw).to_tuple() if rev_iso_bbox_raw else None
    ref_views_bbox = BoundingBox2D.from_tuple(ref_views_bbox_raw).to_tuple() if ref_views_bbox_raw else None
    rev_views_bbox = BoundingBox2D.from_tuple(rev_views_bbox_raw).to_tuple() if rev_views_bbox_raw else None
    ref_title_ul_bbox = BoundingBox2D.from_tuple(ref_title_ul_bbox_raw).to_tuple() if ref_title_ul_bbox_raw else None
    rev_title_ul_bbox = BoundingBox2D.from_tuple(rev_title_ul_bbox_raw).to_tuple() if rev_title_ul_bbox_raw else None

    logger.info(f"Spatial regions - ref BOM bbox: {ref_bom_bbox} | rev BOM bbox: {rev_bom_bbox} | rev Title bbox: {rev_title_bbox}")
    
    if rev_bom_bbox and rev_title_bbox:
        if rev_bom_bbox[0] < rev_title_bbox[2] and rev_bom_bbox[2] > rev_title_bbox[0] and \
           rev_bom_bbox[1] < rev_title_bbox[3] and rev_bom_bbox[3] > rev_title_bbox[1]:
            logger.warning(f"Spatial region overlap detected! BOM: {rev_bom_bbox}, Title: {rev_title_bbox}")

    # Reconcile BOM layout and extract tabular rows
    ref_bounds = ref_drawing.metadata.get("render_bounds") if ref_drawing and ref_drawing.metadata else None
    rev_bounds = rev_drawing.metadata.get("render_bounds") if rev_drawing and rev_drawing.metadata else None
    
    ref_bom_input = [e for e in ref_entities if not is_in_bbox(e, ref_tolerance_bbox_raw)]
    rev_bom_input = [e for e in rev_entities if not is_in_bbox(e, rev_tolerance_bbox_raw)]
    
    ref_bom_rows, ref_is_assembly = BOMAnalyzer.extract_bom_table(ref_bom_input, render_bounds=ref_bounds, bom_bbox=ref_bom_bbox_raw)
    rev_bom_rows, rev_is_assembly = BOMAnalyzer.extract_bom_table(rev_bom_input, render_bounds=rev_bounds, bom_bbox=rev_bom_bbox_raw)
    is_assembly_drawing = ref_is_assembly or rev_is_assembly
    bom_comparison_table = BOMAnalyzer.build_bom_table(ref_bom_rows, rev_bom_rows, is_assembly_drawing)
    logger.info(f"BOM extraction complete - is_assembly={is_assembly_drawing}, ref_bom_rows={ref_bom_rows}, rev_bom_rows={rev_bom_rows}")

    # Retrieve API key
    api_key = os.environ.get("GEMINI_API_KEY") or getattr(settings, "GEMINI_API_KEY", None)
    openai_key = os.environ.get("OPENAI_API_KEY") or getattr(settings, "OPENAI_API_KEY", None)
    if not api_key and not openai_key:
        logger.warning("Neither GEMINI_API_KEY nor OPENAI_API_KEY environment variable is defined.")
        raise ValueError("Neither GEMINI_API_KEY nor OPENAI_API_KEY is configured.")

    # Reconcile title block coordinates and dimensions
    ref_all_text_list = [e.properties.get("text", "") for e in ref_entities if getattr(e, "entity_type", "") == "text"]
    rev_all_text_list = [e.properties.get("text", "") for e in rev_entities if getattr(e, "entity_type", "") == "text"]
    
    if progress_callback:
        await progress_callback("title_block_ocr", 45, "Reading title block")

    # Load cached Title Block OCR results. When refresh_ocr is set the cache is skipped, so the
    # crop is re-sent to Gemini below and the fresh reading overwrites the stale one via
    # set_cached_ocr. This is separate from the comparison cache (force_refresh) because OCR is
    # a paid per-drawing Gemini call and must not fire on every ordinary Re-test.
    if refresh_ocr:
        ref_ocr = rev_ocr = None
    else:
        ref_ocr = ComparisonCacheManager.get_cached_ocr(str(ref_drawing.id), ref_drawing.file_hash)
        rev_ocr = ComparisonCacheManager.get_cached_ocr(str(rev_drawing.id), rev_drawing.file_hash)

    missing_crops = {}
    from ...rendering.image_cropper import crop_title_block_image
    
    if not ref_ocr:
        ref_crop = crop_title_block_image(str(ref_drawing.id), ref_drawing.metadata, ref_entities)
        if ref_crop is not None:
            missing_crops["reference"] = ref_crop
            
    if not rev_ocr:
        rev_crop = crop_title_block_image(str(rev_drawing.id), rev_drawing.metadata, rev_entities)
        if rev_crop is not None:
            missing_crops["revision"] = rev_crop

    if missing_crops:
        from .gemini_client import execute_title_block_ocr
        try:
            ocr_res = await asyncio.to_thread(execute_title_block_ocr, api_key, missing_crops)
            
            # Cache the results independently for each drawing using its specific keys
            if "reference" in ocr_res and ocr_res["reference"]:
                ref_ocr = ocr_res["reference"]
                ComparisonCacheManager.set_cached_ocr(
                    str(ref_drawing.id), ref_drawing.file_hash, ref_ocr
                )
                
            if "revision" in ocr_res and ocr_res["revision"]:
                rev_ocr = ocr_res["revision"]
                ComparisonCacheManager.set_cached_ocr(
                    str(rev_drawing.id), rev_drawing.file_hash, rev_ocr
                )
        except Exception as ocr_err:
            logger.warning(f"Batched visual Title Block OCR failed, falling back to spatial heuristics: {ocr_err}")

    # Exclude the tolerance table and the upper-left table from title extraction — each has its
    # own extractor — but never an entity that also sits in the title block, since an over-wide
    # box would otherwise blank the whole title block. See keep_for_title_extraction.
    ref_title_input = [e for e in ref_entities if keep_for_title_extraction(e, ref_tolerance_bbox_raw, ref_title_bbox, ref_title_ul_bbox_raw)]
    rev_title_input = [e for e in rev_entities if keep_for_title_extraction(e, rev_tolerance_bbox_raw, rev_title_bbox, rev_title_ul_bbox_raw)]

    ref_title_fields = BOMAnalyzer.extract_title_block(ref_title_input, ref_all_text_list, ocr_results=ref_ocr)
    rev_title_fields = BOMAnalyzer.extract_title_block(rev_title_input, rev_all_text_list, ocr_results=rev_ocr)

    # Run comparative overlays checks
    title_block_table = build_title_block_table(ref_title_fields, rev_title_fields)

    # Values already captured by structured title-block/BOM extraction shouldn't ALSO
    # be picked up by the generic drawing_views/notes_section/isometric_view passes
    # below — a title-block or BOM data value (e.g. a "Previous Dwg. No." stamp) can
    # sit outside the detected zone bbox (zone detection is a percentage/content-anchor
    # heuristic — see zone_detection_warnings above) and would otherwise be
    # double-represented under the wrong category: once correctly, by
    # inject_title_block_markings/inject_bom_markings, and once incorrectly, as a
    # generic finding with whatever category SpatialDiffer happens to tag it.
    # ...but this net is keyed on TEXT ALONE and applied sheet-wide, so a value short enough
    # to recur innocently suppresses every occurrence of that string in every zone, on BOTH
    # sides -- which makes the suppressed content's deletion unreportable rather than merely
    # unreported. Measured on the corpus: a BOM row numbered `1` deleted a standalone `１` from
    # the notes zone, and renumbering that row to `999` made the missing REMOVED finding appear.
    # A one-character value carries no evidence that the entity IS the structured source.
    #
    # This is the same reasoning `vault_sync.get_learned_dismissals` already applies to learned
    # patterns -- "several are short (`1`, `2A0`); substring matching would silently suppress
    # unrelated content, which is the one failure mode this system cannot detect". The floor is
    # length-based rather than spatial because the whole point of this net is to catch values
    # that sit OUTSIDE their zone's bbox, so a spatial test would defeat it.
    #
    # See docs/vault/06 - .../Gotcha - A Short Structured Value Suppresses Its Own Zone.
    # `_normalize_value_text` / `_collect_structured_text_values` are module-level; the
    # suppression floor they apply is read from `MIN_STRUCTURED_VALUE_LENGTH` on each call.

    ref_title_ul_pairs, ref_title_ul_claimed_ids = extract_title_ul_kv(
        ref_entities, ref_title_ul_bbox_raw
    )
    rev_title_ul_pairs, rev_title_ul_claimed_ids = extract_title_ul_kv(
        rev_entities, rev_title_ul_bbox_raw
    )

    # ------------------------------------------------------------------
    # Claim only what can actually be compared.
    #
    # A value the extractor pulled out of the upper-left box with NOTHING on the other side to
    # compare it against is not a comparison result -- it is a value this extractor should not
    # have taken. Reporting it as REMOVED/ADDED asserts a change nobody measured, and worse,
    # `_collect_structured_text_values` then suppresses that text sheet-wide, so the zone it
    # really belongs to cannot report it either. That is how one over-reaching zone box turned
    # `4 ロール：12 (2x6台)` into both a false CHANGED against `16組` and a false ADDED against
    # a line the reference plainly has.
    #
    # So an unpairable value is RELEASED: dropped from this extractor's output and from the
    # suppression net, leaving it to whichever zone's pass covers it.
    #
    # ⚠ Releasing is only safe when something else can catch it, and here it usually cannot:
    # `title_upper_left` is in `VIEWS_EXCLUDED_ZONES`, so content inside that box is subtracted
    # from the `views` pool, and there is no other pass scoped to the UL box. A release with no
    # catcher is a SILENT FALSE NEGATIVE -- the one failure mode this system cannot detect --
    # which is why the check below is per-value and geometric: release only when another zone's
    # shape actually covers the value's own coordinates. Zones overlap, and on M745227N01 the
    # released roll-count line lands inside `notes` on the reference, which is exactly how it
    # came back as a real CHANGED against its revision counterpart.
    #
    # With no catcher, the one-sided report stands. Reporting a value nobody could pair beats
    # deleting it: a wrong finding is visible, a missing one is not.
    # See docs/vault/06 - .../Gotcha - The Lowest Row Is Not the Values Row.
    # ------------------------------------------------------------------
    _ul_comparable, _ul_released = partition_ul_pairs(
        match_title_ul_pairs(ref_title_ul_pairs, rev_title_ul_pairs),
        corroborates=lambda value, missing_side: _ul_corroborates(
            value, missing_side,
            ref_entities, rev_entities,
            ref_title_ul_bbox_raw, rev_title_ul_bbox_raw,
        ),
        covered_by_another_zone=lambda coords, side: _other_zone_covers(
            coords, ref_regions if side == "ref" else rev_regions
        ),
    )

    if _ul_released:
        logger.info(
            f"Title-upper-left: released {len(_ul_released)} unpairable value(s) to the zone "
            f"that covers them rather than reporting a one-sided change: "
            f"{[str((p or {}).get('value'))[:24] for p in _ul_released]}"
        )
    _released_keys = {id(p) for p in _ul_released}
    ref_title_ul_claimed = [p for p in ref_title_ul_pairs if id(p) not in _released_keys]
    rev_title_ul_claimed = [p for p in rev_title_ul_pairs if id(p) not in _released_keys]

    ref_structured_values = _collect_structured_text_values(ref_title_fields, ref_bom_rows, ref_title_ul_claimed)
    rev_structured_values = _collect_structured_text_values(rev_title_fields, rev_bom_rows, rev_title_ul_claimed)

    # Bounding boxes and spatial differ imports were hoisted earlier

    from ..bom.spatial_utils import compute_drawing_bounds
    ref_global_bounds = compute_drawing_bounds(ref_entities)
    rev_global_bounds = compute_drawing_bounds(rev_entities)

    # Notes are claimed per ENTITY, not per box. The zone that used to scope this pool has no
    # drawn boundary on these sheets and is grown from text anchors, so it moves when the text
    # moves — including when the change under test is itself an added note. The ownership veto
    # inside the classifier subsumes the `exclude_bboxes` list this call used to pass, and does
    # it in precedence order rather than as an ad-hoc trio. See notes_classifier.py.
    ref_notes_entities = extract_note_entities(
        ref_entities, ref_global_bounds, ref_regions,
        exclude_values=ref_structured_values,
    )
    rev_notes_entities = extract_note_entities(
        rev_entities, rev_global_bounds, rev_regions,
        exclude_values=rev_structured_values,
    )

    # Extract Isometric view entities specifically for isometric_view diffing
    ref_iso_entities = extract_zone_entities(
        ref_entities, ref_iso_bbox_raw, ref_global_bounds,
        exclude_bboxes=[ref_tolerance_bbox_raw, ref_title_bbox_raw, ref_bom_bbox_raw],
        exclude_values=ref_structured_values,
        learned_category="isometric_view",
    )
    rev_iso_entities = extract_zone_entities(
        rev_entities, rev_iso_bbox_raw, rev_global_bounds,
        exclude_bboxes=[rev_tolerance_bbox_raw, rev_title_bbox_raw, rev_bom_bbox_raw],
        exclude_values=rev_structured_values,
        learned_category="isometric_view",
    )

    # drawing_views is scoped to the `views` zone box, not the residual of everything-minus-
    # other-zones. Only entities whose centroid sits inside `views` (minus the sibling zones
    # that may fall within a hand-pinned views rectangle) enter the pool; a sheet with no views
    # box contributes nothing here. This makes the pinned/detected views box the definitive
    # comparison boundary. STRICT, no fallback: content outside the box is deliberately not
    # compared. safe_filter below then applies the same noise filters (margin, layer, learned
    # dismissals, structured-value de-dup) to the already-scoped set.
    #
    # The shim table (シム表) is a SAFE zone like tolerance: its bbox is used only to keep its
    # reference-data rows out of the pool (via safe_filter's shim_bbox below). It is deliberately
    # NOT diffed as its own category -- assembly-thickness data does not change meaningfully
    # between revisions, so comparing it is noise.
    from ..bom.zone_detector import scope_entities_to_views, views_exclusions
    from ..bom.zone_geometry import polygon_for, zone_polygons

    # Hand-drawn outlines for zones the user reshaped in the editor. Empty for every sheet
    # whose template carries plain rectangles, which is the default and the common case.
    ref_polygons = zone_polygons(ref_regions)
    rev_polygons = zone_polygons(rev_regions)

    # `notes` and `title_upper_left` are omitted from the bbox subtraction and removed by
    # IDENTITY instead — each subtracts what it actually claimed, not everything its box
    # happens to cover.
    #
    # For `notes` that is because the pool is chosen per entity now, so the box is no longer the
    # authority on what a note is; subtracting both would double-count in one direction and leak
    # in the other. For `title_upper_left` it is because the box and the extractor disagree: the
    # extractor cuts the bands below the values row, and anything in that gap used to be removed
    # from `views` by the box while being claimed by no comparison at all. That is a silent false
    # negative, and it is the one failure mode this system cannot detect.
    #
    # **The rule, for any zone: a zone may only take content out of the shared pool if it is
    # going to compare it.** Everything else falls through to `views`, which is the drawing area
    # and the correct home for content no specialised pass wanted.
    _ref_claimed = {id(e) for e in ref_notes_entities} | ref_title_ul_claimed_ids
    _rev_claimed = {id(e) for e in rev_notes_entities} | rev_title_ul_claimed_ids
    _omit = ("notes", "title_upper_left")
    ref_views_pool = [
        e for e in scope_entities_to_views(
            ref_entities, ref_views_bbox_raw, views_exclusions(ref_regions, omit=_omit),
            polygon_for(ref_regions, "views"),
        )
        if id(e) not in _ref_claimed
    ]
    rev_views_pool = [
        e for e in scope_entities_to_views(
            rev_entities, rev_views_bbox_raw, views_exclusions(rev_regions, omit=_omit),
            polygon_for(rev_regions, "views"),
        )
        if id(e) not in _rev_claimed
    ]

    # `notes_bbox` and `title_ul_bbox` are None here for the same reason they are omitted above:
    # both subtract by identity now, and re-applying the boxes would undo it — this defensive
    # pass would drop drawing geometry for merely sitting inside a box whose owner never claimed
    # it, which is exactly the silent false negative being fixed.
    filtered_ref_entities = safe_filter(
        ref_views_pool,
        ref_bom_bbox_raw, ref_title_bbox_raw, ref_tolerance_bbox_raw,
        None, ref_iso_bbox_raw, None,
        ref_global_bounds,
        exclude_values=ref_structured_values,
        shim_bbox=ref_shim_bbox_raw,
        polygons=ref_polygons,
    )
    filtered_rev_entities = safe_filter(
        rev_views_pool,
        rev_bom_bbox_raw, rev_title_bbox_raw, rev_tolerance_bbox_raw,
        None, rev_iso_bbox_raw, None,
        rev_global_bounds,
        exclude_values=rev_structured_values,
        shim_bbox=rev_shim_bbox_raw,
        polygons=rev_polygons,
    )

    logger.info(
        f"Filtered entity counts for Spatial Differ — "
        f"ref: {len(ref_entities)} → views-scoped {len(ref_views_pool)} → {len(filtered_ref_entities)} (notes={len(ref_notes_entities)}, iso={len(ref_iso_entities)}), "
        f"rev: {len(rev_entities)} → views-scoped {len(rev_views_pool)} → {len(filtered_rev_entities)} (notes={len(rev_notes_entities)}, iso={len(rev_iso_entities)})"
    )
    if not ref_views_bbox_raw or not rev_views_bbox_raw:
        logger.warning(
            "No `views` zone box on %s — drawing_views is empty for this pair (strict scoping, "
            "no residual fallback). Pin or detect a views box to compare drawing geometry.",
            "reference" if not ref_views_bbox_raw else "revision",
        )

    if progress_callback:
        await progress_callback("spatial_diff", 70, "Running deterministic spatial diff")

    # Perform comparison/diffing on notes, iso views and drawing views.
    #
    # render_bounds is passed so matching runs in each drawing's own normalized frame. The
    # two sides are NOT necessarily in the same coordinate space: a DXF without a paper-space
    # viewport stays in model units while one with a viewport is projected to paper units.
    # Measured on the M7452A0N01 pair that is a 2.500x scale difference, which a
    # translation-only pre-alignment cannot absorb -- it emitted unchanged title-block text as
    # REMOVED on one side and ADDED on the other. See spatial_differ's module header.
    notes_markings = SpatialDiffer.diff_views(
        ref_notes_entities, rev_notes_entities, category="notes_section",
        ref_bounds=ref_bounds, rev_bounds=rev_bounds,
    )
    iso_markings = SpatialDiffer.diff_views(
        ref_iso_entities, rev_iso_entities, category="isometric_view",
        ref_bounds=ref_bounds, rev_bounds=rev_bounds,
    )
    clean_markings = SpatialDiffer.diff_views(
        filtered_ref_entities, filtered_rev_entities, category="drawing_views",
        ref_bounds=ref_bounds, rev_bounds=rev_bounds,
    )

    # Sub-item taxonomy tagging (docs/checklist-taxonomy-grouping-implementation-plan.md,
    # Phase 2) — heuristic, text-only classification; see feature_classifier.py for what
    # each rule can and can't confidently detect. Runs before the .extend() below so
    # each classifier only ever sees findings from its own category.
    for m in clean_markings:
        m["feature"] = classify_drawing_view_feature(m.get("text_content", ""), m.get("details", ""))
    # Second pass — needs the whole drawing, not one finding at a time. See refine_view_labels.
    section_callout_labels = refine_view_labels(clean_markings)
    if DROP_SECTION_CALLOUT_LABELS and section_callout_labels:
        dropped = {id(m) for m in section_callout_labels}
        clean_markings = [m for m in clean_markings if id(m) not in dropped]
        logger.info(
            f"Suppressed {len(dropped)} section-callout label(s) from drawing_views "
            f"(DROP_SECTION_CALLOUT_LABELS) — the section identifier itself is not compared."
        )
    for m in notes_markings:
        m["feature"] = classify_notes_feature(m.get("text_content", ""), m.get("details", ""))
    for m in iso_markings:
        m["feature"] = classify_iso_feature(m.get("text_content", ""), m.get("details", ""))

    # Bare geometry (lines, circles, arcs, ellipses, splines) is deliberately NOT compared.
    # A `diff_geometry` pass existed here and was removed: clustering unmatched shapes produced
    # findings like "Geometry: 10 line" that name a count and a primitive type but no engineering
    # content, so a checker cannot act on them and they crowd out the text findings that are the
    # checklist's actual substance. The known cost of removing it is that a zone present on only
    # one sheet and carrying no text -- a wholly-added isometric view was the motivating case --
    # reports nothing at all, because `diff_views` also returns [] the moment either pool is
    # empty. That was judged the better trade: silence beats unactionable noise. If this is
    # revisited, the finding needs to say what CHANGED, not how many primitives differ.
    clean_markings.extend(notes_markings)
    clean_markings.extend(iso_markings)

    # Collapse content that was diffed against two different pools and therefore reported
    # twice -- once as REMOVED from where it used to sit, once as ADDED where it now sits.
    # This has to run after the three lists are combined, because the two halves of such a
    # pair are by definition in different lists. It also runs after feature classification so
    # the surviving marking keeps the label its category earned.
    # See marking_reconciler for why unambiguous pairs only.
    before_count = len(clean_markings)
    clean_markings = reconcile_relocated_markings(
        clean_markings, ref_bounds=ref_bounds, rev_bounds=rev_bounds
    )
    if len(clean_markings) != before_count:
        logger.info(
            f"Marking reconciliation: {before_count} -> {len(clean_markings)} findings "
            f"({(before_count - len(clean_markings))} relocated REMOVED/ADDED pairs merged)."
        )

    # Line attributes — which line types and thicknesses the views are drawn with.
    #
    # Runs on `ref_views_pool`/`rev_views_pool` rather than `filtered_*_entities`: safe_filter's
    # remaining passes (structured-value de-dup, learned dismissals) are keyed on TEXT, and a
    # stroke has none, so applying them here would filter nothing while implying it had.
    #
    # The full entity lists are passed alongside for their `layer` records only. Those carry no
    # geometry, so `scope_entities_to_views` drops them from both pools, and without them every
    # BYLAYER stroke would resolve against an empty layer table.
    #
    # Placed after reconciliation because these markings carry no coordinates and have nothing
    # to reconcile — running them through it would only ask a proximity merge to reason about
    # findings that have no position.
    line_attribute_markings = diff_line_attributes(
        ref_views_pool, rev_views_pool, ref_entities, rev_entities,
    )
    clean_markings.extend(line_attribute_markings)
    logger.info(
        f"Line attributes: {len(line_attribute_markings)} profile row(s) — "
        f"{len([m for m in line_attribute_markings if m.get('status') == 'MATCHED'])} on both sides, "
        f"{len([m for m in line_attribute_markings if m.get('status') == 'ADDED'])} revision-only, "
        f"{len([m for m in line_attribute_markings if m.get('status') == 'REMOVED'])} reference-only."
    )

    # Amendment/revision-history table -> title_block, not drawing_views.
    #
    # The table's column headers are already filtered out of the drawing_views pool by
    # `safe_filter` (REVISION_TABLE_HEADERS), but its *values* and its A/B/C/D row-letter
    # column are legitimate text that survives filtering and, when the table sits outside
    # the detected `title` box (bottom-left on the reference in the measured pair), lands in
    # drawing_views. This is category attribution, not detection: the finding is real, it is
    # just under the wrong heading. Detected zones don't reach it because the table has no
    # consistent quadrant across the two sheets -- see _amendment_table_bboxes.
    #
    # Reclassify, never drop. `raw_x`/`raw_y` on each marking are CAD units (spatial_differ
    # line 200), the same basis as these bboxes: rev-side position for ADDED/CHANGED/MATCHED,
    # ref-side for REMOVED.
    ref_amend_bboxes = amendment_table_bboxes(ref_entities, ref_global_bounds)
    rev_amend_bboxes = amendment_table_bboxes(rev_entities, rev_global_bounds)

    if ref_amend_bboxes or rev_amend_bboxes:
        reclassified = 0
        for m in clean_markings:
            if m.get("category") != "drawing_views":
                continue
            if _pos_in_bboxes(m.get("coordinates"), rev_amend_bboxes) or \
               _pos_in_bboxes(m.get("ref_coordinates"), ref_amend_bboxes):
                m["category"] = "title_block"
                reclassified += 1
        if reclassified:
            logger.info(
                f"Amendment-table reclassification: {reclassified} finding(s) "
                f"drawing_views -> title_block."
            )

    # Structured key-value extraction for Title Upper Left (top-left metadata)
    # (ref_title_ul_pairs and rev_title_ul_pairs were extracted earlier above)

    # Match ref↔rev UL fields by shared header token (module-level match_title_ul_pairs),
    # not exact combined key, which double-reported identical values whenever the two drawings
    # banded the stacked headers differently by coordinate scale.
    # Matched and classified earlier, next to the extraction, because the suppression net has
    # to be built from the CLAIMED pairs only — a released value must not silence its own text
    # in the zone that is going to report it.
    _ul_matched = _ul_comparable

    title_ul_table_rows = []
    for ref_p, rev_p in _ul_matched:
        ref_p = ref_p or {}
        rev_p = rev_p or {}
        orig_val = ref_p.get('value', 'NONE') or 'NONE'
        kmti_val = rev_p.get('value', 'NONE') or 'NONE'
        orig_coords = ref_p.get('coords')
        kmti_coords = rev_p.get('coords')
        from ...utils.text import compare_values as _cmp
        status_val = _cmp(orig_val, kmti_val)

        # Bilateral corroboration guard — same principle as the bottom title block (see
        # inject_title_block_markings). On the compact SolidWorks revision the notes block
        # crowds the UL metadata table, so extract_title_ul_kv's "last band = values" heuristic
        # returns NONE for values (45 / 2A1 / 4) that are plainly present. Before emitting a
        # one-sided REMOVED/ADDED, check the other side's UL region for the value; if it is
        # there, the field was mis-extracted, not changed → MATCHED. Region-scoped + match_level
        # 2 so a short numeric value can't corroborate against an unrelated dimension.
        if status_val in ("ADDED", "REMOVED"):
            if orig_val == "NONE" and kmti_val != "NONE":
                _rec = BOMAnalyzer.find_drawing_text_coordinates(
                    ref_entities, kmti_val, category="title_block",
                    region_bbox=ref_title_ul_bbox_raw, match_level=2,
                )
                if _rec and _rec.get("coords"):
                    status_val = "MATCHED"
                    orig_coords = orig_coords or _rec["coords"]
            elif kmti_val == "NONE" and orig_val != "NONE":
                _rec = BOMAnalyzer.find_drawing_text_coordinates(
                    rev_entities, orig_val, category="title_block",
                    region_bbox=rev_title_ul_bbox_raw, match_level=2,
                )
                if _rec and _rec.get("coords"):
                    status_val = "MATCHED"
                    kmti_coords = kmti_coords or _rec["coords"]

        display_key = ref_p.get('key') or rev_p.get('key') or 'Value'
        # Emit ONE marking placed on the value cell coordinates (not the header)
        if kmti_val != 'NONE' or orig_val != 'NONE':
            entry = {
                'text_content': kmti_val if kmti_val != 'NONE' else orig_val,
                'status': status_val,
                'details': f'Title Block (Upper-Left) {display_key}: {orig_val} vs {kmti_val}',
                'category': 'title_block',
                'feature': classify_title_ul_feature(display_key),
                'zone': 'title_upper_left',  # disambiguates from bottom-right title bbox in coordinate resolver
                'original_value': orig_val if status_val == 'CHANGED' else None
            }
            if kmti_coords:
                entry['coordinates'] = kmti_coords
            if orig_coords:
                entry['ref_coordinates'] = orig_coords
            clean_markings.append(entry)
        title_ul_table_rows.append(f'| {display_key} | {orig_val} | {kmti_val} | {status_val} |')

    title_ul_table = '\n'.join([
        '| FIELD | ORIGINAL | REVISION | STATUS |',
        '|-------|----------|----------|--------|',
    ] + title_ul_table_rows) if title_ul_table_rows else ''

    logger.info(
        f"Successfully ran Deterministic Spatial Diffing. Found {len(clean_markings)} total markings: "
        f"drawing_views={len([m for m in clean_markings if m.get('category') == 'drawing_views'])}, "
        f"notes_section={len(notes_markings)}, isometric_view={len(iso_markings)}"
    )

    # Build per-category summaries for the checklist panel
    dv_markings  = [m for m in clean_markings if m.get("category") == "drawing_views"]
    dv_table     = build_marking_table(dv_markings)
    dv_changed   = any(m.get("status") != "MATCHED" for m in dv_markings)
    dv_summary   = (
        f"Found {len([m for m in dv_markings if m.get('status') != 'MATCHED'])} changed / "
        f"{len([m for m in dv_markings if m.get('status') == 'MATCHED'])} matched dimensions and annotations."
        if dv_markings else "No drawing view entities detected in the comparison zone."
    )

    notes_markings_list = [m for m in clean_markings if m.get("category") == "notes_section"]
    notes_table = build_marking_table(notes_markings_list)
    notes_changed = any(m.get("status") != "MATCHED" for m in notes_markings_list)
    notes_summary = (
        f"Found {len([m for m in notes_markings_list if m.get('status') != 'MATCHED'])} changed / "
        f"{len([m for m in notes_markings_list if m.get('status') == 'MATCHED'])} matched notes."
        if notes_markings_list else "No notes detected in the notes zone."
    )

    iso_markings_list = [m for m in clean_markings if m.get("category") == "isometric_view"]
    iso_table = build_marking_table(iso_markings_list)
    iso_changed = any(m.get("status") != "MATCHED" for m in iso_markings_list)
    iso_summary = (
        f"Found {len([m for m in iso_markings_list if m.get('status') != 'MATCHED'])} changed / "
        f"{len([m for m in iso_markings_list if m.get('status') == 'MATCHED'])} matched isometric annotations."
        if iso_markings_list else "No isometric annotations detected."
    )

    parsed = {
        "drawing_views": {
            "status": "CHANGED" if dv_changed else "MATCHED",
            "difference_summary": dv_summary,
            "reference_content": dv_table,
            "revision_content": dv_table,
            "engineering_discrepancy_details": f"{len(dv_markings)} annotation(s) verified by Deterministic Spatial Differ."
        },
        "notes_section": {
            "status": "CHANGED" if notes_changed else "MATCHED",
            "difference_summary": notes_summary,
            "reference_content": notes_table,
            "revision_content": notes_table,
            "engineering_discrepancy_details": f"{len(notes_markings_list)} note(s) verified by Deterministic Spatial Differ."
        },
        "isometric_view": {
            "status": "CHANGED" if iso_changed else "MATCHED",
            "difference_summary": iso_summary,
            "reference_content": iso_table,
            "revision_content": iso_table,
            "engineering_discrepancy_details": f"{len(iso_markings_list)} isometric annotation(s) verified by Deterministic Spatial Differ."
        },
        "other_engineering_references": {
            "status": "MATCHED", "difference_summary": "References verified.",
            "reference_content": "", "revision_content": "", "engineering_discrepancy_details": ""
        },
        "title_block": {
            "status": (
                "CHANGED"
                if any("|" in line and ("MISMATCHED" in line or "CHANGED" in line or "ADDED" in line or "REMOVED" in line)
                       for line in (title_block_table + "\n" + title_ul_table).split("\n"))
                else "MATCHED"
            ),
            "difference_summary": "Title Block & production metadata checked",
            "reference_content": "\n\n".join(filter(None, [title_block_table, title_ul_table])),
            "revision_content":  "\n\n".join(filter(None, [title_block_table, title_ul_table])),
            "engineering_discrepancy_details": "Real Title Block + Upper-Left metadata table used"
        },
        "bill_of_materials": {
            "status": "CHANGED" if any("|" in line and "MISMATCHED" in line for line in bom_comparison_table.split("\n")) else "MATCHED",
            "difference_summary": "BOM checked",
            "reference_content": bom_comparison_table, "revision_content": bom_comparison_table,
            "engineering_discrepancy_details": "Real BOM data used"
        },
        "canvas_markings": clean_markings
    }


    # Build ID lookup dictionaries
    id_to_rev_entity = {f"REV-{e.properties.get('handle')}": e for e in rev_entities if e.properties and e.properties.get('handle')}
    id_to_ref_entity = {f"REF-{e.properties.get('handle')}": e for e in ref_entities if e.properties and e.properties.get('handle')}

    if progress_callback:
        await progress_callback("finalizing", 90, "Resolving coordinates & finalizing")

    # Inject Title Block & BOM markings
    used_ref_entities = set()
    used_rev_entities = set()

    inject_title_block_markings(
        clean_markings, ref_title_fields, rev_title_fields, ref_entities, rev_entities,
        ref_title_bbox=ref_title_bbox, rev_title_bbox=rev_title_bbox,
    )
    inject_bom_markings(clean_markings, ref_bom_rows, rev_bom_rows, is_assembly_drawing, ref_bom_bbox, rev_bom_bbox, ref_entities, rev_entities, used_ref_entities, used_rev_entities)
    inject_ballooning_markings(clean_markings, ref_bom_rows, rev_bom_rows, ref_entities, rev_entities)

    # Coordinate Resolution
    resolve_marking_coordinates(
        clean_markings, id_to_rev_entity, id_to_ref_entity,
        rev_entities, ref_entities, rev_bom_rows, ref_bom_rows,
        rev_title_fields, ref_title_fields,
        rev_bom_bbox, ref_bom_bbox,
        rev_title_bbox, ref_title_bbox,
        rev_notes_bbox, ref_notes_bbox,
        rev_iso_bbox, ref_iso_bbox,
        rev_views_bbox, ref_views_bbox,
        rev_title_ul_bbox, ref_title_ul_bbox,
        used_rev_entities, used_ref_entities
    )

    # Value-only-coordinate safety net (docs/checklist-taxonomy-grouping-implementation-
    # plan.md, Phase 7) — defense-in-depth only; the deterministic paths above are
    # already value-only by construction (see harden_value_only_coordinates' docstring).
    harden_value_only_coordinates(clean_markings, ref_entities, rev_entities)

    # SAFE-ZONE NET — the last word on `shim` and `tolerance`.
    #
    # Both are reference data that is **never compared**: their boxes exist so other pools can
    # subtract them, and nothing inside either may reach the user as a finding. Every producer
    # above is meant to honour that, but each honours it differently -- `safe_filter` guards
    # only the drawing_views pool, the BOM and title-block injections consult no zone at all,
    # and `resolve_marking_coordinates` can move a marking after every one of those decisions
    # was taken. Three paths, one invariant, and it was reported violated from live reviews
    # twice in one day (see the v48 note in cache_manager).
    #
    # So it is enforced once, here, where every marking finally has its coordinates.
    #
    # Ownership, not a bare box test, because **a box is not a claim**: the revision's
    # `tolerance` box over-reaches into the title block on M745227N01 and 7 real `title_block`
    # findings sit inside it. `owner_of` walks ZONE_PRECEDENCE and `title` outranks
    # `tolerance`, so all 7 are claimed by `title` and survive -- measured, this net drops 0 of
    # them. A naive "is it inside the tolerance box" test would have deleted every one, which
    # is the silent-false-negative direction this system cannot detect.
    _suppressed = [
        (m, z)
        for m in clean_markings
        if (z := _safe_zone_owner(m, ref_regions, rev_regions))
    ]
    if _suppressed:
        _dropped_ids = {id(m) for m, _ in _suppressed}
        clean_markings[:] = [m for m in clean_markings if id(m) not in _dropped_ids]
        for m, zone in _suppressed:
            logger.info(
                f"Safe-zone net: dropped {m.get('status')} {m.get('category')} "
                f"{str(m.get('text_content'))[:40]!r} — owned by the `{zone}` zone, which is "
                f"never compared."
            )

    # Validate final markings coordinates and bounding boxes via DTO validation boundaries
    for m in clean_markings:
        coords = m.get("coordinates")
        if coords is not None:
            m["coordinates"] = Coordinate2D.from_list(coords).to_list()
        
        ref_coords = m.get("ref_coordinates")
        if ref_coords is not None:
            m["ref_coordinates"] = Coordinate2D.from_list(ref_coords).to_list()
            
        bbox = m.get("bbox")
        if bbox is not None:
            if len(bbox) == 2 and len(bbox[0]) == 2 and len(bbox[1]) == 2:
                flat_bbox = (bbox[0][0], bbox[0][1], bbox[1][0], bbox[1][1])
                validated_bbox = BoundingBox2D.from_tuple(flat_bbox)
                m["bbox"] = [[validated_bbox.xmin, validated_bbox.ymin], [validated_bbox.xmax, validated_bbox.ymax]]
                
        ref_bbox = m.get("ref_bbox")
        if ref_bbox is not None:
            if len(ref_bbox) == 2 and len(ref_bbox[0]) == 2 and len(ref_bbox[1]) == 2:
                flat_bbox = (ref_bbox[0][0], ref_bbox[0][1], ref_bbox[1][0], ref_bbox[1][1])
                validated_bbox = BoundingBox2D.from_tuple(flat_bbox)
                m["ref_bbox"] = [[validated_bbox.xmin, validated_bbox.ymin], [validated_bbox.xmax, validated_bbox.ymax]]

    # Tag provenance — deterministic candidates only ever resolve via exact entity
    # handle or don't resolve at all. The visual-bbox fallback belonged to the removed AI
    # generators (ADR-006), so today this is the only provenance there is; the tag is kept
    # because it is written into cached results and read by the learned overlay.
    #
    # Check coordinates OR ref_coordinates, not just coordinates: a REMOVED item never
    # has rev-side coordinates by definition (it doesn't exist on the revision) even
    # when it resolved perfectly via an exact entity handle on the reference side, and
    # the reverse for ADDED items (no ref-side coordinates by definition). Checking
    # coordinates alone mislabeled every correctly-resolved REMOVED candidate
    # "unresolved" and gave it an undeserved confidence penalty.
    candidates: list[ComparisonCandidate] = []
    for m in clean_markings:
        m["origin"] = "deterministic"
        m["resolution_method"] = (
            "entity_handle" if (m.get("coordinates") is not None or m.get("ref_coordinates") is not None) else "unresolved"
        )
        # Anything not run through a classifier above (e.g. inject_title_block_markings/
        # inject_bom_markings entries for fields with no taxonomy match) already sets
        # 'feature' explicitly to OTHER_FEATURE_KEY at the source; this only catches
        # markings from a path this phase didn't touch.
        if not m.get("feature"):
            m["feature"] = taxonomy.OTHER_FEATURE_KEY
        # 'zone' (used just above for coordinate_resolver disambiguation) isn't a
        # ComparisonCandidate field — dropped here the same way CanvasMarking has always
        # silently dropped unknown keys via Pydantic's default extra="ignore" behavior.
        candidates.append(ComparisonCandidate(**m))

    return candidates, parsed, zone_detection_warnings
