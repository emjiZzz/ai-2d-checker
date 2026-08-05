import os
import re
import json
import asyncio
from datetime import datetime, UTC
from google.genai import types

from ....domain.models.audit_session import AuditSession
from ....domain.models.audit_violation import AuditViolation
from ....domain.models.drawing_document import DrawingDocument
from ....domain.models.extracted_entity import ExtractedEntity
from ....logger import logger
from ....config import settings
from ....api.schemas import (
    PhysicalComparisonResponse,
    CategoryComparison,
    CanvasMarking,
    ComparisonDiagnostics,
)
from ...storage.path_resolver import get_storage_root
from ...utils.text import (
    extract_semantic_text_groups,
    build_title_block_table,
    compare_values
)
from ..bom_analyzer import BOMAnalyzer
from .revision_resolver import resolve_revisions
from .gemini_client import execute_gemini_cascade
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
from .marking_reconciler import reconcile_relocated_markings
from .schemas import Coordinate2D, BoundingBox2D
from .cache_manager import ComparisonCacheManager
from .candidate import ComparisonCandidate
# Learned-correction layer. Applied POST-cache (see perform_drawing_comparison) so a retrain
# takes effect immediately without a cache-version bump; its output is never cached.
from ...learning.inference import apply_learned_adjustments
from . import taxonomy
from .feature_classifier import (
    classify_drawing_view_feature,
    classify_notes_feature,
    classify_iso_feature,
    refine_view_labels,
    classify_title_ul_feature,
)


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


def keep_for_title_extraction(entity, tolerance_bbox, title_bbox) -> bool:
    """Whether to feed `entity` to the title-block extractor.

    Title extraction excludes the tolerance table so its numeric cells aren't misread as title
    fields. But the detected/pinned tolerance box is frequently OVER-WIDE — spanning the full
    bottom strip — and then it also covers the bottom-right title block, so a naive
    `not is_in_bbox(e, tolerance_bbox)` deletes the real title fields and every one reads NONE
    (DRAWN/SCALE/DESIGNED/TITLE). Guard: drop an entity only when it is in the tolerance box AND
    NOT in the title box, so the tolerance *table* is removed but the title block is preserved.
    """
    geom = getattr(entity, "geometry", {}) or {}
    insert = geom.get("insert")
    in_tol = _point_in_bbox(insert, tolerance_bbox)
    in_title = _point_in_bbox(insert, title_bbox)
    return not (in_tol and not in_title)


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


# Bilingual header equivalences for the title-upper-left metadata table.
#
# `_title_ul_tokens`' shared-token rule assumes that when the header banding differs by scale,
# whichever labels survive on the two drawings still overlap. That holds when one side keeps
# BOTH stacked labels ('Unit No. / ユニットNo.') and the other keeps one of them. It fails when
# the two sides keep DIFFERENT halves — measured live: the reference emitted `コードNO.` and the
# revision `PART NO.` for the same column, sharing no token, so the field never paired and its
# identical value 230 was reported twice (230 → NONE and NONE → 230).
#
# These four pairs are the English/Japanese labels of one JIS-style table, the same eight
# strings `vault_sync.get_upper_left_anchors()` already lists — as a flat list, with no record
# of which pair with which. Kept in code rather than sourced from the vault because
# `08 - Client Domain & CAD Rules/` is gitignored: a fix verifiable on exactly one machine is
# the failure mode this vault keeps having to record. A client using different terms should
# extend this tuple.
_TITLE_UL_SYNONYMS: tuple[frozenset[str], ...] = (
    frozenset({"unitno", "ユニットno"}),
    frozenset({"partno", "コードno"}),
    frozenset({"tqty", "総製作個数"}),
    frozenset({"stockqty", "在庫棚入庫"}),
)


def _ul_canonical(token: str) -> str:
    """A header token reduced to its letters, digits and CJK.

    `Part No.`, `PART NO` and `part　no.` all collapse to `partno`, so the synonym table does
    not have to enumerate punctuation and spacing variants of eight strings.
    """
    import re as _r
    return _r.sub(r"[^0-9a-z぀-ヿ一-鿿]", "", token or "")


def _ul_synonym_groups(tokens: set) -> set:
    """Indices of the synonym groups a key's tokens belong to."""
    canonical = {_ul_canonical(t) for t in tokens}
    return {i for i, group in enumerate(_TITLE_UL_SYNONYMS) if canonical & group}


def _title_ul_tokens(key: str) -> set:
    """Normalized header tokens of a title-upper-left key. A field's key is one or more
    stacked header labels joined by ' / ' (e.g. 'Unit No. / ユニットNo.'). Which labels land in
    the key depends on coordinate scale -- the header banding uses a fixed y-threshold, so a
    large-coordinate drawing splits the English and Japanese header rows into separate bands
    (both in the key) while a small-coordinate one merges them (only the nearest single label
    in the key). The same field therefore emits DIFFERENT combined keys on the two drawings."""
    import unicodedata as _u
    import re as _r
    def _n(t: str) -> str:
        return _r.sub(r"\s+", " ", _u.normalize("NFKC", t or "").strip().lower())
    return {_n(part) for part in str(key).split(" / ") if _n(part)}


def match_title_ul_pairs(ref_pairs: list, rev_pairs: list) -> list:
    """Greedy-match reference↔revision title-upper-left pairs by shared header token, so the
    same field pairs up even when the two drawings emitted different combined keys (see
    _title_ul_tokens). Returns [(ref_pair | None, rev_pair | None), ...]; a one-sided tuple is
    a genuinely added/removed field. Replaces an exact-combined-key lookup that double-reported
    every identical value as REMOVED + ADDED whenever the header banding differed by scale."""
    rev_unmatched = list(rev_pairs)
    matched: list = []
    for ref_p in ref_pairs:
        rt = _title_ul_tokens(ref_p.get("key", ""))
        rg = _ul_synonym_groups(rt)
        # Shared token first — the common case, and exact. Only when that finds nothing do we
        # fall back to the synonym table, so an English/Japanese equivalence can never override
        # a literal match that was already available.
        hit = next((rp for rp in rev_unmatched if rt & _title_ul_tokens(rp.get("key", ""))), None)
        if hit is None and rg:
            hit = next(
                (rp for rp in rev_unmatched if rg & _ul_synonym_groups(_title_ul_tokens(rp.get("key", "")))),
                None,
            )
        if hit is not None:
            rev_unmatched.remove(hit)
            matched.append((ref_p, hit))
        else:
            matched.append((ref_p, None))
    for rev_p in rev_unmatched:
        matched.append((None, rev_p))
    return matched


def build_marking_table(markings: list, category_filter: str | None = None) -> str:
    """
    Build a pipe-table summary from a list of marking dicts for the checklist panel.

    Module-level (hoisted out of generate_deterministic_candidates, where it started as
    a nested closure — it doesn't close over anything, so the move is behavior-neutral)
    so hybrid_orchestrator.py can reuse it to rebuild category tables from the final
    reconciled/verified candidate list instead of only Generator A's raw output
    (docs/hybrid-comparison-engine-implementation-plan.md, Phase 6 follow-up).
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


async def generate_deterministic_candidates(
    ref_drawing: DrawingDocument,
    rev_drawing: DrawingDocument,
    ref_entities: list,
    rev_entities: list,
    refresh_ocr: bool = False,
    progress_callback=None,
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
    endpoint can stream real progress. hybrid_orchestrator deliberately passes None — it runs
    this concurrently with Generator B and reports the pair as one stage.
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

    def is_in_bbox(entity, bbox: tuple) -> bool:
        if not bbox: return False
        geom = getattr(entity, 'geometry', {})
        if not geom or 'insert' not in geom or len(geom['insert']) < 2: return False
        x, y = geom['insert'][0], geom['insert'][1]
        return bbox[0] <= x <= bbox[2] and bbox[1] <= y <= bbox[3]

    # Compute bounding boxes for visual overlap warnings and spatial constraints
    from ..bom.table_extractor import extract_dynamic_regions_async, summarize_zone_detection_confidence
    # render_bounds is what hand-aligned zone fractions are stored relative to, and the
    # sheet signature is derived from it. `layout_signature` was read here previously but is
    # never written anywhere, so it was always None.
    ref_bounds = (ref_drawing.metadata or {}).get("render_bounds")
    rev_bounds = (rev_drawing.metadata or {}).get("render_bounds")

    ref_regions = await extract_dynamic_regions_async(ref_entities, render_bounds=ref_bounds)
    rev_regions = await extract_dynamic_regions_async(rev_entities, render_bounds=rev_bounds)
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

    # Exclude the tolerance table from title extraction, but never an entity that also sits in
    # the title block — an over-wide tolerance box otherwise blanks the whole title block. See
    # keep_for_title_extraction.
    ref_title_input = [e for e in ref_entities if keep_for_title_extraction(e, ref_tolerance_bbox_raw, ref_title_bbox)]
    rev_title_input = [e for e in rev_entities if keep_for_title_extraction(e, rev_tolerance_bbox_raw, rev_title_bbox)]

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
    import unicodedata as _ud_vals

    def _normalize_value_text(t) -> str:
        return _ud_vals.normalize("NFKC", str(t or "")).strip().lower()

    def _collect_structured_text_values(*sources) -> set:
        values: set = set()
        for source in sources:
            if isinstance(source, dict):
                # title-field-style: {field_key: {"value": ...} | str}
                for obj in source.values():
                    val = obj.get("value") if isinstance(obj, dict) else obj
                    if val and str(val).strip().upper() != "NONE":
                        values.add(_normalize_value_text(val))
            elif isinstance(source, list):
                # BOM-row-style: [{col_key: {"value": ...} | str, ...}, ...]
                for row in source:
                    if not isinstance(row, dict):
                        continue
                    for obj in row.values():
                        val = obj.get("value") if isinstance(obj, dict) else obj
                        if val and str(val).strip().upper() != "NONE":
                            values.add(_normalize_value_text(val))
        return values

    def extract_title_ul_kv(entities: list, bbox) -> list:
        """Spatially pair header/label texts with their value texts inside bbox.
        DXF uses Y-up coordinates — larger Y is physically higher on the sheet.
        Headers sit ABOVE values, so headers have larger Y values.
        Returns list of {key, value, coords} dicts sorted left-to-right.
        """
        import unicodedata as _ud
        def _ul_norm(t: str) -> str:
            t = _ud.normalize("NFKC", t or "").strip().lower()
            import re as _re
            return _re.sub(r"\s+", " ", t)

        if not bbox:
            return []
        inside = [
            e for e in entities
            if getattr(e, 'entity_type', '') in ('text', 'mtext', 'attrib')
            and is_in_bbox(e, bbox)
        ]
        if not inside:
            return []

        # Frame grid references (single chars at the sheet edge) can leak into the UL zone;
        # exclude them. The edge is measured RELATIVE to the zone bbox, not with absolute
        # vx<25/vy>285: those constants only hold in the small coordinate space, and on a
        # large-coordinate drawing they dropped a legitimate single-digit UL VALUE (a '0'
        # Stock Q'ty at y~822) as if it were a top-margin grid label.
        _bw = (bbox[2] - bbox[0]) or 1.0
        _bh = (bbox[3] - bbox[1]) or 1.0

        def is_grid_label(e):
            t = (getattr(e, 'properties', {}) or {}).get('text', '').strip()
            if len(t) <= 1 or any(c in t for c in "①②③④⑤⑥⑦⑧⑨⑩⑪⑫"):
                vx = getattr(e, 'geometry', {}).get('insert', [0, 0, 0])[0]
                vy = getattr(e, 'geometry', {}).get('insert', [0, 0, 0])[1]
                if vx < bbox[0] + 0.08 * _bw or vy > bbox[3] - 0.08 * _bh:
                    return True
            return False

        inside = [e for e in inside if not is_grid_label(e)]
        if not inside:
            return []

        inside.sort(key=lambda x: getattr(x, 'geometry', {}).get('insert', [0, 0, 0])[1], reverse=True)
        bands: list[list] = []
        current_band = []
        for e in inside:
            if not current_band:
                current_band.append(e)
            else:
                prev_y = getattr(current_band[-1], 'geometry', {}).get('insert', [0, 0, 0])[1]
                ey = getattr(e, 'geometry', {}).get('insert', [0, 0, 0])[1]
                if abs(prev_y - ey) <= 4.0:
                    current_band.append(e)
                else:
                    bands.append(current_band)
                    current_band = [e]
        if current_band:
            bands.append(current_band)

        if len(bands) < 2:
            return []

        value_band = sorted(bands[-1], key=lambda e: getattr(e, 'geometry', {}).get('insert', [0, 0, 0])[0])
        header_bands = bands[:-1]

        all_xs = [getattr(e, 'geometry', {}).get('insert', [0])[0] for e in inside]
        band_width = (max(all_xs) - min(all_xs)) if len(all_xs) > 1 else 9999.0
        max_pair_dist = max(band_width / max(len(value_band), 1) * 1.5, 30.0)

        pairs = []
        for val_e in value_band:
            vx = getattr(val_e, 'geometry', {}).get('insert', [0, 0, 0])[0]
            vy = getattr(val_e, 'geometry', {}).get('insert', [0, 0, 0])[1]
            val_text = (getattr(val_e, 'properties', {}) or {}).get('text', '').strip()
            if not val_text or len(val_text) <= 0:
                continue

            header_parts = []
            for hband in header_bands:
                closest_hdr = min(
                    hband,
                    key=lambda h: abs(getattr(h, 'geometry', {}).get('insert', [0, 0, 0])[0] - vx),
                    default=None
                )
                if closest_hdr:
                    dist = abs(getattr(closest_hdr, 'geometry', {}).get('insert', [0, 0, 0])[0] - vx)
                    if dist <= max_pair_dist:
                        hdr_text = (getattr(closest_hdr, 'properties', {}) or {}).get('text', '').strip()
                        if hdr_text and hdr_text not in header_parts and not hdr_text.isdigit():
                            header_parts.append(hdr_text)

            header_parts.reverse()
            header_parts = [
                p for p in header_parts 
                if not (p.startswith('①') or p.startswith('②') or p.startswith('③') or p.startswith('④') or p.strip().isdigit())
            ]

            combined_key = " / ".join(header_parts) if header_parts else "Value"
            pairs.append({'key': combined_key, 'value': val_text, 'coords': [vx, vy]})
        return pairs

    ref_title_ul_pairs = extract_title_ul_kv(ref_entities, ref_title_ul_bbox_raw)
    rev_title_ul_pairs = extract_title_ul_kv(rev_entities, rev_title_ul_bbox_raw)

    ref_structured_values = _collect_structured_text_values(ref_title_fields, ref_bom_rows, ref_title_ul_pairs)
    rev_structured_values = _collect_structured_text_values(rev_title_fields, rev_bom_rows, rev_title_ul_pairs)

    # Bounding boxes and spatial differ imports were hoisted earlier

    from ..bom.spatial_utils import compute_drawing_bounds
    ref_global_bounds = compute_drawing_bounds(ref_entities)
    rev_global_bounds = compute_drawing_bounds(rev_entities)

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

    def extract_zone_entities(entities: list, bbox: tuple | None, global_bounds: tuple | None, exclude_bboxes: list | None = None, exclude_values: set | None = None) -> list:
        if not bbox or _bbox_covers_too_much(bbox, global_bounds):
            return []

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
                if not should_exclude:
                    result.append(e)
        return result

    def safe_filter(entities: list, bom_bbox, title_bbox, tol_bbox, notes_bbox, iso_bbox, title_ul_bbox, global_bounds, exclude_values: set | None = None, shim_bbox=None) -> list:
        """Apply the drawing_views noise filters to an already views-scoped entity set.

        `entities` here is the views-scoped pool (scope_entities_to_views), NOT the whole sheet.
        This strips margin/frame labels, sibling-zone furniture that overlaps the views box,
        title/BOM/tolerance layers, revision-table headers, learned dismissals, and values
        already captured by structured extraction. The sibling-bbox exclusions are now largely
        defensive (scope_entities_to_views already dropped centroid-in-sibling entities), kept
        because they also catch entities that straddle a boundary. Never uses a bbox that covers
        too much of the drawing for exclusion."""
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
                (use_bom      and is_in_bbox(e, bom_bbox))      or
                (use_title    and is_in_bbox(e, title_bbox))    or
                (use_tol      and is_in_bbox(e, tol_bbox))      or
                (use_notes    and is_in_bbox(e, notes_bbox))    or
                (use_iso      and is_in_bbox(e, iso_bbox))      or
                (use_title_ul and is_in_bbox(e, title_ul_bbox)) or
                (use_shim     and is_in_bbox(e, shim_bbox))     or
                is_in_margin(e, global_bounds)
            )
        ]
        
        # Additional safety net: explicitly exclude entities based on layer keywords to guarantee 
        # they are not double-processed by diff_views even if their coordinates slip outside the bbox.
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
        try:
            from ...knowledge.vault_sync import VaultSyncManager
            learned_patterns = {
                _normalize_value_text(p)
                for p in VaultSyncManager.get_instance().get_learned_dismissals()
            }
            learned_patterns.discard("")
        except Exception as err:
            logger.warning(f"Learned dismissal rules unavailable, continuing without: {err}")
            learned_patterns = set()

        if learned_patterns:
            before_learned = len(result)
            result = [
                e for e in result
                if _normalize_value_text(
                    e.properties.get("text") or e.properties.get("value") or ""
                ) not in learned_patterns
            ]
            if len(result) != before_learned:
                # Logged, not silent: this is the one filter driven by stored human decisions
                # rather than by the drawing, so it must be visible when it fires.
                logger.info(
                    f"Learned dismissal rules excluded {before_learned - len(result)} "
                    f"entit(ies) from {len(learned_patterns)} human-confirmed pattern(s)."
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

    # Extract Notes entities specifically for notes_section diffing
    ref_notes_entities = extract_zone_entities(
        ref_entities, ref_notes_bbox_raw, ref_global_bounds,
        exclude_bboxes=[ref_tolerance_bbox_raw, ref_title_bbox_raw, ref_bom_bbox_raw],
        exclude_values=ref_structured_values,
    )
    rev_notes_entities = extract_zone_entities(
        rev_entities, rev_notes_bbox_raw, rev_global_bounds,
        exclude_bboxes=[rev_tolerance_bbox_raw, rev_title_bbox_raw, rev_bom_bbox_raw],
        exclude_values=rev_structured_values,
    )

    # Extract Isometric view entities specifically for isometric_view diffing
    ref_iso_entities = extract_zone_entities(
        ref_entities, ref_iso_bbox_raw, ref_global_bounds,
        exclude_bboxes=[ref_tolerance_bbox_raw, ref_title_bbox_raw, ref_bom_bbox_raw],
        exclude_values=ref_structured_values,
    )
    rev_iso_entities = extract_zone_entities(
        rev_entities, rev_iso_bbox_raw, rev_global_bounds,
        exclude_bboxes=[rev_tolerance_bbox_raw, rev_title_bbox_raw, rev_bom_bbox_raw],
        exclude_values=rev_structured_values,
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

    ref_views_pool = scope_entities_to_views(
        ref_entities, ref_views_bbox_raw, views_exclusions(ref_regions)
    )
    rev_views_pool = scope_entities_to_views(
        rev_entities, rev_views_bbox_raw, views_exclusions(rev_regions)
    )

    filtered_ref_entities = safe_filter(
        ref_views_pool,
        ref_bom_bbox_raw, ref_title_bbox_raw, ref_tolerance_bbox_raw,
        ref_notes_bbox_raw, ref_iso_bbox_raw, ref_title_ul_bbox_raw,
        ref_global_bounds,
        exclude_values=ref_structured_values,
        shim_bbox=ref_shim_bbox_raw,
    )
    filtered_rev_entities = safe_filter(
        rev_views_pool,
        rev_bom_bbox_raw, rev_title_bbox_raw, rev_tolerance_bbox_raw,
        rev_notes_bbox_raw, rev_iso_bbox_raw, rev_title_ul_bbox_raw,
        rev_global_bounds,
        exclude_values=rev_structured_values,
        shim_bbox=rev_shim_bbox_raw,
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

    def _pos_in_bboxes(pos, bboxes) -> bool:
        if not pos or len(pos) < 2 or not bboxes:
            return False
        return any(b[0] <= pos[0] <= b[2] and b[1] <= pos[1] <= b[3] for b in bboxes)

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
    _ul_matched = match_title_ul_pairs(ref_title_ul_pairs, rev_title_ul_pairs)

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
    # handle or don't resolve at all; the visual-bbox fallback is AI-generator-only
    # (see generate_ai_vision_candidates in full_ai_orchestrator.py, Phase 2).
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


async def perform_drawing_comparison(
    request,
    ref_drawing: DrawingDocument,
    rev_drawing: DrawingDocument,
    ref_entities: list,
    rev_entities: list,
    progress_callback=None,
) -> PhysicalComparisonResponse:
    """
    `rag` method entrypoint. Thin wrapper around generate_deterministic_candidates()
    (Generator A) — this function's job is cache handling, response assembly, and
    persistence; the diffing itself lives in the extracted function so `hybrid` can
    reuse it too. Output here is unchanged from before that extraction (Phase 2 of
    docs/hybrid-comparison-engine-implementation-plan.md).
    """
    # Check cache first (unless force_refresh is requested). refresh_ocr implies force_refresh:
    # a re-read OCR value only reaches the output through a fresh comparison run.
    refresh_ocr = getattr(request, "refresh_ocr", False)
    force_refresh = getattr(request, "force_refresh", False) or refresh_ocr
    cached_payload = None if force_refresh else ComparisonCacheManager.get_cached_comparison(
        ref_drawing_id=str(ref_drawing.id),
        rev_drawing_id=str(rev_drawing.id),
        ref_hash=ref_drawing.file_hash,
        rev_hash=rev_drawing.file_hash,
        method="rag"
    )
    if cached_payload:
        try:
            cached_response = PhysicalComparisonResponse(
                drawing_views=CategoryComparison(**cached_payload["drawing_views"]),
                notes_section=CategoryComparison(**cached_payload["notes_section"]),
                bill_of_materials=CategoryComparison(**cached_payload["bill_of_materials"]),
                title_block=CategoryComparison(**cached_payload["title_block"]),
                isometric_view=CategoryComparison(**cached_payload["isometric_view"]),
                other_engineering_references=CategoryComparison(**cached_payload["other_engineering_references"]),
                canvas_markings=[CanvasMarking(**item) for item in cached_payload.get("canvas_markings", [])],
                diagnostics=cached_payload.get("diagnostics"),
            )
            # Apply the learned model to the cached deterministic result at serve time, so a
            # correction takes effect on already-cached pairs without invalidating the cache.
            return apply_learned_adjustments(cached_response, ref_entities, rev_entities)
        except Exception as cache_err:
            logger.warning(f"Failed to parse cached drawing comparison, performing full comparison: {cache_err}")

    candidates, parsed, zone_detection_warnings = await generate_deterministic_candidates(
        ref_drawing, rev_drawing, ref_entities, rev_entities, refresh_ocr=refresh_ocr, progress_callback=progress_callback
    )

    clean_markings = [c.model_dump() for c in candidates]

    comparison_response = PhysicalComparisonResponse(
        drawing_views=CategoryComparison(**parsed["drawing_views"]),
        notes_section=CategoryComparison(**parsed["notes_section"]),
        bill_of_materials=CategoryComparison(**parsed["bill_of_materials"]),
        title_block=CategoryComparison(**parsed["title_block"]),
        isometric_view=CategoryComparison(**parsed["isometric_view"]),
        other_engineering_references=CategoryComparison(**parsed["other_engineering_references"]),
        canvas_markings=[CanvasMarking(**item) for item in clean_markings],
        diagnostics=ComparisonDiagnostics(zone_detection_warnings=zone_detection_warnings),
    )

    # Save comparison findings as AuditSession + AuditViolations
    try:
        non_matched = [m for m in clean_markings if m.get("status") != "MATCHED"]
        total_markings = len(clean_markings)
        matched_count = total_markings - len(non_matched)
        comparison_score = round((matched_count / total_markings) * 100, 2) if total_markings > 0 else 100.0

        comparison_session = AuditSession(
            drawing_id=str(rev_drawing.id),
            reference_drawing_id=str(ref_drawing.id),
            standard_id=None,
            client_name=None,
            status="completed",
            compliance_score=comparison_score,
            confidence_score=0.95,
            timings={},
            diagnostics={
                "source": "physical_comparison",
                "comparison_method": "rag",
                "total_markings": total_markings,
                "non_matched": len(non_matched),
            },
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
        )
        await comparison_session.save()

        SEVERITY_MAP = {"CHANGED": "medium", "ADDED": "high", "REMOVED": "high"}
        violations_to_save = []
        for marking_dict in non_matched:
            marking = CanvasMarking(**marking_dict)
            coords = None
            if marking.coordinates:
                if isinstance(marking.coordinates, list):
                    if len(marking.coordinates) > 0 and not isinstance(marking.coordinates[0], list):
                        coords = [marking.coordinates]
                    else:
                        coords = marking.coordinates

            violations_to_save.append(
                AuditViolation(
                    audit_session_id=str(comparison_session.id),
                    severity=SEVERITY_MAP.get(marking.status, "medium"),
                    category=f"comparison_{marking.category}",
                    description=f"[{marking.status}] {marking.details}",
                    recommendation=f"Resolve discrepancy in '{marking.text_content}' against the reference drawing.",
                    source="physical_comparison",
                    confidence=0.95,
                    standard_reference=None,
                    affected_entities=[
                        {"entity_id": marking.entity_id, "marker_shape": "BOX"}
                    ] if marking.entity_id else [],
                    coordinates=coords,
                )
            )

        if violations_to_save:
            await AuditViolation.insert_many(violations_to_save)

        logger.info(
            f"Phase 1.4: Persisted {len(violations_to_save)} comparison violations "
            f"(session {comparison_session.id}, score {comparison_score}%)."
        )
    except Exception as persist_err:
        logger.warning(f"Comparison violation persistence failed (non-fatal): {persist_err}")

    try:
        ComparisonCacheManager.set_cached_comparison(
            ref_drawing_id=str(ref_drawing.id),
            rev_drawing_id=str(rev_drawing.id),
            ref_hash=ref_drawing.file_hash,
            rev_hash=rev_drawing.file_hash,
            payload=comparison_response.model_dump(),
            method="rag"
        )
    except Exception as cache_write_err:
        logger.warning(f"Failed to cache physical comparison response: {cache_write_err}")

    # Learned adjustments run AFTER the cache write above, so the deterministic result is what
    # gets cached and the model overlay is recomputed fresh on every serve.
    return apply_learned_adjustments(comparison_response, ref_entities, rev_entities)
