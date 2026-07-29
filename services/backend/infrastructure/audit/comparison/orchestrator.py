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
from . import taxonomy
from .feature_classifier import (
    classify_drawing_view_feature,
    classify_notes_feature,
    classify_iso_feature,
    classify_title_ul_feature,
)


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
    rev_entities: list
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
    """
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
    
    # Load cached Title Block OCR results
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

    ref_title_input = [e for e in ref_entities if not is_in_bbox(e, ref_tolerance_bbox_raw)]
    rev_title_input = [e for e in rev_entities if not is_in_bbox(e, rev_tolerance_bbox_raw)]

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

        def is_grid_label(e):
            t = (getattr(e, 'properties', {}) or {}).get('text', '').strip()
            if len(t) <= 1 or any(c in t for c in "①②③④⑤⑥⑦⑧⑨⑩⑪⑫"):
                vx = getattr(e, 'geometry', {}).get('insert', [0, 0, 0])[0]
                vy = getattr(e, 'geometry', {}).get('insert', [0, 0, 0])[1]
                if vx < 25.0 or vy > 285.0:
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
        
        import unicodedata
        val = str(entity.properties.get("text") or entity.properties.get("value") or "").strip()
        val = unicodedata.normalize("NFKC", val)
        is_grid_char = (
            val in {"A", "B", "C", "D", "E", "F", "G", "H"} or
            (val.isdigit() and 1 <= int(val) <= 12) or
            any(char in val for char in "①②③④⑤⑥⑦⑧⑨⑩⑪⑫")
        )
        # Use wider margin (6%) for sheet border grid references to completely exclude them
        margin_factor_x = 0.06 if is_grid_char else 0.025
        margin_factor_y = 0.06 if is_grid_char else 0.025
        
        margin_x = width * margin_factor_x
        margin_y = height * margin_factor_y
        
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

    def safe_filter(entities: list, bom_bbox, title_bbox, tol_bbox, notes_bbox, iso_bbox, title_ul_bbox, global_bounds, exclude_values: set | None = None) -> list:
        """Filter out template-zone entities, but never use a bbox that covers too much of the drawing."""
        use_bom      = bom_bbox      and not _bbox_covers_too_much(bom_bbox,      global_bounds)
        use_title    = title_bbox    and not _bbox_covers_too_much(title_bbox,    global_bounds)
        use_tol      = tol_bbox      and not _bbox_covers_too_much(tol_bbox,      global_bounds)
        use_notes    = notes_bbox    and not _bbox_covers_too_much(notes_bbox,    global_bounds)
        use_iso      = iso_bbox      and not _bbox_covers_too_much(iso_bbox,      global_bounds)
        use_title_ul = title_ul_bbox and not _bbox_covers_too_much(title_ul_bbox, global_bounds)

        result = [
            e for e in entities
            if not (
                (use_bom      and is_in_bbox(e, bom_bbox))      or
                (use_title    and is_in_bbox(e, title_bbox))    or
                (use_tol      and is_in_bbox(e, tol_bbox))      or
                (use_notes    and is_in_bbox(e, notes_bbox))    or
                (use_iso      and is_in_bbox(e, iso_bbox))      or
                (use_title_ul and is_in_bbox(e, title_ul_bbox)) or
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
            l = (getattr(e, "layer", "") or "").lower()
            if any(x in l for x in ("tol", "tolerance", "公差", "枠")):
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

        result = [
            e for e in result
            if not _is_bom_layer(getattr(e, "layer", "") or "")
            and not _is_title_layer(getattr(e, "layer", "") or "")
            and not _is_tolerance_layer_or_text(e)
        ]

        # Third safety net: exclude entities whose text exactly matches a value already
        # captured by structured title-block/BOM extraction — see
        # _collect_structured_text_values above for why this is needed in addition to
        # the bbox- and layer-based exclusions.
        if exclude_values:
            result = [
                e for e in result
                if _normalize_value_text(e.properties.get("text") or e.properties.get("value") or "") not in exclude_values
            ]

        # Safety valve: if filtering wiped everything out, fall back to margin-only exclusion
        if len(result) == 0 and len(entities) > 0:
            logger.warning("Entity filter produced empty set — falling back to margin-only exclusion.")
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

    filtered_ref_entities = safe_filter(
        ref_entities,
        ref_bom_bbox_raw, ref_title_bbox_raw, ref_tolerance_bbox_raw,
        ref_notes_bbox_raw, ref_iso_bbox_raw, ref_title_ul_bbox_raw,
        ref_global_bounds,
        exclude_values=ref_structured_values,
    )
    filtered_rev_entities = safe_filter(
        rev_entities,
        rev_bom_bbox_raw, rev_title_bbox_raw, rev_tolerance_bbox_raw,
        rev_notes_bbox_raw, rev_iso_bbox_raw, rev_title_ul_bbox_raw,
        rev_global_bounds,
        exclude_values=rev_structured_values,
    )

    logger.info(
        f"Filtered entity counts for Spatial Differ — "
        f"ref: {len(ref_entities)} → {len(filtered_ref_entities)} (notes={len(ref_notes_entities)}, iso={len(ref_iso_entities)}), "
        f"rev: {len(rev_entities)} → {len(filtered_rev_entities)} (notes={len(rev_notes_entities)}, iso={len(rev_iso_entities)})"
    )

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
    for m in notes_markings:
        m["feature"] = classify_notes_feature(m.get("text_content", ""), m.get("details", ""))
    for m in iso_markings:
        m["feature"] = classify_iso_feature(m.get("text_content", ""), m.get("details", ""))

    # Combine all visual checklist markings
    clean_markings.extend(notes_markings)
    clean_markings.extend(iso_markings)

    # Collapse content that was diffed against two different pools and therefore reported
    # twice -- once as REMOVED from where it used to sit, once as ADDED where it now sits.
    # This has to run after the three lists are combined, because the two halves of such a
    # pair are by definition in different lists. It also runs after feature classification so
    # the surviving marking keeps the label its category earned.
    # See marking_reconciler for why unambiguous pairs only.
    before_count = len(clean_markings)
    clean_markings = reconcile_relocated_markings(clean_markings)
    if len(clean_markings) != before_count:
        logger.info(
            f"Marking reconciliation: {before_count} -> {len(clean_markings)} findings "
            f"({(before_count - len(clean_markings))} relocated REMOVED/ADDED pairs merged)."
        )

    # Structured key-value extraction for Title Upper Left (top-left metadata)
    # (ref_title_ul_pairs and rev_title_ul_pairs were extracted earlier above)

    import unicodedata as _ud2
    import re as _re2
    def _ul_key(t: str) -> str:
        """NFKC + lowercase + whitespace collapse for stable cross-drawing key matching."""
        t = _ud2.normalize("NFKC", t or "").strip().lower()
        return _re2.sub(r"\s+", " ", t)

    # Build normalized key lookups
    ref_ul_map = {_ul_key(p['key']): p for p in ref_title_ul_pairs}
    rev_ul_map = {_ul_key(p['key']): p for p in rev_title_ul_pairs}
    ul_all_keys = list(dict.fromkeys(
        list(ref_ul_map.keys()) + list(rev_ul_map.keys())
    ))

    title_ul_table_rows = []
    for hdr_key in ul_all_keys:
        ref_p = ref_ul_map.get(hdr_key, {})
        rev_p = rev_ul_map.get(hdr_key, {})
        orig_val = ref_p.get('value', 'NONE') or 'NONE'
        kmti_val = rev_p.get('value', 'NONE') or 'NONE'
        orig_coords = ref_p.get('coords')
        kmti_coords = rev_p.get('coords')
        from ...utils.text import compare_values as _cmp
        status_val = _cmp(orig_val, kmti_val)
        display_key = ref_p.get('key') or rev_p.get('key') or hdr_key
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

    # Inject Title Block & BOM markings
    used_ref_entities = set()
    used_rev_entities = set()

    inject_title_block_markings(clean_markings, ref_title_fields, rev_title_fields, ref_entities, rev_entities)
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
    rev_entities: list
) -> PhysicalComparisonResponse:
    """
    `rag` method entrypoint. Thin wrapper around generate_deterministic_candidates()
    (Generator A) — this function's job is cache handling, response assembly, and
    persistence; the diffing itself lives in the extracted function so `hybrid` can
    reuse it too. Output here is unchanged from before that extraction (Phase 2 of
    docs/hybrid-comparison-engine-implementation-plan.md).
    """
    # Check cache first (unless force_refresh is requested)
    force_refresh = getattr(request, "force_refresh", False)
    cached_payload = None if force_refresh else ComparisonCacheManager.get_cached_comparison(
        ref_drawing_id=str(ref_drawing.id),
        rev_drawing_id=str(rev_drawing.id),
        ref_hash=ref_drawing.file_hash,
        rev_hash=rev_drawing.file_hash,
        method="rag"
    )
    if cached_payload:
        try:
            return PhysicalComparisonResponse(
                drawing_views=CategoryComparison(**cached_payload["drawing_views"]),
                notes_section=CategoryComparison(**cached_payload["notes_section"]),
                bill_of_materials=CategoryComparison(**cached_payload["bill_of_materials"]),
                title_block=CategoryComparison(**cached_payload["title_block"]),
                isometric_view=CategoryComparison(**cached_payload["isometric_view"]),
                other_engineering_references=CategoryComparison(**cached_payload["other_engineering_references"]),
                canvas_markings=[CanvasMarking(**item) for item in cached_payload.get("canvas_markings", [])],
                diagnostics=cached_payload.get("diagnostics"),
            )
        except Exception as cache_err:
            logger.warning(f"Failed to parse cached drawing comparison, performing full comparison: {cache_err}")

    candidates, parsed, zone_detection_warnings = await generate_deterministic_candidates(
        ref_drawing, rev_drawing, ref_entities, rev_entities
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

    return comparison_response
