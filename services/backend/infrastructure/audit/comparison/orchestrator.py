import os
import re
import json
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
    CanvasMarking
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
    generate_auto_matched_markings
)
from .coordinate_resolver import resolve_marking_coordinates
from .schemas import Coordinate2D, BoundingBox2D
from .cache_manager import ComparisonCacheManager

async def perform_drawing_comparison(
    request,
    ref_drawing: DrawingDocument,
    rev_drawing: DrawingDocument,
    ref_entities: list,
    rev_entities: list
) -> PhysicalComparisonResponse:
    """Orchestrates drawing comparison pipeline including layout analysis, prompt assembly, and post-processing."""
    # Check cache first
    cached_payload = ComparisonCacheManager.get_cached_comparison(
        ref_drawing_id=str(ref_drawing.id),
        rev_drawing_id=str(rev_drawing.id),
        ref_hash=ref_drawing.file_hash,
        rev_hash=rev_drawing.file_hash
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
                canvas_markings=[CanvasMarking(**item) for item in cached_payload.get("canvas_markings", [])]
            )
        except Exception as cache_err:
            logger.warning(f"Failed to parse cached drawing comparison, performing full comparison: {cache_err}")

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

    # Reconcile BOM layout and extract tabular rows
    ref_bounds = ref_drawing.metadata.get("render_bounds") if ref_drawing and ref_drawing.metadata else None
    rev_bounds = rev_drawing.metadata.get("render_bounds") if rev_drawing and rev_drawing.metadata else None
    
    ref_bom_rows, ref_is_assembly = BOMAnalyzer.extract_bom_table(ref_entities, render_bounds=ref_bounds)
    rev_bom_rows, rev_is_assembly = BOMAnalyzer.extract_bom_table(rev_entities, render_bounds=rev_bounds)
    is_assembly_drawing = ref_is_assembly or rev_is_assembly
    bom_comparison_table = BOMAnalyzer.build_bom_table(ref_bom_rows, rev_bom_rows, is_assembly_drawing)
    logger.info(f"BOM extraction complete - is_assembly={is_assembly_drawing}, ref_bom_rows={ref_bom_rows}, rev_bom_rows={rev_bom_rows}")

    # Retrieve API key
    api_key = os.environ.get("GEMINI_API_KEY") or getattr(settings, "GEMINI_API_KEY", None)
    if not api_key:
        logger.warning("GEMINI_API_KEY environment variable is not defined.")
        raise ValueError("GEMINI_API_KEY is not configured.")

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
        import asyncio
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

    ref_title_fields = BOMAnalyzer.extract_title_block(ref_entities, ref_all_text_list, ocr_results=ref_ocr)
    rev_title_fields = BOMAnalyzer.extract_title_block(rev_entities, rev_all_text_list, ocr_results=rev_ocr)
    
    # Run comparative overlays checks
    title_block_table = build_title_block_table(ref_title_fields, rev_title_fields)

    # Compute bounding boxes for visual overlap warnings
    ref_bom_bbox_raw = BOMAnalyzer.compute_bom_bbox(ref_entities)
    rev_bom_bbox_raw = BOMAnalyzer.compute_bom_bbox(rev_entities)
    rev_title_bbox_raw = BOMAnalyzer.compute_title_block_bbox(rev_entities)

    # Validate regions via BoundingBox2D DTOs
    ref_bom_bbox = BoundingBox2D.from_tuple(ref_bom_bbox_raw).to_tuple() if ref_bom_bbox_raw else None
    rev_bom_bbox = BoundingBox2D.from_tuple(rev_bom_bbox_raw).to_tuple() if rev_bom_bbox_raw else None
    rev_title_bbox = BoundingBox2D.from_tuple(rev_title_bbox_raw).to_tuple() if rev_title_bbox_raw else None

    logger.info(f"Spatial regions - ref BOM bbox: {ref_bom_bbox} | rev BOM bbox: {rev_bom_bbox} | rev Title bbox: {rev_title_bbox}")
    
    if rev_bom_bbox and rev_title_bbox:
        if rev_bom_bbox[0] < rev_title_bbox[2] and rev_bom_bbox[2] > rev_title_bbox[0] and \
           rev_bom_bbox[1] < rev_title_bbox[3] and rev_bom_bbox[3] > rev_title_bbox[1]:
            logger.warning(f"Spatial region overlap detected! BOM: {rev_bom_bbox}, Title: {rev_title_bbox}")

    ref_iso_text = ref_groups["isometric_view_data"]
    rev_iso_text = rev_groups["isometric_view_data"]

    # api_key is already resolved at the top of the comparison orchestrator

    system_instruction = (
        "You are an expert manufacturing quality inspector and principal technical drafting checker at a major engineering facility.\n"
        "Your role is to perform a detailed physical and semantic comparison of two technical drawings of a mechanical part:\n"
        "1. Reference Drawing (ORIGINAL baseline document version)\n"
        "2. Revised Drawing (KMTI updated blueprint version)\n\n"
        "You will compare both the text annotations (dimensions, notes, BOM cells) and the actual drawing layout elements (views, orientations, geometric structures) to output a complete, structured diff of the updates.\n"
        "Your final response MUST be a valid JSON matching the exact schema definition provided."
    )

    contents = []
    
    # Load rendering images for multimodal visual check if they exist
    ref_image_part = None
    rev_image_part = None
    
    try:
        storage_root = get_storage_root()
        ref_render_path = storage_root / "renderings" / f"{request.reference_drawing_id}.png"
        rev_render_path = storage_root / "renderings" / f"{request.drawing_id}.png"
        
        if ref_render_path.exists() and rev_render_path.exists():
            logger.info(f"Loading multimodal visual comparison images: {ref_render_path} & {rev_render_path}")
            with open(ref_render_path, "rb") as f:
                ref_bytes = f.read()
            with open(rev_render_path, "rb") as f:
                rev_bytes = f.read()
                
            ref_image_part = types.Part.from_bytes(data=ref_bytes, mime_type="image/png")
            rev_image_part = types.Part.from_bytes(data=rev_bytes, mime_type="image/png")
            logger.info("Successfully loaded raw PNG bytes as types.Part multimodal components.")
        else:
            logger.warning(
                f"Multimodal renderings missing from disk. "
                f"Ref exists: {ref_render_path.exists()}, Rev exists: {rev_render_path.exists()}"
            )
    except Exception as img_err:
        logger.warning(f"Failed to prepare drawing image parts for multimodal comparison: {str(img_err)}")

    prompt = (
        "Act as an automated engineering checker. Review and audit character-by-character the visual and structural differences between two technical drawing versions using the following semantic variables:\n\n"
        "1. DRAWING VIEWS (Main Geometry Area):\n"
        f"   Reference (Original): {ref_geom if ref_geom else 'No callouts detected'}\n"
        f"   Revision (KMTI): {rev_geom if rev_geom else 'No callouts detected'}\n\n"
        "2. NOTES SECTION (Manufacturing Instructions):\n"
        f"   Reference (Original): {ref_notes if ref_notes else 'No rules detected'}\n"
        f"   Revision (KMTI): {rev_notes if rev_notes else 'No rules detected'}\n\n"
        "3. BILL OF MATERIALS (BOM Table):\n"
        "   CATEGORY RULE: Every canvas_marking for a BOM item MUST use \"category\": \"bill_of_materials\".\n"
        "   COLUMNS EXPECTED FOR PARTS DRAWING: No., 材質 Code, 材料寸法/型式 Dimension/Model No., 材料個数 (Qty), 素材重量 Kg Material Weight (kg), 仕上重量 Kg Finished Weight (kg), 備考 Remark.\n"
        f"   Reference (Original): {ref_bom if ref_bom else 'No BOM data detected'}\n"
        f"   Revision (KMTI): {rev_bom if rev_bom else 'No BOM data detected'}\n\n"
        "4. TITLE BLOCK (Pre-extracted 11-field comparison table — values are REAL, dynamically read from the actual drawings):\n"
        f"{title_block_table}\n\n"
        "5. ISOMETRIC VIEW (ISO View):\n"
        f"   Reference (Original): {ref_iso_text}\n"
        f"   Revision (KMTI): {rev_iso_text}\n\n"
        "6. OTHER ENGINEERING REFERENCES:\n"
        f"   Reference (Original): Full grid frame line indicators across outer margins.\n"
        f"   Revision (KMTI): Definitive CAD boundary ticks (┌ ┐) along print space margins.\n\n"
        "AUDIT INSTRUCTIONS FOR EACH CATEGORY:\n"
        "[Perform a character-by-character compare of all dimensions, BOM rows, notes and metadata. Return the JSON output strictly according to PhysicalComparisonResponse schema.]"
    )

    if ref_image_part and rev_image_part:
        contents.extend([
            "Reference Drawing Image (Original Baseline version):",
            ref_image_part,
            "Revised Drawing Image (Updated KMTI version):",
            rev_image_part,
            "Please compare the two drawings visually and semantically based on the rules."
        ])
    contents.append(prompt)

    # Call Gemini Cascade Fallback
    response_text = execute_gemini_cascade(api_key, system_instruction, contents)
    parsed = json.loads(response_text)
    logger.info("Successfully parsed structured Gemini 2.5 Pro comparison results.")

    # Override title_block and bill_of_materials comparative contents with Python-pre-built tables
    if "bill_of_materials" not in parsed or parsed["bill_of_materials"] is None:
        parsed["bill_of_materials"] = {"status": "CHANGED", "difference_summary": "BOM checked", "engineering_discrepancy_details": "Real BOM data used", "reference_content": "", "revision_content": ""}
    parsed["bill_of_materials"]["reference_content"] = bom_comparison_table
    parsed["bill_of_materials"]["revision_content"] = bom_comparison_table

    if "title_block" not in parsed or parsed["title_block"] is None:
        parsed["title_block"] = {"status": "CHANGED", "difference_summary": "Title Block checked", "engineering_discrepancy_details": "Real Title Block data used", "reference_content": "", "revision_content": ""}
    parsed["title_block"]["reference_content"] = title_block_table
    parsed["title_block"]["revision_content"] = title_block_table

    # Process canvas markings
    existing_markings = parsed.get("canvas_markings", [])

    # Clean title block and ALL Gemini-generated BOM markings to prevent duplicate and false-positive checks/pins
    clean_markings = [
        m for m in existing_markings 
        if not is_title_block_category(m.get("category")) 
        and not is_bom_category(m.get("category")) 
        and not is_admin_bom_marking(m)
    ]
    
    # Post-process Gemini canvas markings to extract original_value for CHANGED markers
    for m in clean_markings:
        if m.get("status") == "CHANGED" and not m.get("original_value"):
            d = m.get("details", "")
            if " changed: " in d and " -> " in d:
                try:
                    m["original_value"] = d.split(" changed: ")[1].split(" -> ")[0].strip()
                except Exception:
                    pass

    # Clean [ID: ...] prefix from text_content if AI mistakenly included it
    for m in clean_markings:
        if "text_content" in m:
            txt = m["text_content"]
            match = re.match(r'^\[ID:\s*([^,\]]+)[^\]]*\]\s*(.*)$', txt)
            if match:
                if not m.get("entity_id"):
                    m["entity_id"] = match.group(1).strip()
                m["text_content"] = match.group(2).strip()

    # Build ID lookup dictionaries
    id_to_rev_entity = {f"REV-{e.properties.get('handle')}": e for e in rev_entities if e.properties and e.properties.get('handle')}
    id_to_ref_entity = {f"REF-{e.properties.get('handle')}": e for e in ref_entities if e.properties and e.properties.get('handle')}

    # Build allowed ID sets
    allowed_rev_ids = set()
    for line in (rev_geom + "\n" + rev_notes + "\n" + rev_iso_text).split('\n'):
        m_id = re.match(r'^\[ID:\s*([^,\]]+)[^\]]*\]', line.strip())
        if m_id:
            allowed_rev_ids.add(m_id.group(1).strip())
        
    allowed_ref_ids = set()
    for line in (ref_geom + "\n" + ref_notes + "\n" + ref_iso_text).split('\n'):
        m_id = re.match(r'^\[ID:\s*([^,\]]+)[^\]]*\]', line.strip())
        if m_id:
            allowed_ref_ids.add(m_id.group(1).strip())

    # Anti-Hallucination Guardrails
    rev_all_text = " ".join([e.properties.get("text", "") for e in rev_entities if getattr(e, "entity_type", "") == "text"])
    ref_all_text = " ".join([e.properties.get("text", "") for e in ref_entities if getattr(e, "entity_type", "") == "text"])
    rev_all_text_lower = rev_all_text.lower().replace(" ", "").replace("\n", "")
    ref_all_text_lower = ref_all_text.lower().replace(" ", "").replace("\n", "")
    
    guardrailed_markings = []
    for m in clean_markings:
        txt = str(m.get("text_content", "")).strip()
        if not txt:
            continue
        txt_clean = txt.lower().replace(" ", "").replace("\n", "")
        mark_status = m.get("status")
        
        eid = m.get("entity_id")
        if eid:
            if eid.startswith("REV-") and eid not in allowed_rev_ids:
                logger.warning(f"Guardrail intercepted marker {eid} because it is outside allowed drawing views (likely BOM/Title block hallucination).")
                continue
            if eid.startswith("REF-") and eid not in allowed_ref_ids:
                logger.warning(f"Guardrail intercepted marker {eid} because it is outside allowed drawing views (likely BOM/Title block hallucination).")
                continue
        
        if mark_status in ["ADDED", "CHANGED"]:
            if txt_clean not in rev_all_text_lower:
                logger.warning(f"Guardrail intercepted hallucinated {mark_status} marker for '{txt}' (not found in rev drawing)")
                continue
        elif mark_status == "REMOVED":
            if txt_clean not in ref_all_text_lower:
                logger.warning(f"Guardrail intercepted hallucinated REMOVED marker for '{txt}' (not found in ref drawing)")
                continue
        guardrailed_markings.append(m)
    clean_markings = guardrailed_markings

    # MATCHED Map-Reduce
    generate_auto_matched_markings(clean_markings, rev_geom, rev_notes, rev_iso_text)

    # Inject Title Block & BOM markings
    used_ref_entities = set()
    used_rev_entities = set()

    inject_title_block_markings(clean_markings, ref_title_fields, rev_title_fields, ref_entities, rev_entities)
    inject_bom_markings(clean_markings, ref_bom_rows, rev_bom_rows, is_assembly_drawing, ref_bom_bbox, rev_bom_bbox, ref_entities, rev_entities, used_ref_entities, used_rev_entities)

    # Coordinate Resolution
    resolve_marking_coordinates(
        clean_markings, id_to_rev_entity, id_to_ref_entity,
        rev_entities, ref_entities, rev_bom_rows, ref_bom_rows,
        rev_title_fields, ref_title_fields, rev_bom_bbox, ref_bom_bbox,
        used_rev_entities, used_ref_entities
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

    parsed["canvas_markings"] = clean_markings

    comparison_response = PhysicalComparisonResponse(
        drawing_views=CategoryComparison(**parsed["drawing_views"]),
        notes_section=CategoryComparison(**parsed["notes_section"]),
        bill_of_materials=CategoryComparison(**parsed["bill_of_materials"]),
        title_block=CategoryComparison(**parsed["title_block"]),
        isometric_view=CategoryComparison(**parsed["isometric_view"]),
        other_engineering_references=CategoryComparison(**parsed["other_engineering_references"]),
        canvas_markings=[CanvasMarking(**item) for item in parsed.get("canvas_markings", [])]
    )

    # Save comparison findings as AuditSession + AuditViolations
    try:
        non_matched = [m for m in parsed.get("canvas_markings", []) if m.get("status") != "MATCHED"]
        total_markings = len(parsed.get("canvas_markings", []))
        matched_count = total_markings - len(non_matched)
        comparison_score = round((matched_count / total_markings) * 100, 2) if total_markings > 0 else 100.0

        comparison_session = AuditSession(
            drawing_id=rev_drawing.id,
            reference_drawing_id=ref_drawing.id,
            standard_id=None,
            client_name=None,
            status="completed",
            compliance_score=comparison_score,
            confidence_score=0.95,
            timings={},
            diagnostics={
                "source": "physical_comparison",
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
            payload=comparison_response.model_dump()
        )
    except Exception as cache_write_err:
        logger.warning(f"Failed to cache physical comparison response: {cache_write_err}")

    return comparison_response
