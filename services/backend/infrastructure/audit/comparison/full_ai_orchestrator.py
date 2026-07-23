"""
full_ai_orchestrator.py — Full-AI drawing comparison orchestrator.

Parallel to perform_drawing_comparison() in orchestrator.py but routes the entire
comparison to Gemini instead of SpatialDiffer + BOMAnalyzer. Intended for dev
benchmarking (comparison_method="full_ai" on a Room) to compare outputs against
the deterministic pipeline side by side.

Gemini receives:
  - Both rendered drawing PNGs (from storage/renderings/)
  - build_structured_context() output for both ref and rev drawings
  - BOM rows extracted the same way as the deterministic pass
  - Title block text extracted the same way as the deterministic pass
  - response_schema=PhysicalComparisonResponse so it returns structured JSON directly

Canvas markings returned by Gemini will NOT go through the coordinate resolver
(that depends on SpatialDiffer intermediate data), but canvas_markings[].text_content
can be used by the frontend for text-search-based positioning.
"""

import asyncio
import json
import os
from datetime import datetime, UTC

from google.genai import types

from ....domain.models.audit_session import AuditSession
from ....domain.models.audit_violation import AuditViolation
from ....domain.models.drawing_document import DrawingDocument
from ....logger import logger
from ....config import settings
from ....api.schemas import (
    PhysicalComparisonResponse,
    CategoryComparison,
    CanvasMarking,
    ComparisonDiagnostics,
)
from ...storage.path_resolver import get_storage_root
from ...utils.text import extract_semantic_text_groups, build_title_block_table
from ..bom_analyzer import BOMAnalyzer
from ..context_builder import build_structured_context, load_drawing_png
from .revision_resolver import resolve_revisions
from .gemini_client import execute_gemini_cascade
from .cache_manager import ComparisonCacheManager
from .coordinate_resolver import resolve_marking_coordinates, harden_value_only_coordinates
from .schemas import Coordinate2D, BoundingBox2D
from .candidate import ComparisonCandidate
from . import taxonomy


def build_drawing_views_prompt_instructions() -> str:
    return (
        "=== CATEGORY: DRAWING VIEWS (Senior Industrial CAD Auditor Persona - ISO 128 / JIS B 0001) ===\n"
        "Evaluate `drawing_views` across all orthogonal, detail, and section views.\n"
        "Output a 4-column markdown table in `reference_content`: `Feature | Original Value | Revision Value | Status`.\n"
        "Must evaluate these 11 features strictly (feature keys in parentheses — use them verbatim as the `feature` value on any canvas_marking you tag under drawing_views, see the canvas_markings instructions below):\n"
        "1. Origin (origin): Evaluate datum reference lines (Base Datum Edge / Centerlines) and view origin placement. Do NOT output 'N/A' — report 'Datum Origin / Centerlines Aligned (Maintained)' if views match.\n"
        "2. Alignment of Views (alignment_of_views): Check orthographic projection alignment across front, top, side, and section views.\n"
        "3. Line Attributes (line_attributes): Check line types (hidden, center, solid, phantom, hatching).\n"
        "4. Dimensions (dimensions): Summarize dimensions broken down by drawing view (e.g. Main View: 140, 100, 15 | Section A-A: 170 +0/-0.1). Include dimensional fit tolerances.\n"
        "5. Hole Properties (hole_properties): Detail hole callouts, drill sizes (キリ), counterbores (ザグリ), and depth (深サ).\n"
        "6. Chamfer/Radius (chamfer_radius): Detail chamfers (C1, C2) and radii (R2, R3, R0.5), noting view additions (e.g., Reference: 2x R3, 1x R0.5 | Revision: R2, R4, R0.5 [Added Detail View]). Mark as CHANGED or ADDED as applicable.\n"
        "7. Machining Symbol (machining_symbol): Visually inspect the PNG renderings for surface-finish / machining marks (∇, √). This is a DIFFERENT symbol from Welding Symbol below — do not conflate the two.\n"
        "8. Welding Symbol (welding_symbol): Visually inspect the PNG renderings for graphical welding symbols (fillet △, bevel ∨). Extracted text takes precedence for numeric data; visual OCR takes precedence for graphical weld symbols.\n"
        "9. Geometric Tolerances (geometric_tolerances): Capture both GD&T feature control frames (⊕, ⊥, □) AND dimensional fit/limit tolerances (170 +0/-0.1, 15 +0/-0.05, ±0.02).\n"
        "10. Additional Views (additional_views): Report newly added or modified detail/section views (e.g., 油溝詳細 Oil groove detail).\n"
        "11. Text Attributes (text_attributes): Standard text font, height, and spacing.\n"
    )

def build_notes_prompt_instructions() -> str:
    return (
        "=== CATEGORY: NOTES SECTION ===\n"
        "Evaluate `notes_section` for standard notes, special manufacturing instructions, and heat treatment callouts.\n"
        "Output a 4-column markdown table in `reference_content`: `Feature | Original Value | Revision Value | Status`.\n"
        "Evaluate: standard notes, special notes.\n"
    )

def build_title_block_prompt_instructions() -> str:
    return (
        "=== CATEGORY: TITLE BLOCK ===\n"
        "Evaluate `title_block` metadata. Output a 4-column markdown table in `reference_content`: `Feature | Original Value | Revision Value | Status`.\n"
        "Must evaluate these 10 features (feature keys in parentheses — use them verbatim as the `feature` value on any canvas_marking you tag under title_block):\n"
        "1. Machine Name (machine_name): the product/machine title text.\n"
        "2. Line Name (line_name): there is no reliable signal for this field in these drawings — mark it 'N/A' / MATCHED rather than guessing at a value.\n"
        "3. Scale (scale)\n"
        "4. Designed (designed): the 'designed by' signee/date field.\n"
        "5. Drawn (drawn): the 'drawn by' signee/date field.\n"
        "6. Quantity (quantity)\n"
        "7. Job Number (job_number)\n"
        "8. Cross Reference Number (cross_reference_number)\n"
        "9. Previous Drawing Number (previous_drawing_number)\n"
        "10. Revision Code (revision_code): the amendment/correction mark, often labeled AMD. or 訂正符号 — mark 'N/A' / MATCHED if the drawing has no revision-code field at all rather than inventing one.\n"
    )

def build_isometric_prompt_instructions() -> str:
    return (
        "=== CATEGORY: ISOMETRIC VIEW ===\n"
        "Evaluate `isometric_view` (3D perspective representations usually placed in the corner).\n"
        "IMPORTANT: Isometric views often lack text labels in CAD context. Visually inspect the PNG renderings to verify if a 3D perspective representation exists before concluding it is missing.\n"
        "Output a 4-column markdown table in `reference_content`: `Feature | Original Value | Revision Value | Status`.\n"
        "Evaluate: orientation, scale, location.\n"
    )

def build_others_prompt_instructions() -> str:
    return (
        "=== CATEGORY: OTHER ENGINEERING REFERENCES ===\n"
        "Evaluate `other_engineering_references`. Output a 4-column markdown table in `reference_content`: `Feature | Original Value | Revision Value | Status`.\n"
        "Evaluate these 2 features (feature keys in parentheses): Tree View Properties / Link (tree_view_properties), Excel — Additional Information (excel_additional_info).\n"
    )

def build_categorization_discipline_instructions() -> str:
    return (
        "=== CATEGORIZATION DISCIPLINE (apply this before evaluating any category below) ===\n"
        "The six categories are mutually exclusive. Every annotation, dimension, or data item "
        "belongs to exactly ONE of them, based on where it physically is on the sheet and what "
        "it represents — never based on which category section you happen to be writing about.\n"
        "- `title_block`: ONLY the metadata block(s) — typically a bottom-right stamp (title, "
        "drawing number, scale, drawn/designed/checked/approved by, date) and/or a secondary "
        "upper-left admin block (unit no., part no., quantity, stock qty).\n"
        "- `bill_of_materials`: ONLY the parts/materials schedule table (item no., code, "
        "dimension, quantity, weight, material, remarks).\n"
        "- `isometric_view`: ONLY the 3D perspective representation, usually in its own "
        "dedicated box in a corner of the sheet.\n"
        "- `notes_section`: ONLY free-text manufacturing/process instructions and callouts "
        "(e.g. \"Tap and drill holes to be chamfered\") — not dimensions, not title block data.\n"
        "- `drawing_views`: the orthogonal/section/detail views and their dimensions, "
        "tolerances, hole callouts, and geometry — everything that is NOT part of the title "
        "block, BOM, isometric box, or notes text. Do not report a title block field, BOM row, "
        "or notes entry here just because it sits spatially near a view.\n"
        "- `other_engineering_references`: anything else (tree view properties, external "
        "links, Excel data) that doesn't fit the five categories above.\n"
        "If uncertain whether something is a title block field, BOM row, or notes entry versus "
        "a drawing_views annotation, prefer the more specific category over the catch-all "
        "drawing_views.\n"
    )

def _format_subview_breakdown(subviews: list, prefix: str) -> str:
    """Render detect_subviews() output as grounding text for the drawing_views prompt."""
    if not subviews:
        return f"{prefix}: No distinct sub-views detected — treat as a single Main View."
    lines = [f"{prefix}: {len(subviews)} sub-view(s) detected via deterministic anchor clustering:"]
    for sv in subviews:
        bbox = tuple(round(c, 1) for c in sv["bbox"])
        lines.append(f"  - \"{sv['label']}\" — bbox={bbox}")
    return "\n".join(lines)

def build_full_system_instruction() -> str:
    header = (
        "You are a Senior Industrial CAD Engineering Auditor performing a rigorous comparison between a REFERENCE drawing and a REVISION drawing.\n"
        "For each category (except bill_of_materials which uses its own format), you MUST provide a markdown table in `reference_content` with exactly 4 columns: `Feature | Original Value | Revision Value | Status`.\n"
        "CRITICAL: If a feature is not present in either drawing, mark it N/A / MATCHED in the table rather than omitting the row or inventing content.\n"
        "For each category, determine the overall status (MATCHED, CHANGED, ADDED, REMOVED, or MISSING), write a detailed summary report in `difference_summary`, output the 4-column table in `reference_content`, and write a professional suggestion in `engineering_discrepancy_details`.\n"
    )
    markings_instr = (
        "For canvas_markings, produce one entry per significant annotation or data item found in the drawings — including BOTH MATCHED items AND changed/added/removed ones.\n"
        "For MATCHED items: set status='MATCHED', use EXACT text string, and populate category.\n"
        "Produce at least one MATCHED canvas_marking per MATCHED category so each verified item gets a green checkmark on the drawing canvas.\n"
        "CRITICAL — mark VALUES, not labels: for title_block and bill_of_materials specifically, a canvas_marking must point at the actual DATA VALUE (e.g. the text \"45\", \"ZHR\", \"1/2\"), never at the static field-name LABEL next to it (e.g. \"Unit No.\", \"DRAWN\", \"SCALE\"). Field labels are template boilerplate — do not emit a canvas_marking for one just because it also appears unchanged in both drawings.\n"
        "Assign `category` strictly per the CATEGORIZATION DISCIPLINE section above — do not tag a title block field, BOM row, or notes entry as `drawing_views` just because it is spatially near a view.\n"
        "Assign a `feature` sub-item tag to every canvas_marking, using the feature key (the snake_case name in parentheses in each category's section above) that best matches what it is:\n"
        "  - drawing_views: origin, alignment_of_views, line_attributes, dimensions, hole_properties, chamfer_radius, machining_symbol, welding_symbol, geometric_tolerances, additional_views, text_attributes\n"
        "  - notes_section: standard_notes, special_notes\n"
        "  - bill_of_materials: material_type, material_specification, quantity, material_weight, ballooning, remarks, numbering_arrangement\n"
        "  - title_block: machine_name, line_name, scale, designed, drawn, quantity, job_number, cross_reference_number, previous_drawing_number, revision_code\n"
        "  - isometric_view: orientation, scale, location\n"
        "  - other_engineering_references: tree_view_properties, excel_additional_info\n"
        "If nothing in a category's list confidently matches, set feature='other' rather than guessing — never invent a feature key not listed above.\n"
        "IMPORTANT: Provide 'visual_bbox' [ymin, xmin, ymax, xmax] normalized 0-1000 for each canvas_marking.\n"
    )
    return "\n\n".join([
        header,
        build_categorization_discipline_instructions(),
        build_drawing_views_prompt_instructions(),
        build_notes_prompt_instructions(),
        build_title_block_prompt_instructions(),
        build_isometric_prompt_instructions(),
        build_others_prompt_instructions(),
        markings_instr
    ])


async def generate_ai_vision_candidates(
    ref_drawing: DrawingDocument,
    rev_drawing: DrawingDocument,
    ref_entities: list,
    rev_entities: list,
) -> tuple[list[ComparisonCandidate], str]:
    """
    Generator B (AI Vision): independent full-drawing scan using only the two rendered
    PNGs — no structured CAD context, no BOM/title tables in the prompt. Deliberately a
    separate function from perform_full_ai_comparison(), not a refactor of it: that
    function's `rag_ai` prompt path and its post-hoc BOM/title-block override both stay
    untouched (docs/hybrid-comparison-engine-implementation-plan.md, Phase 2 sections 1.4
    and 1.5) — `hybrid` never wants the rag_ai prompt, and its equivalent of the override
    is the general reconciliation step in Phase 3/4, not this generator overriding itself.

    Returns:
        candidates: raw AI Vision findings, each tagged origin="ai_vision". No BOM/title
            override applied here — unlike `rag_ai`/`ai_vision`, whatever Gemini says
            about those categories is returned as-is; reconciliation decides whether it's
            trusted once Generator A's candidates exist to compare against.
        model_used: which model in the Gemini cascade actually answered.
    """
    api_key = os.environ.get("GEMINI_API_KEY") or getattr(settings, "GEMINI_API_KEY", None)
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not configured.")

    ref_rev, rev_rev, ref_title, rev_title = resolve_revisions(
        ref_entities, rev_entities,
        ref_drawing.file_hash, rev_drawing.file_hash,
        ref_drawing.file_name, rev_drawing.file_name,
    )

    from ..bom.table_extractor import extract_dynamic_regions
    ref_regions = extract_dynamic_regions(ref_entities)
    rev_regions = extract_dynamic_regions(rev_entities)

    ref_png = load_drawing_png(str(ref_drawing.id))
    rev_png = load_drawing_png(str(rev_drawing.id))

    system_instruction = build_full_system_instruction()

    contents: list = []
    if ref_png:
        contents.append("The following image is the REFERENCE (old) drawing:")
        contents.append(types.Part.from_bytes(data=ref_png, mime_type="image/png"))
    else:
        logger.warning(f"[hybrid/gen_b] No PNG for reference drawing {ref_drawing.id} — text-only")

    if rev_png:
        contents.append("The following image is the REVISION (new) drawing:")
        contents.append(types.Part.from_bytes(data=rev_png, mime_type="image/png"))
    else:
        logger.warning(f"[hybrid/gen_b] No PNG for revision drawing {rev_drawing.id} — text-only")

    prompt_text = (
        f"=== REFERENCE DRAWING METADATA ===\n"
        f"File: {ref_drawing.file_name} | Title: {ref_title} | Rev: {ref_rev}\n\n"
        f"=== REVISION DRAWING METADATA ===\n"
        f"File: {rev_drawing.file_name} | Title: {rev_title} | Rev: {rev_rev}\n\n"
        "Perform a complete engineering comparison using ONLY the provided images. "
        "Return your findings as a structured JSON object matching the required schema."
    )
    contents.append(prompt_text)

    logger.info(
        f"[hybrid/gen_b] Dispatching AI Vision scan for "
        f"ref={ref_drawing.file_name} vs rev={rev_drawing.file_name}"
    )
    raw_json_text, model_used = await asyncio.to_thread(
        execute_gemini_cascade, api_key, system_instruction, contents
    )

    try:
        parsed = json.loads(raw_json_text)
    except json.JSONDecodeError as parse_err:
        logger.error(f"[hybrid/gen_b] Gemini returned non-JSON response: {parse_err}")
        raise RuntimeError(f"AI Vision generator: Gemini returned malformed JSON: {parse_err}")

    clean_markings = parsed.get("canvas_markings", [])

    # Region bboxes for the text/entity-handle coordinate resolver — same source as
    # perform_full_ai_comparison's, just fetched independently since this function
    # doesn't share that one's local variables.
    ref_title_bbox_raw = ref_regions.get("title")
    rev_title_bbox_raw = rev_regions.get("title")
    ref_notes_bbox_raw = ref_regions.get("notes")
    rev_notes_bbox_raw = rev_regions.get("notes")
    ref_iso_bbox_raw = ref_regions.get("iso")
    rev_iso_bbox_raw = rev_regions.get("iso")
    ref_title_ul_bbox_raw = ref_regions.get("title_upper_left")
    rev_title_ul_bbox_raw = rev_regions.get("title_upper_left")
    ref_views_bbox_raw = ref_regions.get("views")
    rev_views_bbox_raw = rev_regions.get("views")
    ref_bom_bbox_raw = ref_regions.get("bom")
    rev_bom_bbox_raw = rev_regions.get("bom")

    _to_bbox = lambda raw: BoundingBox2D.from_tuple(raw).to_tuple() if raw else None
    ref_title_bbox = _to_bbox(ref_title_bbox_raw)
    rev_title_bbox = _to_bbox(rev_title_bbox_raw)
    ref_notes_bbox = _to_bbox(ref_notes_bbox_raw)
    rev_notes_bbox = _to_bbox(rev_notes_bbox_raw)
    ref_iso_bbox = _to_bbox(ref_iso_bbox_raw)
    rev_iso_bbox = _to_bbox(rev_iso_bbox_raw)
    ref_views_bbox = _to_bbox(ref_views_bbox_raw)
    rev_views_bbox = _to_bbox(rev_views_bbox_raw)
    ref_title_ul_bbox = _to_bbox(ref_title_ul_bbox_raw)
    rev_title_ul_bbox = _to_bbox(rev_title_ul_bbox_raw)
    ref_bom_bbox_validated = _to_bbox(ref_bom_bbox_raw)
    rev_bom_bbox_validated = _to_bbox(rev_bom_bbox_raw)

    # BOM/title fields are needed here only as resolver input (text/row lookups for
    # matching a marking to an entity) — NOT as override ground truth. No override
    # happens in this generator; see the docstring above.
    ref_bounds_meta = ref_drawing.metadata.get("render_bounds") if ref_drawing.metadata else None
    rev_bounds_meta = rev_drawing.metadata.get("render_bounds") if rev_drawing.metadata else None
    ref_bom_rows, _ = BOMAnalyzer.extract_bom_table(ref_entities, render_bounds=ref_bounds_meta, bom_bbox=ref_bom_bbox_raw)
    rev_bom_rows, _ = BOMAnalyzer.extract_bom_table(rev_entities, render_bounds=rev_bounds_meta, bom_bbox=rev_bom_bbox_raw)
    ref_title_fields = BOMAnalyzer.extract_title_block(
        ref_entities, [e.properties.get("text", "") for e in ref_entities if getattr(e, "entity_type", "") == "text"]
    )
    rev_title_fields = BOMAnalyzer.extract_title_block(
        rev_entities, [e.properties.get("text", "") for e in rev_entities if getattr(e, "entity_type", "") == "text"]
    )

    id_to_rev_entity = {
        f"REV-{e.properties.get('handle')}": e for e in rev_entities if e.properties and e.properties.get("handle")
    }
    id_to_ref_entity = {
        f"REF-{e.properties.get('handle')}": e for e in ref_entities if e.properties and e.properties.get("handle")
    }
    used_rev_entities: set = set()
    used_ref_entities: set = set()

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
        logger.warning(f"[hybrid/gen_b] Coordinate resolution failed (non-fatal): {resolve_err}")

    # Snapshot right after the entity-handle resolver, before the visual-bbox fallback
    # below, so resolution_method can tell the two apart without resolve_marking_coordinates
    # itself needing to know about this hybrid-only concept.
    resolved_by_entity_handle = {id(m) for m in clean_markings if m.get("coordinates") is not None}

    def _visual_to_cad(visual_bbox: list[float], render_bounds: list[float]) -> list[float]:
        """Convert Gemini [ymin, xmin, ymax, xmax] (0–1000) to CAD [x, y] center point."""
        ymin_n, xmin_n, ymax_n, xmax_n = visual_bbox
        x_min_cad, y_min_cad, x_max_cad, y_max_cad = render_bounds
        cad_w = x_max_cad - x_min_cad
        cad_h = y_max_cad - y_min_cad
        x_frac = ((xmin_n + xmax_n) / 2.0) / 1000.0
        y_frac = ((ymin_n + ymax_n) / 2.0) / 1000.0
        x_cad = x_min_cad + (x_frac * cad_w)
        y_cad = y_min_cad + ((1.0 - y_frac) * cad_h)
        return [x_cad, y_cad]

    rev_render_bounds = rev_drawing.metadata.get("render_bounds") if rev_drawing.metadata else None
    ref_render_bounds = ref_drawing.metadata.get("render_bounds") if ref_drawing.metadata else None

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

    # Spatial dedup within this generator's own output only (Gemini can emit more than
    # one marking for the same real finding) — cross-generator reconciliation is a
    # separate step (Phase 3/4), not this function's job.
    import math
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
    if len(clean_markings) != len(deduped_markings):
        logger.info(f"[hybrid/gen_b] Spatial dedup: {len(clean_markings)} → {len(deduped_markings)} markings.")
    clean_markings = deduped_markings

    # Value-only-coordinate safety net (docs/checklist-taxonomy-grouping-implementation-
    # plan.md, Phase 7) — this generator's coordinates come from Gemini's visual_bbox
    # guess, steered only by a prompt instruction, not enforced, so this is the one path
    # where this check does real work rather than pure defense-in-depth.
    harden_value_only_coordinates(clean_markings, ref_entities, rev_entities)

    # DTO validation — same as perform_full_ai_comparison's tail.
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

    candidates: list[ComparisonCandidate] = []
    for m in clean_markings:
        m["origin"] = "ai_vision"
        if id(m) in resolved_by_entity_handle:
            m["resolution_method"] = "entity_handle"
        elif m.get("coordinates") is not None:
            m["resolution_method"] = "visual_bbox_fallback"
        else:
            m["resolution_method"] = "unresolved"
        # Gemini's raw `feature` guess is free text, not schema-constrained (see
        # markings_instr) — normalize against the canonical taxonomy so a near-miss
        # synonym or a category Gemini got wrong don't leak an unrecognized string
        # into ComparisonCandidate.
        m["feature"] = taxonomy.normalize_feature(m.get("category", "drawing_views"), m.get("feature"))
        try:
            candidates.append(ComparisonCandidate(**m))
        except Exception as candidate_err:
            logger.warning(f"[hybrid/gen_b] Dropping malformed AI Vision candidate ({candidate_err}): {m}")

    logger.info(f"[hybrid/gen_b] AI Vision scan produced {len(candidates)} candidates using model {model_used}.")
    return candidates, model_used


async def perform_full_ai_comparison(
    request,
    ref_drawing: DrawingDocument,
    rev_drawing: DrawingDocument,
    ref_entities: list,
    rev_entities: list,
    method: str = "rag_ai",
) -> PhysicalComparisonResponse:
    """
    Full-AI comparison pipeline: Gemini receives both drawings (PNG + structured
    CAD context) and performs the entire comparison without SpatialDiffer.

    Returns the same PhysicalComparisonResponse shape as perform_drawing_comparison()
    so the frontend rendering path is identical.
    """
    # ── Cache check ────────────────────────────────────────────────────────────
    cached_payload = ComparisonCacheManager.get_cached_comparison(
        ref_drawing_id=str(ref_drawing.id),
        rev_drawing_id=str(rev_drawing.id),
        ref_hash=ref_drawing.file_hash,
        rev_hash=rev_drawing.file_hash,
        method=method,
    )
    if cached_payload:
        try:
            return PhysicalComparisonResponse(
                drawing_views=CategoryComparison(**cached_payload["drawing_views"]),
                notes_section=CategoryComparison(**cached_payload["notes_section"]),
                bill_of_materials=CategoryComparison(**cached_payload["bill_of_materials"]),
                title_block=CategoryComparison(**cached_payload["title_block"]),
                isometric_view=CategoryComparison(**cached_payload["isometric_view"]),
                other_engineering_references=CategoryComparison(
                    **cached_payload["other_engineering_references"]
                ),
                canvas_markings=[
                    CanvasMarking(**item)
                    for item in cached_payload.get("canvas_markings", [])
                ],
                diagnostics=cached_payload.get("diagnostics"),
            )
        except Exception as cache_err:
            logger.warning(
                f"[full_ai] Failed to parse cached comparison, re-running: {cache_err}"
            )

    # ── API key ────────────────────────────────────────────────────────────────
    api_key = os.environ.get("GEMINI_API_KEY") or getattr(settings, "GEMINI_API_KEY", None)
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not configured.")

    # ── Resolve revision / title labels ───────────────────────────────────────
    ref_rev, rev_rev, ref_title, rev_title = resolve_revisions(
        ref_entities,
        rev_entities,
        ref_drawing.file_hash,
        rev_drawing.file_hash,
        ref_drawing.file_name,
        rev_drawing.file_name,
    )

    # ── Structured context (same builder as AIEngine) ─────────────────────────
    ref_ctx = build_structured_context(ref_entities, ref_drawing)
    rev_ctx = build_structured_context(rev_entities, rev_drawing)

    # ── BOM extraction (same as deterministic, just for context text) ─────────
    from ..bom.table_extractor import extract_dynamic_regions, summarize_zone_detection_confidence
    from ..bom.zone_detector import detect_subviews

    ref_regions = extract_dynamic_regions(ref_entities)
    rev_regions = extract_dynamic_regions(rev_entities)
    zone_detection_warnings = summarize_zone_detection_confidence(ref_regions, rev_regions)
    if zone_detection_warnings:
        logger.info(f"[full_ai] Zone detection confidence warnings: {zone_detection_warnings}")

    # ── Sub-view detection (Section A-A, Detail B, etc.) for prompt grounding ──
    ref_views_bbox_raw = ref_regions.get("views")
    rev_views_bbox_raw = rev_regions.get("views")
    ref_subviews = detect_subviews(ref_entities, views_bbox=ref_views_bbox_raw)
    rev_subviews = detect_subviews(rev_entities, views_bbox=rev_views_bbox_raw)
    logger.info(
        f"[full_ai] Sub-view detection — ref: {len(ref_subviews)} "
        f"({[sv['label'] for sv in ref_subviews]}), rev: {len(rev_subviews)} "
        f"({[sv['label'] for sv in rev_subviews]})"
    )

    ref_bom_bbox = ref_regions.get("bom")
    rev_bom_bbox = rev_regions.get("bom")

    ref_bounds_meta = ref_drawing.metadata.get("render_bounds") if ref_drawing.metadata else None
    rev_bounds_meta = rev_drawing.metadata.get("render_bounds") if rev_drawing.metadata else None

    ref_bom_rows, ref_is_assembly = BOMAnalyzer.extract_bom_table(
        ref_entities, render_bounds=ref_bounds_meta, bom_bbox=ref_bom_bbox
    )
    rev_bom_rows, rev_is_assembly = BOMAnalyzer.extract_bom_table(
        rev_entities, render_bounds=rev_bounds_meta, bom_bbox=rev_bom_bbox
    )
    is_assembly = ref_is_assembly or rev_is_assembly
    bom_table_text = BOMAnalyzer.build_bom_table(ref_bom_rows, rev_bom_rows, is_assembly)

    # ── Title block extraction ─────────────────────────────────────────────────
    ref_title_fields = BOMAnalyzer.extract_title_block(
        ref_entities,
        [e.properties.get("text", "") for e in ref_entities if getattr(e, "entity_type", "") == "text"],
    )
    rev_title_fields = BOMAnalyzer.extract_title_block(
        rev_entities,
        [e.properties.get("text", "") for e in rev_entities if getattr(e, "entity_type", "") == "text"],
    )
    title_block_table_text = build_title_block_table(ref_title_fields, rev_title_fields)

    # ── Semantic text groups for notes/geometry ────────────────────────────────
    ref_groups = extract_semantic_text_groups(ref_entities, prefix="REF")
    rev_groups = extract_semantic_text_groups(rev_entities, prefix="REV")

    # ── Load PNGs ─────────────────────────────────────────────────────────────
    ref_png = load_drawing_png(str(ref_drawing.id))
    rev_png = load_drawing_png(str(rev_drawing.id))

    # ── Assemble prompt ────────────────────────────────────────────────────────
    system_instruction = build_full_system_instruction()

    # Build contents list for Gemini multipart call
    contents: list = []

    # Reference drawing image
    if ref_png:
        contents.append("The following image is the REFERENCE (old) drawing:")
        contents.append(types.Part.from_bytes(data=ref_png, mime_type="image/png"))
    else:
        logger.warning(f"[full_ai] No PNG for reference drawing {ref_drawing.id} — text-only")

    # Revision drawing image
    if rev_png:
        contents.append("The following image is the REVISION (new) drawing:")
        contents.append(types.Part.from_bytes(data=rev_png, mime_type="image/png"))
    else:
        logger.warning(f"[full_ai] No PNG for revision drawing {rev_drawing.id} — text-only")

    # Build prompt_text dynamically based on method
    if method == "ai_vision":
        prompt_text = (
            f"=== REFERENCE DRAWING METADATA ===\n"
            f"File: {ref_drawing.file_name} | Title: {ref_title} | Rev: {ref_rev}\n\n"
            f"=== REVISION DRAWING METADATA ===\n"
            f"File: {rev_drawing.file_name} | Title: {rev_title} | Rev: {rev_rev}\n\n"
            "Perform a complete engineering comparison using ONLY the provided images. "
            "Return your findings as a structured JSON object matching the required schema."
        )
    else:
        prompt_text = (
            f"=== REFERENCE DRAWING METADATA ===\n"
            f"File: {ref_drawing.file_name} | Title: {ref_title} | Rev: {ref_rev}\n"
            f"{json.dumps(ref_ctx, indent=2)}\n\n"
            f"=== REVISION DRAWING METADATA ===\n"
            f"File: {rev_drawing.file_name} | Title: {rev_title} | Rev: {rev_rev}\n"
            f"{json.dumps(rev_ctx, indent=2)}\n\n"
            f"=== BILL OF MATERIALS COMPARISON TABLE ===\n"
            f"{bom_table_text or '(No BOM detected)'}\n\n"
            f"=== TITLE BLOCK COMPARISON TABLE ===\n"
            f"{title_block_table_text or '(No title block data)'}\n\n"
            f"=== REFERENCE MAIN DRAWING VIEW ANNOTATIONS ===\n"
            f"{ref_groups.get('geometry_annotations', '')[:3000]}\n\n"
            f"=== REVISION MAIN DRAWING VIEW ANNOTATIONS ===\n"
            f"{rev_groups.get('geometry_annotations', '')[:3000]}\n\n"
            f"=== REFERENCE DRAWING SUB-VIEW BREAKDOWN ===\n"
            f"{_format_subview_breakdown(ref_subviews, 'REF')}\n\n"
            f"=== REVISION DRAWING SUB-VIEW BREAKDOWN ===\n"
            f"{_format_subview_breakdown(rev_subviews, 'REV')}\n\n"
            f"=== REFERENCE NOTES ===\n"
            f"{ref_groups.get('notes_zone_text', '')[:2000]}\n\n"
            f"=== REVISION NOTES ===\n"
            f"{rev_groups.get('notes_zone_text', '')[:2000]}\n\n"
            "Perform a complete engineering comparison. "
            "Return your findings as a structured JSON object matching the required schema."
        )
    contents.append(prompt_text)

    # ── Call Gemini (in thread, same as deterministic OCR path) ───────────────
    logger.info(
        f"[full_ai] Dispatching Gemini cascade for "
        f"ref={ref_drawing.file_name} vs rev={rev_drawing.file_name}"
    )
    raw_json_text, model_used = await asyncio.to_thread(
        execute_gemini_cascade, api_key, system_instruction, contents
    )

    # ── Parse response ─────────────────────────────────────────────────────────
    try:
        parsed = json.loads(raw_json_text)
    except json.JSONDecodeError as parse_err:
        logger.error(f"[full_ai] Gemini returned non-JSON response: {parse_err}")
        raise RuntimeError(f"Full-AI comparison: Gemini returned malformed JSON: {parse_err}")

    # Ensure required top-level keys are present (Gemini may omit MATCHED categories)
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

    # ── Deterministic BOM Override ─────────────────────────────────────────────
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

    # ── Deterministic Title Block Override ──────────────────────────────────────
    # Same pattern as the BOM override above: title_block_table_text (built by
    # build_title_block_table via compare_values) is already deterministic, computed
    # from extracted title-block fields, and already handed to Gemini as grounding
    # context — but until now Gemini's own free-form title_block verdict went through
    # unchecked, same class of gap as the drawing_views dimension-symbol bug fixed
    # earlier. Title block is the next-best fit for a full override (unlike
    # drawing_views/notes_section/isometric_view, it has a clean per-field structured
    # ground truth already computed, not just unstructured text/geometry).
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

    # ── Coordinate resolution (bridge Full-AI to deterministic-quality coords) ─
    clean_markings = parsed["canvas_markings"]

    # Downgrade hallucinated ADDED/REMOVED pins in BOM if the table is just CHANGED
    if bom_status == "CHANGED":
        for m in clean_markings:
            if m.get("category") == "bill_of_materials" and m.get("status") in ("ADDED", "REMOVED"):
                m["status"] = "CHANGED"

    # Same downgrade for title_block
    if title_status == "CHANGED":
        for m in clean_markings:
            if m.get("category") == "title_block" and m.get("status") in ("ADDED", "REMOVED"):
                m["status"] = "CHANGED"

    # 1. Extract all region bounding boxes (same as deterministic path)
    ref_title_bbox_raw = ref_regions.get("title")
    rev_title_bbox_raw = rev_regions.get("title")
    ref_notes_bbox_raw = ref_regions.get("notes")
    rev_notes_bbox_raw = rev_regions.get("notes")
    ref_iso_bbox_raw = ref_regions.get("iso")
    rev_iso_bbox_raw = rev_regions.get("iso")
    ref_title_ul_bbox_raw = ref_regions.get("title_upper_left")
    rev_title_ul_bbox_raw = rev_regions.get("title_upper_left")
    ref_tolerance_bbox_raw = ref_regions.get("tolerance")
    rev_tolerance_bbox_raw = rev_regions.get("tolerance")

    _to_bbox = lambda raw: BoundingBox2D.from_tuple(raw).to_tuple() if raw else None
    ref_title_bbox = _to_bbox(ref_title_bbox_raw)
    rev_title_bbox = _to_bbox(rev_title_bbox_raw)
    ref_notes_bbox = _to_bbox(ref_notes_bbox_raw)
    rev_notes_bbox = _to_bbox(rev_notes_bbox_raw)
    ref_iso_bbox = _to_bbox(ref_iso_bbox_raw)
    rev_iso_bbox = _to_bbox(rev_iso_bbox_raw)
    ref_views_bbox = _to_bbox(ref_views_bbox_raw)
    rev_views_bbox = _to_bbox(rev_views_bbox_raw)
    ref_title_ul_bbox = _to_bbox(ref_title_ul_bbox_raw)
    rev_title_ul_bbox = _to_bbox(rev_title_ul_bbox_raw)
    ref_tolerance_bbox = _to_bbox(ref_tolerance_bbox_raw)
    rev_tolerance_bbox = _to_bbox(rev_tolerance_bbox_raw)
    ref_bom_bbox_validated = _to_bbox(ref_bom_bbox)
    rev_bom_bbox_validated = _to_bbox(rev_bom_bbox)

    # 2. Build entity ID lookup dictionaries for coordinate resolution
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

    # 3. Run text-based coordinate resolution (same resolver as deterministic)
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
        resolved_count = sum(1 for m in clean_markings if m.get("coordinates"))
        logger.info(
            f"[full_ai] Text-based coordinate resolution: "
            f"{resolved_count}/{len(clean_markings)} markings resolved."
        )
    except Exception as resolve_err:
        logger.warning(f"[full_ai] Coordinate resolution failed (non-fatal): {resolve_err}")

    # 4. Visual coordinate fallback — convert Gemini normalized [ymin,xmin,ymax,xmax]/1000
    #    to CAD world coordinates for any markings still missing coordinates.
    def _visual_to_cad(visual_bbox: list[float], render_bounds: list[float]) -> list[float]:
        """Convert Gemini [ymin, xmin, ymax, xmax] (0–1000) to CAD [x, y] center point."""
        ymin_n, xmin_n, ymax_n, xmax_n = visual_bbox
        x_min_cad, y_min_cad, x_max_cad, y_max_cad = render_bounds
        cad_w = x_max_cad - x_min_cad
        cad_h = y_max_cad - y_min_cad
        # Center of the visual bbox
        x_frac = ((xmin_n + xmax_n) / 2.0) / 1000.0
        y_frac = ((ymin_n + ymax_n) / 2.0) / 1000.0
        # Y-inversion: Gemini image origin is top-left, CAD origin is bottom-left
        x_cad = x_min_cad + (x_frac * cad_w)
        y_cad = y_min_cad + ((1.0 - y_frac) * cad_h)
        return [x_cad, y_cad]

    rev_render_bounds = rev_drawing.metadata.get("render_bounds") if rev_drawing.metadata else None
    ref_render_bounds = ref_drawing.metadata.get("render_bounds") if ref_drawing.metadata else None

    visual_fallback_count = 0
    for m in clean_markings:
        # Revision coordinates fallback
        if m.get("coordinates") is None and m.get("visual_bbox") and rev_render_bounds:
            try:
                m["coordinates"] = _visual_to_cad(m["visual_bbox"], rev_render_bounds)
                visual_fallback_count += 1
            except Exception:
                pass
        # Reference coordinates fallback
        if m.get("ref_coordinates") is None and m.get("ref_visual_bbox") and ref_render_bounds:
            try:
                m["ref_coordinates"] = _visual_to_cad(m["ref_visual_bbox"], ref_render_bounds)
                visual_fallback_count += 1
            except Exception:
                pass

    if visual_fallback_count > 0:
        logger.info(f"[full_ai] Visual coordinate fallback resolved {visual_fallback_count} additional coordinate(s).")

    # 4.5 Bbox-aware visual overwrite — map CAD bbox back to normalized visual_bbox
    def _cad_to_visual(cad_bbox: list[float], render_bounds: list[float]) -> list[float]:
        """Convert CAD [xmin, ymin, xmax, ymax] to Gemini [ymin, xmin, ymax, xmax] (0–1000)."""
        xmin_cad, ymin_cad, xmax_cad, ymax_cad = cad_bbox
        x_min_bound, y_min_bound, x_max_bound, y_max_bound = render_bounds
        cad_w = x_max_bound - x_min_bound
        cad_h = y_max_bound - y_min_bound
        
        if cad_w == 0 or cad_h == 0: return None
        
        xmin_n = max(0.0, min(1000.0, ((xmin_cad - x_min_bound) / cad_w) * 1000.0))
        xmax_n = max(0.0, min(1000.0, ((xmax_cad - x_min_bound) / cad_w) * 1000.0))
        
        # Y-inversion
        ymax_n = max(0.0, min(1000.0, (1.0 - (ymin_cad - y_min_bound) / cad_h) * 1000.0))
        ymin_n = max(0.0, min(1000.0, (1.0 - (ymax_cad - y_min_bound) / cad_h) * 1000.0))
        
        return [int(ymin_n), int(xmin_n), int(ymax_n), int(xmax_n)]

    for m in clean_markings:
        if m.get("bbox") and rev_render_bounds:
            try:
                if len(m["bbox"]) == 2 and len(m["bbox"][0]) == 2:
                    flat_bbox = [m["bbox"][0][0], m["bbox"][0][1], m["bbox"][1][0], m["bbox"][1][1]]
                    mapped_vbbox = _cad_to_visual(flat_bbox, rev_render_bounds)
                    if mapped_vbbox:
                        m["visual_bbox"] = mapped_vbbox
            except Exception:
                pass
        if m.get("ref_bbox") and ref_render_bounds:
            try:
                if len(m["ref_bbox"]) == 2 and len(m["ref_bbox"][0]) == 2:
                    flat_bbox = [m["ref_bbox"][0][0], m["ref_bbox"][0][1], m["ref_bbox"][1][0], m["ref_bbox"][1][1]]
                    mapped_vbbox = _cad_to_visual(flat_bbox, ref_render_bounds)
                    if mapped_vbbox:
                        m["ref_visual_bbox"] = mapped_vbbox
            except Exception:
                pass

    # 5. Spatial deduplication — merge markings within 5mm CAD distance threshold
    import math
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
                        # Merge: keep the one with more detail
                        if len(m.get("details", "")) > len(existing.get("details", "")):
                            existing.update(m)
                        is_duplicate = True
                        break
        if not is_duplicate:
            deduped_markings.append(m)

    if len(clean_markings) != len(deduped_markings):
        logger.info(f"[full_ai] Spatial dedup: {len(clean_markings)} → {len(deduped_markings)} markings.")
    clean_markings = deduped_markings

    # Value-only-coordinate safety net (docs/checklist-taxonomy-grouping-implementation-
    # plan.md, Phase 7) — same rationale as generate_ai_vision_candidates above: this
    # `rag_ai`/`ai_vision` path's title_block/BOM markings can also come from Gemini's
    # visual_bbox guess (deterministic override only applies to the category-level
    # status/table, not every individual canvas_marking's coordinates), so this is real
    # coverage here too, not pure defense-in-depth.
    harden_value_only_coordinates(clean_markings, ref_entities, rev_entities)

    # 6. Validate coordinates and bounding boxes via DTO constraints
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
        # Gemini's raw `feature` guess is free text, not schema-constrained (see
        # markings_instr) — normalize against the canonical taxonomy so a near-miss
        # synonym or a category Gemini got wrong don't leak an unrecognized string
        # into CanvasMarking.
        m["feature"] = taxonomy.normalize_feature(m.get("category", "drawing_views"), m.get("feature"))

    parsed["canvas_markings"] = clean_markings

    comparison_response = PhysicalComparisonResponse(
        drawing_views=CategoryComparison(**parsed["drawing_views"]),
        notes_section=CategoryComparison(**parsed["notes_section"]),
        bill_of_materials=CategoryComparison(**parsed["bill_of_materials"]),
        title_block=CategoryComparison(**parsed["title_block"]),
        isometric_view=CategoryComparison(**parsed["isometric_view"]),
        other_engineering_references=CategoryComparison(**parsed["other_engineering_references"]),
        canvas_markings=[CanvasMarking(**item) for item in parsed.get("canvas_markings", [])],
        diagnostics=ComparisonDiagnostics(
            model_used=model_used,
            zone_detection_warnings=zone_detection_warnings,
        ),
    )

    logger.info(
        f"[full_ai] Comparison complete — "
        f"categories: drawing_views={parsed['drawing_views']['status']}, "
        f"notes_section={parsed['notes_section']['status']}, "
        f"bill_of_materials={parsed['bill_of_materials']['status']}, "
        f"title_block={parsed['title_block']['status']}, "
        f"canvas_markings={len(parsed.get('canvas_markings', []))}"
    )

    # ── Persist AuditSession + violations ─────────────────────────────────────
    try:
        canvas_markings_raw = parsed.get("canvas_markings", [])
        non_matched = [m for m in canvas_markings_raw if m.get("status") != "MATCHED"]
        total_markings = len(canvas_markings_raw)
        matched_count = total_markings - len(non_matched)
        comparison_score = (
            round((matched_count / total_markings) * 100, 2) if total_markings > 0 else 100.0
        )

        comparison_session = AuditSession(
            drawing_id=str(rev_drawing.id),
            reference_drawing_id=str(ref_drawing.id),
            standard_id=None,
            client_name=None,
            status="completed",
            compliance_score=comparison_score,
            confidence_score=0.80,  # lower than deterministic — LLM has inherent uncertainty
            timings={},
            diagnostics={
                "source": "physical_comparison",
                "comparison_method": method,
                "total_markings": total_markings,
                "non_matched": len(non_matched),
                "ref_png_used": ref_png is not None,
                "rev_png_used": rev_png is not None,
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
                    if len(marking.coordinates) > 0 and not isinstance(
                        marking.coordinates[0], list
                    ):
                        coords = [marking.coordinates]
                    else:
                        coords = marking.coordinates

            violations_to_save.append(
                AuditViolation(
                    audit_session_id=str(comparison_session.id),
                    severity=SEVERITY_MAP.get(marking.status, "medium"),
                    category=f"comparison_{marking.category}",
                    description=f"[{marking.status}] {marking.details}",
                    recommendation=(
                        f"Resolve discrepancy in '{marking.text_content}' against the reference drawing."
                    ),
                    source="full_ai_comparison",
                    confidence=0.80,
                    standard_reference=None,
                    affected_entities=(
                        [{"entity_id": marking.entity_id, "marker_shape": "BOX"}]
                        if marking.entity_id
                        else []
                    ),
                    coordinates=coords,
                )
            )

        if violations_to_save:
            await AuditViolation.insert_many(violations_to_save)

        logger.info(
            f"[full_ai] Persisted {len(violations_to_save)} violations "
            f"(session {comparison_session.id}, score {comparison_score}%)."
        )
    except Exception as persist_err:
        logger.warning(f"[full_ai] Violation persistence failed (non-fatal): {persist_err}")

    # ── Write to cache ─────────────────────────────────────────────────────────
    try:
        ComparisonCacheManager.set_cached_comparison(
            ref_drawing_id=str(ref_drawing.id),
            rev_drawing_id=str(rev_drawing.id),
            ref_hash=ref_drawing.file_hash,
            rev_hash=rev_drawing.file_hash,
            payload=comparison_response.model_dump(),
            method=method,
        )
    except Exception as cache_write_err:
        logger.warning(f"[full_ai] Failed to cache comparison response: {cache_write_err}")

    return comparison_response
