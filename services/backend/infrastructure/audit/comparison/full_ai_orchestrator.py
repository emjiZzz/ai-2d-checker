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
)
from ...storage.path_resolver import get_storage_root
from ...utils.text import extract_semantic_text_groups, build_title_block_table
from ..bom_analyzer import BOMAnalyzer
from ..context_builder import build_structured_context, load_drawing_png
from .revision_resolver import resolve_revisions
from .gemini_client import execute_gemini_cascade
from .cache_manager import ComparisonCacheManager


async def perform_full_ai_comparison(
    request,
    ref_drawing: DrawingDocument,
    rev_drawing: DrawingDocument,
    ref_entities: list,
    rev_entities: list,
    method: str = "full_ai",
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
    from ..bom.table_extractor import extract_dynamic_regions

    ref_regions = extract_dynamic_regions(ref_entities)
    rev_regions = extract_dynamic_regions(rev_entities)

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
    system_instruction = (
        "You are a senior CAD engineering auditor comparing two technical drawings: "
        "a REFERENCE drawing and a REVISION drawing. "
        "Your task is to perform a complete physical comparison across all checklist categories: "
        "drawing_views, notes_section, bill_of_materials, title_block, isometric_view, and "
        "other_engineering_references. "
        "For each category, determine the status (MATCHED, CHANGED, ADDED, REMOVED, or MISSING), "
        "write a concise difference_summary, list specific content in reference_content and "
        "revision_content (even when status is MATCHED — show what was verified), and list "
        "specific discrepancies in engineering_discrepancy_details. "
        "For canvas_markings, produce one entry per significant annotation or data item found "
        "in the drawings — including BOTH MATCHED items AND changed/added/removed ones. "
        "For MATCHED items: set status='MATCHED', use the EXACT text string as text_content "
        "(copy it verbatim from the drawing — e.g. dimension values, part numbers, notes text, "
        "Japanese characters), and populate category to match the checklist key. "
        "For CHANGED/ADDED/REMOVED items: set the correct status, use the revision drawing's "
        "exact text string as text_content. "
        "Produce at least one MATCHED canvas_marking per MATCHED category so each verified "
        "item gets a green checkmark on the drawing canvas. "
        "Be precise and thorough. Do not fabricate markings not present in the drawings."
    )

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
    if method == "full_ai_vision":
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
            f"=== REFERENCE GEOMETRY ANNOTATIONS (sample) ===\n"
            f"{ref_groups.get('geometry_annotations', '')[:3000]}\n\n"
            f"=== REVISION GEOMETRY ANNOTATIONS (sample) ===\n"
            f"{rev_groups.get('geometry_annotations', '')[:3000]}\n\n"
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
    raw_json_text = await asyncio.to_thread(
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

    comparison_response = PhysicalComparisonResponse(
        drawing_views=CategoryComparison(**parsed["drawing_views"]),
        notes_section=CategoryComparison(**parsed["notes_section"]),
        bill_of_materials=CategoryComparison(**parsed["bill_of_materials"]),
        title_block=CategoryComparison(**parsed["title_block"]),
        isometric_view=CategoryComparison(**parsed["isometric_view"]),
        other_engineering_references=CategoryComparison(**parsed["other_engineering_references"]),
        canvas_markings=[CanvasMarking(**item) for item in parsed.get("canvas_markings", [])],
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
                "comparison_method": "full_ai",
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
            method="full_ai",
        )
    except Exception as cache_write_err:
        logger.warning(f"[full_ai] Failed to cache comparison response: {cache_write_err}")

    return comparison_response
