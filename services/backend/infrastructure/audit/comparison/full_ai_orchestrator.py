"""
full_ai_orchestrator.py — Full-AI drawing comparison orchestrator facade.

Parallel to perform_drawing_comparison() in orchestrator.py but routes the entire
comparison to Gemini instead of SpatialDiffer + BOMAnalyzer. Intended for dev
benchmarking (comparison_method="full_ai" on a Room) to compare outputs side by side.
"""

import asyncio
import json
import os
from typing import Any

from google.genai import types

from ....api.schemas import PhysicalComparisonResponse
from ....config import settings
from ....domain.models.drawing_document import DrawingDocument
from ....logger import logger
from ..context_builder import build_structured_context, load_drawing_png
from ...utils.text import build_title_block_table, extract_semantic_text_groups
from ..bom_analyzer import BOMAnalyzer
from .candidate import ComparisonCandidate
from .cache_manager import ComparisonCacheManager
from .full_ai.persistence_handler import FullAIPersistenceHandler
from .full_ai.prompt_builder import (
    build_full_system_instruction,
    build_multimodal_contents,
    format_subview_breakdown,
)
from .full_ai.result_parser import (
    apply_deterministic_overrides,
    build_physical_comparison_response,
    parse_and_normalize_gemini_json,
    resolve_and_harden_coordinates,
)
from .gemini_client import execute_gemini_cascade
from .revision_resolver import resolve_revisions


async def generate_ai_vision_candidates(
    ref_drawing: DrawingDocument,
    rev_drawing: DrawingDocument,
    ref_entities: list,
    rev_entities: list,
) -> tuple[list[ComparisonCandidate], str]:
    """
    Generator B (AI Vision): independent full-drawing scan using only the two rendered
    PNGs — no structured CAD context, no BOM/title tables in the prompt.
    Returns raw AI Vision candidates tagged origin="ai_vision".
    """
    api_key = os.environ.get("GEMINI_API_KEY") or getattr(settings, "GEMINI_API_KEY", None)
    openai_key = os.environ.get("OPENAI_API_KEY") or getattr(settings, "OPENAI_API_KEY", None)
    if not api_key and not openai_key:
        raise ValueError("Neither GEMINI_API_KEY nor OPENAI_API_KEY is configured.")

    ref_rev, rev_rev, ref_title, rev_title = resolve_revisions(
        ref_entities, rev_entities,
        ref_drawing.file_hash, rev_drawing.file_hash,
        ref_drawing.file_name, rev_drawing.file_name,
    )

    from ..bom.table_extractor import extract_dynamic_regions
    ref_regions = extract_dynamic_regions(ref_entities)
    rev_regions = extract_dynamic_regions(rev_entities)

    system_instruction = build_full_system_instruction()
    prompt_text = (
        f"=== REFERENCE DRAWING METADATA ===\n"
        f"File: {ref_drawing.file_name} | Title: {ref_title} | Rev: {ref_rev}\n\n"
        f"=== REVISION DRAWING METADATA ===\n"
        f"File: {rev_drawing.file_name} | Title: {rev_title} | Rev: {rev_rev}\n\n"
        "Perform a complete engineering comparison using ONLY the provided images. "
        "Return your findings as a structured JSON object matching the required schema."
    )
    contents = build_multimodal_contents(ref_drawing, rev_drawing, prompt_text)

    logger.info(
        f"[hybrid/gen_b] Dispatching AI Vision scan for "
        f"ref={ref_drawing.file_name} vs rev={rev_drawing.file_name}"
    )
    raw_json_text, model_used = await asyncio.to_thread(
        execute_gemini_cascade, api_key, system_instruction, contents
    )

    parsed = parse_and_normalize_gemini_json(raw_json_text)
    clean_markings = parsed.get("canvas_markings", [])

    ref_bounds_meta = ref_drawing.metadata.get("render_bounds") if ref_drawing.metadata else None
    rev_bounds_meta = rev_drawing.metadata.get("render_bounds") if rev_drawing.metadata else None
    ref_bom_rows, _ = BOMAnalyzer.extract_bom_table(ref_entities, render_bounds=ref_bounds_meta, bom_bbox=ref_regions.get("bom"))
    rev_bom_rows, _ = BOMAnalyzer.extract_bom_table(rev_entities, render_bounds=rev_bounds_meta, bom_bbox=rev_regions.get("bom"))
    ref_title_fields = BOMAnalyzer.extract_title_block(
        ref_entities, [e.properties.get("text", "") for e in ref_entities if getattr(e, "entity_type", "") == "text"]
    )
    rev_title_fields = BOMAnalyzer.extract_title_block(
        rev_entities, [e.properties.get("text", "") for e in rev_entities if getattr(e, "entity_type", "") == "text"]
    )

    resolve_and_harden_coordinates(
        parsed, ref_drawing, rev_drawing, ref_entities, rev_entities,
        ref_regions, rev_regions, ref_bom_rows, rev_bom_rows,
        ref_title_fields, rev_title_fields
    )

    candidates = [
        ComparisonCandidate.from_canvas_marking(dict(m), origin="ai_vision")
        for m in parsed.get("canvas_markings", [])
    ]
    return candidates, model_used


async def perform_full_ai_comparison(
    request: Any,
    ref_drawing: DrawingDocument,
    rev_drawing: DrawingDocument,
    ref_entities: list,
    rev_entities: list,
    method: str = "rag_ai",
) -> PhysicalComparisonResponse:
    """
    Executes full AI drawing comparison pipeline.
    Facilitates caching, prompt assembly, Gemini invocation, result parsing, and session persistence.
    """
    api_key = os.environ.get("GEMINI_API_KEY") or getattr(settings, "GEMINI_API_KEY", None)
    openai_key = os.environ.get("OPENAI_API_KEY") or getattr(settings, "OPENAI_API_KEY", None)
    if not api_key and not openai_key:
        raise ValueError("Neither GEMINI_API_KEY nor OPENAI_API_KEY is configured inside system environment.")

    # 1. Check cache
    cached = ComparisonCacheManager.get_cached_comparison(
        ref_drawing_id=str(ref_drawing.id),
        rev_drawing_id=str(rev_drawing.id),
        ref_hash=ref_drawing.file_hash,
        rev_hash=rev_drawing.file_hash,
        method=method,
    )
    if cached:
        logger.info(f"[full_ai] Cache hit for ref={ref_drawing.id} vs rev={rev_drawing.id} (method={method})")
        return PhysicalComparisonResponse(**cached)

    # 2. Extract metadata & CAD context
    ref_rev, rev_rev, ref_title, rev_title = resolve_revisions(
        ref_entities, rev_entities,
        ref_drawing.file_hash, rev_drawing.file_hash,
        ref_drawing.file_name, rev_drawing.file_name,
    )

    ref_ctx = build_structured_context(ref_entities, ref_drawing)
    rev_ctx = build_structured_context(rev_entities, rev_drawing)

    from ..bom.table_extractor import extract_dynamic_regions, summarize_zone_detection_confidence
    from ..bom.zone_detector import detect_subviews

    ref_regions = extract_dynamic_regions(ref_entities)
    rev_regions = extract_dynamic_regions(rev_entities)
    zone_detection_warnings = summarize_zone_detection_confidence(ref_regions, rev_regions)

    ref_subviews = detect_subviews(ref_entities, views_bbox=ref_regions.get("views"))
    rev_subviews = detect_subviews(rev_entities, views_bbox=rev_regions.get("views"))

    ref_bounds_meta = ref_drawing.metadata.get("render_bounds") if ref_drawing.metadata else None
    rev_bounds_meta = rev_drawing.metadata.get("render_bounds") if rev_drawing.metadata else None

    ref_bom_rows, ref_is_assembly = BOMAnalyzer.extract_bom_table(
        ref_entities, render_bounds=ref_bounds_meta, bom_bbox=ref_regions.get("bom")
    )
    rev_bom_rows, rev_is_assembly = BOMAnalyzer.extract_bom_table(
        rev_entities, render_bounds=rev_bounds_meta, bom_bbox=rev_regions.get("bom")
    )
    bom_table_text = BOMAnalyzer.build_bom_table(ref_bom_rows, rev_bom_rows, ref_is_assembly or rev_is_assembly)

    ref_title_fields = BOMAnalyzer.extract_title_block(
        ref_entities, [e.properties.get("text", "") for e in ref_entities if getattr(e, "entity_type", "") == "text"]
    )
    rev_title_fields = BOMAnalyzer.extract_title_block(
        rev_entities, [e.properties.get("text", "") for e in rev_entities if getattr(e, "entity_type", "") == "text"]
    )
    title_block_table_text = build_title_block_table(ref_title_fields, rev_title_fields)

    ref_groups = extract_semantic_text_groups(ref_entities, prefix="REF")
    rev_groups = extract_semantic_text_groups(rev_entities, prefix="REV")

    # 3. Assemble Prompt & Execute Gemini Cascade
    system_instruction = build_full_system_instruction()

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
            f"{format_subview_breakdown(ref_subviews, 'REF')}\n\n"
            f"=== REVISION DRAWING SUB-VIEW BREAKDOWN ===\n"
            f"{format_subview_breakdown(rev_subviews, 'REV')}\n\n"
            f"=== REFERENCE NOTES ===\n"
            f"{ref_groups.get('notes_zone_text', '')[:2000]}\n\n"
            f"=== REVISION NOTES ===\n"
            f"{rev_groups.get('notes_zone_text', '')[:2000]}\n\n"
            "Perform a complete engineering comparison. "
            "Return your findings as a structured JSON object matching the required schema."
        )

    contents = build_multimodal_contents(ref_drawing, rev_drawing, prompt_text)

    logger.info(f"[full_ai] Dispatching Gemini cascade for ref={ref_drawing.file_name} vs rev={rev_drawing.file_name}")
    raw_json_text, model_used = await asyncio.to_thread(
        execute_gemini_cascade, api_key, system_instruction, contents
    )

    # 4. Parse JSON & Apply Overrides
    parsed = parse_and_normalize_gemini_json(raw_json_text)
    apply_deterministic_overrides(parsed, bom_table_text, title_block_table_text)

    # 5. Resolve Coordinates
    resolve_and_harden_coordinates(
        parsed, ref_drawing, rev_drawing, ref_entities, rev_entities,
        ref_regions, rev_regions, ref_bom_rows, rev_bom_rows,
        ref_title_fields, rev_title_fields
    )

    comparison_response = build_physical_comparison_response(parsed, model_used, zone_detection_warnings)

    # 6. Persist session & write cache
    ref_png = load_drawing_png(str(ref_drawing.id))
    rev_png = load_drawing_png(str(rev_drawing.id))
    await FullAIPersistenceHandler.persist_audit_results(
        ref_drawing=ref_drawing,
        rev_drawing=rev_drawing,
        parsed_data=parsed,
        comparison_response=comparison_response,
        method=method,
        ref_png_used=ref_png is not None,
        rev_png_used=rev_png is not None,
    )

    return comparison_response
