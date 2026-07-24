"""
result_parser.py — Gemini response parsing, coordinate resolution, and deterministic overrides.
"""

import json
import math
from typing import Any

from .....logger import logger
from .....api.schemas import (
    PhysicalComparisonResponse,
    CategoryComparison,
    CanvasMarking,
    ComparisonDiagnostics,
)
from ..coordinate_resolver import resolve_marking_coordinates, harden_value_only_coordinates
from ..schemas import Coordinate2D, BoundingBox2D
from .. import taxonomy


def parse_and_normalize_gemini_json(raw_json_text: str) -> dict[str, Any]:
    """
    Parses raw JSON string from Gemini response and enforces required top-level category keys.
    """
    try:
        parsed = json.loads(raw_json_text)
    except json.JSONDecodeError as parse_err:
        logger.error(f"[full_ai] Gemini returned non-JSON response: {parse_err}")
        raise RuntimeError(f"Full-AI comparison: Gemini returned malformed JSON: {parse_err}")

    _empty_category = {
        "status": "MATCHED",
        "difference_summary": "No differences detected.",
        "reference_content": "",
        "revision_content": "",
        "engineering_discrepancy_details": "",
    }
    for cat in (
        "drawing_views",
        "notes_section",
        "bill_of_materials",
        "title_block",
        "isometric_view",
        "other_engineering_references",
    ):
        if cat not in parsed:
            parsed[cat] = _empty_category.copy()

    if "canvas_markings" not in parsed:
        parsed["canvas_markings"] = []

    return parsed


def apply_deterministic_overrides(
    parsed: dict[str, Any],
    bom_table_text: str | None,
    title_block_table_text: str | None
) -> None:
    """
    Applies deterministic BOM and Title Block status overrides onto Gemini results.
    """
    # Deterministic BOM Override
    bom_status = "CHANGED" if any("|" in line and "MISMATCHED" in line for line in (bom_table_text or "").split("\n")) else "MATCHED"
    gemini_summary = parsed["bill_of_materials"].get("difference_summary", "")

    contradicts_matched = (bom_status == "MATCHED" and any(w in gemini_summary.lower() for w in ("added", "removed", "changed", "updated")))
    contradicts_changed = (bom_status == "CHANGED" and any(w in gemini_summary.lower() for w in ("added", "removed")))

    if contradicts_matched:
        final_summary = "No BOM discrepancies detected."
        final_details = ""
    elif contradicts_changed:
        final_summary = "BOM table was modified."
        final_details = "Specific row discrepancies verified via Deterministic Spatial Differ."
    else:
        final_summary = gemini_summary
        final_details = parsed["bill_of_materials"].get("engineering_discrepancy_details", "")

    parsed["bill_of_materials"].update({
        "status": bom_status,
        "reference_content": bom_table_text or "(No BOM)",
        "revision_content": bom_table_text or "(No BOM)",
        "difference_summary": final_summary,
        "engineering_discrepancy_details": final_details,
    })

    # Deterministic Title Block Override
    title_status = "CHANGED" if any("|" in line and "MISMATCHED" in line for line in (title_block_table_text or "").split("\n")) else "MATCHED"
    gemini_title_summary = parsed["title_block"].get("difference_summary", "")

    title_contradicts_matched = (title_status == "MATCHED" and any(w in gemini_title_summary.lower() for w in ("added", "removed", "changed", "updated")))
    title_contradicts_changed = (title_status == "CHANGED" and any(w in gemini_title_summary.lower() for w in ("added", "removed")))

    if title_contradicts_matched:
        final_title_summary = "No title block discrepancies detected."
        final_title_details = ""
    elif title_contradicts_changed:
        final_title_summary = "Title block was modified."
        final_title_details = "Specific field discrepancies verified via deterministic field comparison."
    else:
        final_title_summary = gemini_title_summary
        final_title_details = parsed["title_block"].get("engineering_discrepancy_details", "")

    parsed["title_block"].update({
        "status": title_status,
        "reference_content": title_block_table_text or "(No title block data)",
        "revision_content": title_block_table_text or "(No title block data)",
        "difference_summary": final_title_summary,
        "engineering_discrepancy_details": final_title_details,
    })

    # Downgrade markings if category status is CHANGED
    clean_markings = parsed["canvas_markings"]
    if bom_status == "CHANGED":
        for m in clean_markings:
            if m.get("category") == "bill_of_materials" and m.get("status") in ("ADDED", "REMOVED"):
                m["status"] = "CHANGED"

    if title_status == "CHANGED":
        for m in clean_markings:
            if m.get("category") == "title_block" and m.get("status") in ("ADDED", "REMOVED"):
                m["status"] = "CHANGED"


def resolve_and_harden_coordinates(
    parsed: dict[str, Any],
    ref_drawing: Any,
    rev_drawing: Any,
    ref_entities: list[Any],
    rev_entities: list[Any],
    ref_regions: dict[str, Any],
    rev_regions: dict[str, Any],
    ref_bom_rows: list[Any],
    rev_bom_rows: list[Any],
    ref_title_fields: dict[str, Any],
    rev_title_fields: dict[str, Any],
) -> None:
    """
    Executes text-based coordinate resolution, visual bbox fallbacks, spatial deduplication,
    and taxonomy feature normalization.
    """
    clean_markings = parsed["canvas_markings"]

    # 1. Extract region bounding boxes
    _to_bbox = lambda raw: BoundingBox2D.from_tuple(raw).to_tuple() if raw else None
    ref_title_bbox = _to_bbox(ref_regions.get("title"))
    rev_title_bbox = _to_bbox(rev_regions.get("title"))
    ref_notes_bbox = _to_bbox(ref_regions.get("notes"))
    rev_notes_bbox = _to_bbox(rev_regions.get("notes"))
    ref_iso_bbox = _to_bbox(ref_regions.get("iso"))
    rev_iso_bbox = _to_bbox(rev_regions.get("iso"))
    ref_views_bbox = _to_bbox(ref_regions.get("views"))
    rev_views_bbox = _to_bbox(rev_regions.get("views"))
    ref_title_ul_bbox = _to_bbox(ref_regions.get("title_upper_left"))
    rev_title_ul_bbox = _to_bbox(rev_regions.get("title_upper_left"))
    ref_bom_bbox_validated = _to_bbox(ref_regions.get("bom"))
    rev_bom_bbox_validated = _to_bbox(rev_regions.get("bom"))

    # 2. Build entity ID lookup dictionaries
    id_to_rev_entity = {
        f"REV-{e.properties.get('handle')}": e
        for e in rev_entities if e.properties and e.properties.get("handle")
    }
    id_to_ref_entity = {
        f"REF-{e.properties.get('handle')}": e
        for e in ref_entities if e.properties and e.properties.get("handle")
    }
    used_rev_entities: set = set()
    used_ref_entities: set = set()

    # 3. Text-based coordinate resolution
    try:
        resolve_marking_coordinates(
            clean_markings, id_to_rev_entity, id_to_ref_entity,
            rev_entities, ref_entities, rev_bom_rows, ref_bom_rows,
            rev_title_fields, ref_title_fields,
            rev_bom_bbox_validated, ref_bom_bbox_validated,
            rev_title_bbox, ref_title_bbox,
            rev_notes_bbox, ref_notes_bbox,
            rev_iso_bbox, ref_iso_bbox,
            rev_views_bbox, ref_views_bbox,
            rev_title_ul_bbox, ref_title_ul_bbox,
            used_rev_entities, used_ref_entities,
        )
    except Exception as resolve_err:
        logger.warning(f"[full_ai] Coordinate resolution failed (non-fatal): {resolve_err}")

    # 4. Visual coordinate fallback
    def _visual_to_cad(visual_bbox: list[float], render_bounds: list[float]) -> list[float]:
        ymin_n, xmin_n, ymax_n, xmax_n = visual_bbox
        x_min_cad, y_min_cad, x_max_cad, y_max_cad = render_bounds
        cad_w = x_max_cad - x_min_cad
        cad_h = y_max_cad - y_min_cad
        x_frac = ((xmin_n + xmax_n) / 2.0) / 1000.0
        y_frac = ((ymin_n + ymax_n) / 2.0) / 1000.0
        x_cad = x_min_cad + (x_frac * cad_w)
        y_cad = y_min_cad + ((1.0 - y_frac) * cad_h)
        return [x_cad, y_cad]

    rev_render_bounds = rev_drawing.metadata.get("render_bounds") if rev_drawing and rev_drawing.metadata else None
    ref_render_bounds = ref_drawing.metadata.get("render_bounds") if ref_drawing and ref_drawing.metadata else None

    for m in clean_markings:
        if m.get("coordinates") is None and m.get("visual_bbox") and rev_render_bounds:
            try:
                m["coordinates"] = _visual_to_cad(m["visual_bbox"], rev_render_bounds)
            except Exception:
                pass
        if m.get("ref_coordinates") is None and m.get("ref_visual_bbox") and ref_render_bounds:
            try:
                m["ref_coordinates"] = _visual_to_cad(m["ref_visual_bbox"], ref_render_bounds)
            except Exception:
                pass

    # 5. Spatial deduplication within 5mm threshold
    DEDUP_THRESHOLD_MM = 5.0
    deduped_markings: list[dict] = []
    for m in clean_markings:
        coords = m.get("coordinates")
        is_duplicate = False
        if coords and len(coords) >= 2:
            for existing in deduped_markings:
                ec = existing.get("coordinates")
                if ec and len(ec) >= 2:
                    dist = math.hypot(coords[0] - ec[0], coords[1] - ec[1])
                    if dist < DEDUP_THRESHOLD_MM and m.get("status") == existing.get("status") and m.get("category") == existing.get("category"):
                        if len(m.get("details", "")) > len(existing.get("details", "")):
                            existing.update(m)
                        is_duplicate = True
                        break
        if not is_duplicate:
            deduped_markings.append(m)

    clean_markings = deduped_markings

    # 6. Safety net for value-only coordinates & DTO constraint normalization
    harden_value_only_coordinates(clean_markings, ref_entities, rev_entities)

    for m in clean_markings:
        coords = m.get("coordinates")
        if coords is not None:
            m["coordinates"] = Coordinate2D.from_list(coords).to_list()
        ref_coords = m.get("ref_coordinates")
        if ref_coords is not None:
            m["ref_coordinates"] = Coordinate2D.from_list(ref_coords).to_list()
        bbox = m.get("bbox")
        if bbox is not None and len(bbox) == 2 and len(bbox[0]) == 2 and len(bbox[1]) == 2:
            flat = (bbox[0][0], bbox[0][1], bbox[1][0], bbox[1][1])
            vb = BoundingBox2D.from_tuple(flat)
            m["bbox"] = [[vb.xmin, vb.ymin], [vb.xmax, vb.ymax]]
        ref_bbox_val = m.get("ref_bbox")
        if ref_bbox_val is not None and len(ref_bbox_val) == 2 and len(ref_bbox_val[0]) == 2 and len(ref_bbox_val[1]) == 2:
            flat = (ref_bbox_val[0][0], ref_bbox_val[0][1], ref_bbox_val[1][0], ref_bbox_val[1][1])
            vb = BoundingBox2D.from_tuple(flat)
            m["ref_bbox"] = [[vb.xmin, vb.ymin], [vb.xmax, vb.ymax]]

        m["feature"] = taxonomy.normalize_feature(m.get("category", "drawing_views"), m.get("feature"))

    # Filter out Shim Table (シム表 / Shim Schedule) items as out of scope
    def _is_shim_table_item(item: dict) -> bool:
        t = (item.get("text_content") or "").lower()
        d = (item.get("details") or "").lower()
        o = (item.get("original_value") or "").lower()
        return "シム表" in t or "シム表" in d or "シム表" in o or "shim table" in t or "shim schedule" in t

    clean_markings = [m for m in clean_markings if not _is_shim_table_item(m)]

    parsed["canvas_markings"] = clean_markings


def build_physical_comparison_response(
    parsed: dict[str, Any],
    model_used: str,
    zone_detection_warnings: list[str] | None = None
) -> PhysicalComparisonResponse:
    """
    Constructs the final PhysicalComparisonResponse schema instance from parsed data.
    """
    return PhysicalComparisonResponse(
        drawing_views=CategoryComparison(**parsed["drawing_views"]),
        notes_section=CategoryComparison(**parsed["notes_section"]),
        bill_of_materials=CategoryComparison(**parsed["bill_of_materials"]),
        title_block=CategoryComparison(**parsed["title_block"]),
        isometric_view=CategoryComparison(**parsed["isometric_view"]),
        other_engineering_references=CategoryComparison(**parsed["other_engineering_references"]),
        canvas_markings=[CanvasMarking(**item) for item in parsed.get("canvas_markings", [])],
        diagnostics=ComparisonDiagnostics(
            model_used=model_used,
            zone_detection_warnings=zone_detection_warnings or [],
        ),
    )
