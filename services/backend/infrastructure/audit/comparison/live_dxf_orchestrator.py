"""
live_dxf_orchestrator.py — Dedicated Live Real-DXF AI Comparison Orchestrator.

Executed when comparison_method == "ai_vision".
Operates directly on physical .dxf drawing files on disk (resolving paths via get_storage_root()).
Performs live ezdxf parsing on the fly without relying on pre-ingested MongoDB ExtractedEntity models
or pre-rendered PNG images.
"""

import asyncio
import json
import os
from pathlib import Path
from typing import Any

from ....api.schemas import PhysicalComparisonResponse
from ....config import settings
from ....domain.models.drawing_document import DrawingDocument
from ....logger import logger
from ...cad.oda_converter import ODAConverter
from ...cad.dxf_parser import DXFParser
from ...storage.path_resolver import get_storage_root
from ..bom.table_extractor import extract_dynamic_regions, extract_dynamic_regions_async, summarize_zone_detection_confidence
from ..bom.zone_detector import detect_subviews
from ..bom_analyzer import BOMAnalyzer
from ..context_builder import build_structured_context, load_drawing_png
from ...utils.text import build_title_block_table, extract_semantic_text_groups, safe_decode, strip_mtext
from .cache_manager import ComparisonCacheManager
from .candidate import ComparisonCandidate
from .marking_builder import (
    inject_title_block_markings,
    inject_bom_markings,
    inject_ballooning_markings,
    generate_auto_matched_markings,
)
from .full_ai.persistence_handler import FullAIPersistenceHandler
from .full_ai.prompt_builder import (
    build_full_system_instruction,
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


async def resolve_physical_dxf_path(drawing: DrawingDocument) -> tuple[Path, bool]:
    """
    Resolves the physical .dxf file path on disk for a DrawingDocument.
    If the file is DWG, performs a live sandboxed conversion to a temporary DXF on disk.
    Returns (dxf_path, is_temporary).
    """
    storage_root = get_storage_root()
    relative_path = Path(drawing.file_path)
    abs_path = storage_root / relative_path

    if not abs_path.exists():
        raise FileNotFoundError(f"Physical drawing file not found on disk: {abs_path}")

    fmt = (drawing.format or abs_path.suffix.lstrip(".")).lower()

    if fmt == "dwg":
        logger.info(f"[live_dxf] Executing live DWG->DXF conversion for {drawing.file_name}")
        converter = ODAConverter()
        temp_dir = storage_root / "temp"
        temp_dir.mkdir(parents=True, exist_ok=True)
        dxf_path = await converter.convert_dwg_to_dxf(abs_path, temp_dir)
        return dxf_path, True
    elif fmt == "dxf":
        return abs_path, False
    else:
        # Fallback for PDF or other formats: if DXF file exists in storage root, use it
        dxf_candidate = abs_path.with_suffix(".dxf")
        if dxf_candidate.exists():
            return dxf_candidate, False
        return abs_path, False


def parse_live_dxf_file(dxf_path: Path) -> tuple[list[Any], dict[str, Any]]:
    """
    Performs on-the-fly live parsing of a physical .dxf file using DXFParser (ezdxf).
    Returns (entities, metadata).
    """
    logger.info(f"[live_dxf] Parsing physical .dxf file live from disk: {dxf_path.name}")
    parser = DXFParser()
    entities_dict, layers, counts, metadata = parser.parse_file(dxf_path)
    
    # Convert entity dicts to lightweight ExtractedEntity-like objects or dicts for context extraction
    # The context builder and BOM analyzer accept entity dicts or objects with properties dict
    class LiveEntityWrapper:
        def __init__(self, data: dict):
            self._data = data
            self.id = str(data.get("entity_id") or data.get("handle") or "")
            self.handle = self.id
            self.entity_type = str(data.get("entity_type") or data.get("type", "unknown")).lower()
            self.layer = str(data.get("layer", "0"))
            self.properties = data.get("properties") if isinstance(data.get("properties"), dict) else data
            self.geometry = data.get("geometry") if isinstance(data.get("geometry"), dict) else {}
            self.bounding_box = data.get("bounding_box") if isinstance(data.get("bounding_box"), dict) else {}

        def __getitem__(self, item: str):
            if item in ("id", "handle", "entity_type", "layer", "properties", "geometry", "bounding_box"):
                return getattr(self, item)
            return self._data.get(item)

        def get(self, item: str, default: Any = None):
            res = self.__getitem__(item)
            return res if res is not None else default

    wrapped_entities = [LiveEntityWrapper(e) for e in entities_dict]
    return wrapped_entities, metadata


def build_clean_dxf_manifest(entities: list, metadata: dict) -> str:
    """
    Extracts all text-bearing entities, callouts, dimensions, title block attributes,
    and layer breakdowns into a clean, concise DXF text manifest for AI reasoning.
    Omits raw line/arc vertex numbers to keep prompt compact and ultra-fast.
    """
    lines = []
    lines.append(f"Header Title: {metadata.get('title', 'N/A')} | Encoding: {metadata.get('encoding', 'N/A')}")
    
    text_items = []
    dim_items = []
    other_items = []

    for e in entities:
        etype = getattr(e, "entity_type", "").lower()
        handle = getattr(e, "handle", getattr(e, "id", ""))
        props = getattr(e, "properties", {}) or {}
        layer = getattr(e, "layer", "0")

        raw_text = props.get("text") or props.get("value") or ""
        if raw_text:
            text_val = strip_mtext(safe_decode(raw_text), convert_symbols=True)
            item_str = f"[{handle}] (Layer: {layer}, Type: {etype.upper()}): {text_val}"
            if etype in ("text", "mtext", "attrib"):
                text_items.append(item_str)
            elif etype == "dimension":
                dim_items.append(item_str)
            else:
                other_items.append(item_str)

    lines.append(f"--- TEXT & ANNOTATION ENTITIES ({len(text_items)} items) ---")
    lines.extend(text_items[:300])

    lines.append(f"\n--- DIMENSION CALLOUTS ({len(dim_items)} items) ---")
    lines.extend(dim_items[:200])

    if other_items:
        lines.append(f"\n--- OTHER CALLOUTS & ATTRIBUTES ({len(other_items)} items) ---")
        lines.extend(other_items[:100])

    return "\n".join(lines)


def reconcile_reference_drawing_values(clean_markings: list[dict], ref_entities: list) -> None:
    """
    Spatially and contextually matches reference entities to clean_markings.
    Prevents false-positive matches for short/ambiguous strings (like "1" or "0")
    by enforcing 2D spatial proximity bounds and nearest spatial neighbor selection.
    """
    import math
    from .coordinate_resolver import calc_anchor

    for m in clean_markings:
        orig = str(m.get("original_value") or "").strip()
        txt = str(m.get("text_content") or "").strip()
        if not txt or txt == "NONE":
            continue

        clean_txt = strip_mtext(safe_decode(txt), convert_symbols=True)
        norm_txt = clean_txt.replace(" ", "").replace("　", "").lower()
        if not norm_txt:
            continue

        # Short/ambiguous strings (length <= 3 e.g. "1", "A", "C1") require strict 2D spatial proximity
        is_short_ambiguous = len(norm_txt) <= 3

        # Get revision 2D anchor location if available
        rev_coords = m.get("coordinates")

        best_match = None
        min_dist = float("inf")

        for ref_e in ref_entities:
            props = getattr(ref_e, "properties", {}) or {}
            raw_ref_t = props.get("text") or props.get("value") or ""
            if not raw_ref_t:
                continue

            clean_ref_t = strip_mtext(safe_decode(raw_ref_t), convert_symbols=True)
            norm_ref_t = clean_ref_t.replace(" ", "").replace("　", "").lower()

            if norm_txt == norm_ref_t:
                ref_anchor = calc_anchor(ref_e)

                if rev_coords and len(rev_coords) >= 2 and len(ref_anchor) >= 2:
                    dist = math.hypot(rev_coords[0] - ref_anchor[0], rev_coords[1] - ref_anchor[1])

                    # For short ambiguous strings (like "1"), candidate MUST be within 150mm spatial sheet radius
                    if is_short_ambiguous and dist > 150.0:
                        continue

                    if dist < min_dist:
                        min_dist = dist
                        best_match = (clean_ref_t, ref_e)
                else:
                    # No 2D coords available: allow match ONLY if long/unambiguous string (>3 chars)
                    if not is_short_ambiguous and best_match is None:
                        best_match = (clean_ref_t, ref_e)

        # If a valid spatially-grounded match was found in reference drawing
        if best_match and (not orig or orig in ("N/A", "NONE")):
            matched_ref_text, ref_ent = best_match
            m["original_value"] = matched_ref_text
            if m.get("status") in ("ADDED", "UNVERIFIED"):
                m["status"] = "MATCHED"
            if not m.get("ref_coordinates"):
                m["ref_coordinates"] = calc_anchor(ref_ent)


async def perform_live_dxf_ai_comparison(
    request: Any,
    ref_drawing: DrawingDocument,
    rev_drawing: DrawingDocument,
    method: str = "ai_vision",
) -> PhysicalComparisonResponse:
    """
    Executes live Real-DXF AI drawing comparison pipeline.
    Directly reads physical .dxf files on disk, passes clean DXF entity manifests to Gemini AI,
    and resolves coordinates back to canvas markings.
    """
    api_key = os.environ.get("GEMINI_API_KEY") or getattr(settings, "GEMINI_API_KEY", None)
    openai_key = os.environ.get("OPENAI_API_KEY") or getattr(settings, "OPENAI_API_KEY", None)
    if not api_key and not openai_key:
        raise ValueError("Neither GEMINI_API_KEY nor OPENAI_API_KEY is configured inside system environment.")

    # 1. Check cache (unless force_refresh is requested)
    force_refresh = getattr(request, "force_refresh", False)
    cached = None if force_refresh else ComparisonCacheManager.get_cached_comparison(
        ref_drawing_id=str(ref_drawing.id),
        rev_drawing_id=str(rev_drawing.id),
        ref_hash=ref_drawing.file_hash,
        rev_hash=rev_drawing.file_hash,
        method=method,
    )
    if cached:
        logger.info(f"[live_dxf] Cache hit for ref={ref_drawing.id} vs rev={rev_drawing.id} (method={method})")
        return PhysicalComparisonResponse(**cached)

    # 2. Resolve physical DXF paths on disk
    ref_dxf_path, is_ref_temp = await resolve_physical_dxf_path(ref_drawing)
    rev_dxf_path, is_rev_temp = await resolve_physical_dxf_path(rev_drawing)

    try:
        # 3. Live on-the-fly DXF entity extraction
        ref_entities, ref_meta = await asyncio.to_thread(parse_live_dxf_file, ref_dxf_path)
        rev_entities, rev_meta = await asyncio.to_thread(parse_live_dxf_file, rev_dxf_path)

        ref_rev, rev_rev, ref_title, rev_title = resolve_revisions(
            ref_entities, rev_entities,
            ref_drawing.file_hash, rev_drawing.file_hash,
            ref_drawing.file_name, rev_drawing.file_name,
        )

        ref_regions = await extract_dynamic_regions_async(
            ref_entities, render_bounds=(ref_drawing.metadata or {}).get("render_bounds")
        )
        rev_regions = await extract_dynamic_regions_async(
            rev_entities, render_bounds=(rev_drawing.metadata or {}).get("render_bounds")
        )
        zone_detection_warnings = summarize_zone_detection_confidence(ref_regions, rev_regions)

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
            ref_entities, [e.properties.get("text", "") for e in ref_entities if getattr(e, "entity_type", "") in ("text", "mtext", "attrib")]
        )
        rev_title_fields = BOMAnalyzer.extract_title_block(
            rev_entities, [e.properties.get("text", "") for e in rev_entities if getattr(e, "entity_type", "") in ("text", "mtext", "attrib")]
        )
        title_block_table_text = build_title_block_table(ref_title_fields, rev_title_fields)

        # 4. Build concise DXF entity manifests directly from physical files on disk
        ref_manifest = build_clean_dxf_manifest(ref_entities, ref_meta)
        rev_manifest = build_clean_dxf_manifest(rev_entities, rev_meta)

        client_name = getattr(request, "client_name", None)
        system_instruction = await build_full_system_instruction(client_name=client_name)
        prompt_text = (
            f"=== DIRECT DXF FILE COMPARISON MODE ===\n"
            f"REFERENCE DRAWING: File={ref_drawing.file_name} | Title={ref_title} | Rev={ref_rev}\n"
            f"{ref_manifest}\n\n"
            f"=== BILL OF MATERIALS COMPARISON TABLE ===\n"
            f"{bom_table_text or '(No BOM detected)'}\n\n"
            f"=== TITLE BLOCK COMPARISON TABLE ===\n"
            f"{title_block_table_text or '(No title block data)'}\n\n"
            f"REVISION DRAWING: File={rev_drawing.file_name} | Title={rev_title} | Rev={rev_rev}\n"
            f"{rev_manifest}\n\n"
            "Perform a complete engineering comparison directly from the live DXF entity manifests provided above.\n"
            "Analyze all text, dimensions, tolerances, title blocks, notes, BOM tables, and geometric entity changes.\n"
            "Return your findings as a structured JSON object matching the required schema."
        )

        from .full_ai.prompt_builder import build_multimodal_contents
        contents = await build_multimodal_contents(ref_drawing, rev_drawing, prompt_text)

        logger.info(f"[live_dxf] Dispatching live DXF comparison for ref={ref_drawing.file_name} vs rev={rev_drawing.file_name}")
        raw_json_text, model_used = await asyncio.to_thread(
            execute_gemini_cascade, api_key, system_instruction, contents
        )

        # 5. Parse JSON & Apply Overrides
        parsed = parse_and_normalize_gemini_json(raw_json_text)
        apply_deterministic_overrides(parsed, bom_table_text, title_block_table_text)

        # Inject deterministic markings (Title Block, BOM, Balloons, Auto-Matched) for 100% item coverage
        clean_markings = parsed.get("canvas_markings", [])
        inject_title_block_markings(clean_markings, ref_title_fields, rev_title_fields, ref_entities, rev_entities)
        inject_bom_markings(clean_markings, ref_bom_rows, rev_bom_rows, ref_is_assembly or rev_is_assembly, ref_entities, rev_entities)
        inject_ballooning_markings(clean_markings, ref_entities, rev_entities)
        generate_auto_matched_markings(clean_markings, ref_entities, rev_entities)
        reconcile_reference_drawing_values(clean_markings, ref_entities)

        # Normalize taxonomy feature keys for perfect UI checklist grouping
        from . import taxonomy
        for m in clean_markings:
            cat = m.get("category", "drawing_views")
            m["feature"] = taxonomy.normalize_feature(cat, m.get("feature"))

        parsed["canvas_markings"] = clean_markings

        # 6. Resolve Coordinates
        resolve_and_harden_coordinates(
            parsed, ref_drawing, rev_drawing, ref_entities, rev_entities,
            ref_regions, rev_regions, ref_bom_rows, rev_bom_rows,
            ref_title_fields, rev_title_fields
        )

        comparison_response = build_physical_comparison_response(parsed, model_used, zone_detection_warnings)

        # 7. Persist session & write cache
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

    finally:
        # Clean up temporary converted DXF files if applicable
        if is_ref_temp and ref_dxf_path.exists():
            try:
                ref_dxf_path.unlink()
            except Exception:
                pass
        if is_rev_temp and rev_dxf_path.exists():
            try:
                rev_dxf_path.unlink()
            except Exception:
                pass
