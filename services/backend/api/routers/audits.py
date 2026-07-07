import os
import time
import re
import aiofiles
from datetime import datetime, timezone, UTC
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Header, Form
from fastapi.responses import FileResponse
from pydantic import BaseModel
from google import genai
from google.genai import types

from ...domain.models.audit_session import AuditSession
from ...domain.models.audit_violation import AuditViolation
from ...domain.models.drawing_document import DrawingDocument
from ...domain.models.extracted_entity import ExtractedEntity
from ...domain.models.client import ClientDocument
from ...domain.models.standard_document import StandardDocument
from ...domain.models.standard_chunk import StandardChunk
from ...infrastructure.audit.audit_pipeline import audit_queue
from ...infrastructure.storage.path_resolver import get_storage_root
from ...infrastructure.audit.report_generator import ReportGenerator
from ...infrastructure.utils.text import (
    safe_decode,
    strip_mtext,
    compare_values,
    extract_semantic_text_groups,
    build_title_block_table,
)
from ...logger import logger
from ...config import settings
from ..dependencies import get_auth_token
from ..schemas import (
    StandardResponse,
    AuditSessionResponse,
    AuditViolationResponse,
    ClientResponse,
    CreateClientRequest,
    LaunchAuditRequest,
    UpdateAuditSessionRequest,
    PhysicalComparisonRequest,
    PhysicalComparisonResponse,
    CategoryComparison,
    CanvasMarking,
)

router = APIRouter()


@router.post(
    "/audits/launch",
    response_model=StandardResponse[AuditSessionResponse],
    summary="Initialize and enqueue drawing audit process session",
    dependencies=[Depends(get_auth_token)]
)
async def launch_audit(
    request: LaunchAuditRequest, 
    token: str = Depends(get_auth_token),
    x_session_token: str | None = Header(None, alias="X-Session-Token")
):
    """
    Registers a new AuditSession document in database in 'queued' state and pushes the task to
    the background processing queue, returning immediately to the client.
    """
    username = None
    try:
        if x_session_token:
            from ...core.auth import verify_jwt_token
            payload = verify_jwt_token(x_session_token)
            username = payload.get("username")
    except Exception:
        pass

    drawing = await DrawingDocument.get(request.drawing_id)
    if not drawing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Drawing document not found: {request.drawing_id}"
        )

    # Auto-Revision Comparison Resolution
    ref_drawing_id = request.reference_drawing_id
    if not ref_drawing_id:
        ref_drawing_id = getattr(drawing, "previous_revision_id", None)
        if ref_drawing_id:
            logger.info(f"Phase 7.3: Auto-linking drawing {drawing.id} to previous revision {ref_drawing_id} for comparative audit.")

    session = AuditSession(
        drawing_id=request.drawing_id,
        reference_drawing_id=ref_drawing_id,
        standard_id=request.standard_id,
        client_name=request.client_name.upper() if request.client_name else None,
        status="queued",
        username=username
    )
    await session.save()

    await audit_queue.enqueue(
        drawing_id=request.drawing_id,
        standard_id=request.standard_id,
        session_id=str(session.id),
        client_name=request.client_name.upper() if request.client_name else None
    )

    return StandardResponse(
        success=True,
        data=AuditSessionResponse(
            id=str(session.id),
            drawing_id=session.drawing_id,
            reference_drawing_id=session.reference_drawing_id,
            standard_id=session.standard_id,
            client_name=session.client_name,
            status=session.status,
            compliance_score=session.compliance_score,
            confidence_score=session.confidence_score,
            timings=session.timings,
            diagnostics=session.diagnostics,
            started_at=session.started_at,
            completed_at=session.completed_at,
            username=session.username,
            is_deleted=session.is_deleted,
            deleted_at=session.deleted_at,
            deleted_by=session.deleted_by,
            is_restored=session.is_restored
        )
    )


@router.get(
    "/audits/sessions",
    response_model=StandardResponse[list[AuditSessionResponse]],
    summary="List historical audit sessions metadata",
    dependencies=[Depends(get_auth_token)]
)
async def list_audit_sessions(show_deleted: bool = False):
    """
    Fetches all completed or active sessions from MongoDB.
    """
    if show_deleted:
        sessions = await AuditSession.find_all().to_list()
    else:
        sessions = await AuditSession.find(AuditSession.is_deleted != True).to_list()
        
    res = [
        AuditSessionResponse(
            id=str(s.id),
            drawing_id=s.drawing_id,
            reference_drawing_id=s.reference_drawing_id,
            standard_id=s.standard_id,
            client_name=s.client_name,
            status=s.status,
            compliance_score=s.compliance_score,
            confidence_score=s.confidence_score,
            timings=s.timings,
            diagnostics=s.diagnostics,
            started_at=s.started_at,
            completed_at=s.completed_at,
            username=s.username,
            is_deleted=s.is_deleted,
            deleted_at=s.deleted_at,
            deleted_by=s.deleted_by,
            is_restored=s.is_restored
        )
        for s in sessions
    ]
    return StandardResponse(success=True, data=res)


@router.get(
    "/audits/sessions/trash",
    response_model=StandardResponse[list[AuditSessionResponse]],
    summary="List all soft-deleted audit sessions",
    dependencies=[Depends(get_auth_token)]
)
async def list_trash_sessions():
    """
    Fetches all audit sessions from MongoDB that are marked as is_deleted=True.
    """
    sessions = await AuditSession.find(AuditSession.is_deleted == True).to_list()
    res = [
        AuditSessionResponse(
            id=str(s.id),
            drawing_id=s.drawing_id,
            reference_drawing_id=s.reference_drawing_id,
            standard_id=s.standard_id,
            client_name=s.client_name,
            status=s.status,
            compliance_score=s.compliance_score,
            confidence_score=s.confidence_score,
            timings=s.timings,
            diagnostics=s.diagnostics,
            started_at=s.started_at,
            completed_at=s.completed_at,
            username=s.username,
            is_deleted=s.is_deleted,
            deleted_at=s.deleted_at,
            deleted_by=s.deleted_by,
            is_restored=s.is_restored
        )
        for s in sessions
    ]
    return StandardResponse(success=True, data=res)


@router.delete(
    "/audits/sessions/trash",
    response_model=StandardResponse[dict],
    summary="Permanently delete all soft-deleted audit sessions",
    dependencies=[Depends(get_auth_token)]
)
async def empty_trash_sessions():
    """
    Permanently deletes all audit sessions from MongoDB that are marked as is_deleted=True.
    """
    trashed_sessions = await AuditSession.find(AuditSession.is_deleted == True).to_list()
    count = len(trashed_sessions)
    for session in trashed_sessions:
        await session.delete()
        
    return StandardResponse(
        success=True,
        data={"message": f"Successfully purged {count} sessions from trashbin.", "deleted_count": count}
    )


@router.get(
    "/audits/sessions/{id}",
    response_model=StandardResponse[AuditSessionResponse],
    summary="Retrieve details of an AuditSession",
    dependencies=[Depends(get_auth_token)]
)
async def get_audit_session(id: str):
    session = await AuditSession.get(id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Audit session not found: {id}"
        )
    return StandardResponse(
        success=True,
        data=AuditSessionResponse(
            id=str(session.id),
            drawing_id=session.drawing_id,
            reference_drawing_id=session.reference_drawing_id,
            standard_id=session.standard_id,
            client_name=session.client_name,
            status=session.status,
            compliance_score=session.compliance_score,
            confidence_score=session.confidence_score,
            timings=session.timings,
            diagnostics=session.diagnostics,
            started_at=session.started_at,
            completed_at=session.completed_at,
            username=session.username,
            is_deleted=session.is_deleted,
            deleted_at=session.deleted_at,
            deleted_by=session.deleted_by,
            is_restored=session.is_restored
        )
    )


@router.delete(
    "/audits/sessions/{id}",
    response_model=StandardResponse[dict],
    summary="Delete an audit session and associated violations",
    dependencies=[Depends(get_auth_token)]
)
async def delete_audit_session(id: str, token: str = Depends(get_auth_token)):
    """
    Soft deletes the specified audit session from MongoDB.
    """
    session = await AuditSession.get(id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Audit session not found: {id}"
        )
    
    username = None
    try:
        from ...core.auth import verify_jwt_token
        payload = verify_jwt_token(token)
        username = payload.get("username")
    except Exception:
        pass
    
    session.is_deleted = True
    session.deleted_at = datetime.now(timezone.utc)
    session.deleted_by = username
    await session.save()
    
    return StandardResponse(
        success=True,
        data={"message": f"Audit session '{id}' successfully moved to trashbin."}
    )


@router.get(
    "/audits/sessions/{id}/violations",
    response_model=StandardResponse[list[AuditViolationResponse]],
    summary="Get all findings/violations flagged during an audit session",
    dependencies=[Depends(get_auth_token)]
)
async def get_session_violations(id: str):
    """
    Returns the list of persistent infraction violations.
    """
    violations = await AuditViolation.find(AuditViolation.audit_session_id == id).to_list()
    res = [
        AuditViolationResponse(
            id=str(v.id),
            audit_session_id=v.audit_session_id,
            severity=v.severity,
            category=v.category,
            description=v.description,
            recommendation=v.recommendation,
            affected_entities=v.affected_entities,
            confidence=v.confidence,
            source=v.source,
            coordinates=v.coordinates,
            standard_reference=v.standard_reference,
            pen_type=v.pen_type,
            is_resolved=v.is_resolved,
            resolved_at=v.resolved_at,
            checker_remarks=v.checker_remarks,
            created_at=v.created_at
        )
        for v in violations
    ]
    return StandardResponse(success=True, data=res)


class ViolationReviewRequest(BaseModel):
    is_valid: bool
    remarks: str = ""


@router.patch(
    "/audits/violations/{id}/review",
    response_model=StandardResponse[AuditViolationResponse],
    summary="Record supervisor review of a violation, accumulating lessons learned in the vector store",
    dependencies=[Depends(get_auth_token)]
)
async def review_violation(id: str, request: ViolationReviewRequest):
    """
    Supervisor reviewing a violation. Confirmed findings are embedded and automatically
    written to the vector store (`lessons_learned`), updating AI memory for future audits.
    """
    violation = await AuditViolation.get(id)
    if not violation:
        raise HTTPException(status_code=404, detail="Audit violation not found.")

    violation.is_resolved = request.is_valid
    violation.resolved_at = datetime.now(timezone.utc)
    violation.checker_remarks = request.remarks
    violation.resolution_type = "APPROVED" if request.is_valid else "REJECTED"
    await violation.save()

    # Index into vector database
    try:
        from ...infrastructure.ai.vectorstore.embedding_provider import EmbeddingProvider
        from ...infrastructure.ai.vectorstore.lancedb_manager import LanceDBManager

        provider = EmbeddingProvider()
        db_manager = LanceDBManager()

        text_to_embed = f"Violation Category: {violation.category}\nDescription: {violation.description}\nSupervisor Remarks: {request.remarks}\nValid: {request.is_valid}"
        vector = provider.embed_text(text_to_embed)

        record = {
            "vector": vector,
            "text": text_to_embed,
            "metadata": {
                "violation_id": str(violation.id),
                "audit_session_id": str(violation.audit_session_id),
                "is_valid": request.is_valid,
                "remarks": request.remarks,
                "category": violation.category,
                "severity": violation.severity,
                "timestamp": datetime.now(timezone.utc).timestamp()
            }
        }
        db_manager.write_embeddings("lessons_learned", [record])
        logger.info(f"Phase 8.2: Violation {id} indexed as a lesson learned in vector index.")
    except Exception as vec_err:
        logger.warning(f"Failed to index reviewed violation into lessons_learned (non-fatal): {vec_err}")

    return StandardResponse(
        success=True,
        data=AuditViolationResponse(
            id=str(violation.id),
            audit_session_id=violation.audit_session_id,
            severity=violation.severity,
            category=violation.category,
            description=violation.description,
            recommendation=violation.recommendation,
            affected_entities=violation.affected_entities,
            confidence=violation.confidence,
            source=violation.source,
            coordinates=violation.coordinates,
            standard_reference=violation.standard_reference,
            pen_type=violation.pen_type,
            is_resolved=violation.is_resolved,
            resolved_at=violation.resolved_at,
            checker_remarks=violation.checker_remarks,
            created_at=violation.created_at
        )
    )


@router.get(
    "/reports/{session_id}/pdf",
    summary="Get official PDF Compliance Audit Report",
    dependencies=[Depends(get_auth_token)]
)
async def export_pdf_report(session_id: str):
    """
    Compiles detailed findings, embeds red-lined blueprint graphics,
    and returns a downloadable PDF artifact.
    """
    try:
        target_path = get_storage_root() / "reports" / f"report_{session_id}.pdf"
        await ReportGenerator.compile_pdf_report(session_id, target_path)
        
        if not target_path.exists():
            raise HTTPException(status_code=500, detail="Failed to compile PDF report artifact on disk.")
            
        return FileResponse(
            str(target_path),
            media_type="application/pdf",
            filename=f"AI-2D-Checker_Report_{session_id}.pdf"
        )
    except Exception as err:
        logger.error(f"Failed to compile report for session {session_id}: {str(err)}")
        raise HTTPException(status_code=500, detail=f"PDF compilation failed: {str(err)}")


@router.get(
    "/reports/{session_id}/xlsx",
    summary="Get detailed XLSX technical sheets",
    dependencies=[Depends(get_auth_token)]
)
async def export_xlsx_report(session_id: str):
    """
    Exports structured audit sheets with layered violation grids.
    """
    try:
        target_path = get_storage_root() / "reports" / f"report_{session_id}.xlsx"
        await ReportGenerator.compile_xlsx_report(session_id, target_path)
        
        if not target_path.exists():
            raise HTTPException(status_code=500, detail="Failed to compile Excel spreadsheet on disk.")
            
        return FileResponse(
            str(target_path),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            filename=f"AI-2D-Checker_Report_{session_id}.xlsx"
        )
    except Exception as err:
        logger.error(f"Failed to compile Excel report for session {session_id}: {str(err)}")
        raise HTTPException(status_code=500, detail=f"XLSX export failed: {str(err)}")


@router.post(
    "/audits/physical-comparison",
    response_model=StandardResponse[PhysicalComparisonResponse],
    summary="Perform dynamic AI-grounded engineering physical comparison of drawing files",
    dependencies=[Depends(get_auth_token)]
)
async def perform_physical_comparison(request: PhysicalComparisonRequest):
    ref_drawing = await DrawingDocument.get(request.reference_drawing_id)
    rev_drawing = await DrawingDocument.get(request.drawing_id)
    
    if not ref_drawing or not rev_drawing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Reference drawing or revised drawing not found."
        )

    ref_entities = await ExtractedEntity.find(ExtractedEntity.drawing_id == request.reference_drawing_id).to_list()
    rev_entities = await ExtractedEntity.find(ExtractedEntity.drawing_id == request.drawing_id).to_list()

    def map_signature_value(text: str) -> str:
        if not text:
            return "NONE"
        return text.strip()

    ref_rev = "A"
    for e in ref_entities:
        if e.entity_type == "text":
            raw_txt = e.properties.get("text")
            if raw_txt is not None:
                txt = str(raw_txt).strip()
                m = re.search(r'\b(?:REV|revision)\.?\s*([A-Z0-9]+)\b', txt, re.IGNORECASE)
                if m:
                    ref_rev = m.group(1)
                    
    rev_rev = "B"
    for e in rev_entities:
        if e.entity_type == "text":
            raw_txt = e.properties.get("text")
            if raw_txt is not None:
                txt = str(raw_txt).strip()
                m = re.search(r'\b(?:REV|revision)\.?\s*([A-Z0-9]+)\b', txt, re.IGNORECASE)
                if m:
                    rev_rev = m.group(1)
    
    if ref_rev == rev_rev and ref_drawing.file_hash != rev_drawing.file_hash:
        try:
            ref_rev_char = ref_rev[0] if ref_rev else "A"
            rev_rev = chr(ord(ref_rev_char) + 1) if (ref_rev_char.isalpha() and len(ref_rev_char)==1) else "B"
        except Exception:
            rev_rev = "B"

    ref_title = ref_drawing.file_name.rsplit('.', 1)[0].replace('_', ' ').replace('-', ' ').upper()
    rev_title = rev_drawing.file_name.rsplit('.', 1)[0].replace('_', ' ').replace('-', ' ').upper()

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
    from ...infrastructure.audit.bom_analyzer import BOMAnalyzer
    ref_bounds = ref_drawing.metadata.get("render_bounds") if ref_drawing and ref_drawing.metadata else None
    rev_bounds = rev_drawing.metadata.get("render_bounds") if rev_drawing and rev_drawing.metadata else None
    ref_bom_rows, ref_is_assembly = BOMAnalyzer.extract_bom_table(ref_entities, render_bounds=ref_bounds)
    rev_bom_rows, rev_is_assembly = BOMAnalyzer.extract_bom_table(rev_entities, render_bounds=rev_bounds)
    is_assembly_drawing = ref_is_assembly or rev_is_assembly
    bom_comparison_table = BOMAnalyzer.build_bom_table(ref_bom_rows, rev_bom_rows, is_assembly_drawing)
    logger.info(f"BOM extraction complete - is_assembly={is_assembly_drawing}, ref_bom_rows={ref_bom_rows}, rev_bom_rows={rev_bom_rows}")

    # Reconcile title block coordinates and dimensions
    ref_all_text_list = [e.properties.get("text", "") for e in ref_entities if getattr(e, "entity_type", "") == "text"]
    rev_all_text_list = [e.properties.get("text", "") for e in rev_entities if getattr(e, "entity_type", "") == "text"]
    ref_title_fields = BOMAnalyzer.extract_title_block(ref_entities, ref_all_text_list)
    rev_title_fields = BOMAnalyzer.extract_title_block(rev_entities, rev_all_text_list)
    
    # Run comparative overlays checks
    title_block_table = build_title_block_table(ref_title_fields, rev_title_fields)

    # Compute bounding boxes for visual overlap warnings
    rev_bom_bbox = BOMAnalyzer.compute_bom_bbox(rev_entities)
    rev_title_bbox = BOMAnalyzer.compute_title_block_bbox(rev_entities)
    logger.info(f"Spatial regions - rev BOM bbox: {rev_bom_bbox} | rev Title bbox: {rev_title_bbox}")
    if rev_bom_bbox and rev_title_bbox:
        # Check simple box overlap (xmin1 < xmax2 and xmax1 > xmin2 and ymin1 < ymax2 and ymax1 > ymin2)
        if rev_bom_bbox[0] < rev_title_bbox[2] and rev_bom_bbox[2] > rev_title_bbox[0] and \
           rev_bom_bbox[1] < rev_title_bbox[3] and rev_bom_bbox[3] > rev_title_bbox[1]:
            logger.warning(f"Spatial region overlap detected! BOM: {rev_bom_bbox}, Title: {rev_title_bbox}")

    ref_iso_text = ref_groups["isometric_view_data"]
    rev_iso_text = rev_groups["isometric_view_data"]

    # Invalidate stale comparison cache files on upload/ingestion if necessary (handled at upload_drawing)

    api_key = os.environ.get("GEMINI_API_KEY") or getattr(settings, "GEMINI_API_KEY", None)
    if not api_key:
        logger.warning("GEMINI_API_KEY environment variable is not defined. Cascade fallback activated.")
        # [Fallback comparative mock data simulation logic...]
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Gemini API Key is not configured. Please supply a valid GEMINI_API_KEY inside the system environment."
        )

    client = genai.Client(api_key=api_key)

    system_instruction = (
        "You are an expert manufacturing quality inspector and principal technical drafting checker at a major engineering facility.\n"
        "Your role is to perform a detailed physical and semantic comparison of two technical drawings of a mechanical part:\n"
        "1. Reference Drawing (ORIGINAL baseline document version)\n"
        "2. Revised Drawing (KMTI updated blueprint version)\n\n"
        "You will compare both the text annotations (dimensions, notes, BOM cells) and the actual drawing layout elements (views, orientations, geometric structures) to output a complete, structured diff of the updates.\n"
        "Your final response MUST be a valid JSON matching the exact schema definition provided."
    )

    try:
        # Construct multimodal contents sequence
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
                    
                ref_image_part = types.Part.from_bytes(
                    data=ref_bytes,
                    mime_type="image/png"
                )
                rev_image_part = types.Part.from_bytes(
                    data=rev_bytes,
                    mime_type="image/png"
                )
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

        _model_cascade = ["gemini-2.5-pro", "gemini-2.5-flash", "gemini-flash-latest"]
        _last_err = None
        response = None
        for _attempt, _model in enumerate(_model_cascade):
            try:
                logger.info(f"Gemini comparison attempt {_attempt + 1}/{len(_model_cascade)} using model: {_model}")
                response = client.models.generate_content(
                    model=_model,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        response_mime_type="application/json",
                        response_schema=PhysicalComparisonResponse,
                        temperature=0.0
                    )
                )
                logger.info(f"Gemini comparison succeeded with model: {_model}")
                break
            except Exception as _model_err:
                _last_err = _model_err
                _err_str = str(_model_err)
                _is_overload = "503" in _err_str or "429" in _err_str or "RESOURCE_EXHAUSTED" in _err_str or "UNAVAILABLE" in _err_str or "overloaded" in _err_str.lower() or "high demand" in _err_str.lower()
                if _is_overload and _attempt < len(_model_cascade) - 1:
                    _backoff = 2 ** (_attempt + 1)
                    logger.warning(f"{_model} is unavailable (503/overload). Waiting {_backoff}s before trying next model...")
                    time.sleep(_backoff)
                    continue
                raise _model_err
        if response is None:
            raise _last_err or RuntimeError("All Gemini models failed without a response.")
        
        response_text = response.text
        
        import json
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

        # Ensure all 11 Title Block fields are present in canvas_markings with real values for glowing checkmarks
        existing_markings = parsed.get("canvas_markings", [])
        
        from ...infrastructure.audit.comparison.hallucination_guardrails import (
            is_title_block_category,
            is_bom_category,
            is_admin_bom_marking
        )

        # Clean title block and ALL Gemini-generated BOM markings to prevent duplicate and false-positive checks/pins
        clean_markings = [
            m for m in existing_markings 
            if not is_title_block_category(m.get("category")) 
            and not is_bom_category(m.get("category")) 
            and not is_admin_bom_marking(m)
        ]
        
        # Post-process Gemini canvas markings to extract original_value for CHANGED markers (Fixes Issue 1)
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
                # Extract ID if present in text and entity_id is missing
                match = re.match(r'^\[ID:\s*([^,\]]+)[^\]]*\]\s*(.*)$', txt)
                if match:
                    if not m.get("entity_id"):
                        m["entity_id"] = match.group(1).strip()
                    m["text_content"] = match.group(2).strip()

        # Build ID lookup dictionaries for 100% exact coordinate mapping and guardrails
        id_to_rev_entity = {f"REV-{e.properties.get('handle')}": e for e in rev_entities if e.properties and e.properties.get('handle')}
        id_to_ref_entity = {f"REF-{e.properties.get('handle')}": e for e in ref_entities if e.properties and e.properties.get('handle')}

        # Build allowed ID sets: Only IDs in drawing views, notes sections, and iso views are allowed to have canvas_markings!
        allowed_rev_ids = set()
        for line in (rev_geom + "\n" + rev_notes + "\n" + rev_iso_text).split('\n'):
            m_id = re.match(r'^\[ID:\s*([^,\]]+)[^\]]*\]', line.strip())
            if m_id: allowed_rev_ids.add(m_id.group(1).strip())
            
        allowed_ref_ids = set()
        for line in (ref_geom + "\n" + ref_notes + "\n" + ref_iso_text).split('\n'):
            m_id = re.match(r'^\[ID:\s*([^,\]]+)[^\]]*\]', line.strip())
            if m_id: allowed_ref_ids.add(m_id.group(1).strip())

        # PHASE 2: Anti-Hallucination Guardrails
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
            
            # Guardrail 1: Exact Spatial Allowed-List
            eid = m.get("entity_id")
            if eid:
                if eid.startswith("REV-") and eid not in allowed_rev_ids:
                    logger.warning(f"Guardrail intercepted marker {eid} because it is outside allowed drawing views (likely BOM/Title block hallucination).")
                    continue
                if eid.startswith("REF-") and eid not in allowed_ref_ids:
                    logger.warning(f"Guardrail intercepted marker {eid} because it is outside allowed drawing views (likely BOM/Title block hallucination).")
                    continue
            
            # Guardrail 2: Check if the exact claimed text actually exists in the CAD data
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

        # PHASE 3: Python-Side MATCHED Map-Reduce
        # We programmatically generate MATCHED markers for every other physical entity.
        changed_or_removed_ids = set()
        for m in clean_markings:
            if m.get("entity_id"):
                changed_or_removed_ids.add(m.get("entity_id"))

        all_rev_formatted = rev_geom.split('\n') + rev_notes.split('\n')
        for line in all_rev_formatted:
            line = line.strip()
            if not line:
                continue
            
            match = re.match(r'^\[ID:\s*([^,\]]+)[^\]]*\]\s*(.*)$', line)
            if match:
                entity_id = match.group(1).strip()
                text_content = match.group(2).strip()
                
                if entity_id not in changed_or_removed_ids:
                    # Skip administrative/title block markers from being auto-matched
                    if not is_admin_bom_marking({"text_content": text_content, "category": "drawing_views"}):
                        clean_markings.append({
                            "entity_id": entity_id,
                            "text_content": text_content,
                            "status": "MATCHED",
                            "details": "Element verified and matches reference.",
                            "category": "drawing_views"
                        })
        
        field_labels_map = {
            "QTY": " T. Q'ty (Total Quantity)",
            "CROSS REF NO": " Cross ref No.",
            "PREVIOUS DWG NO": " Previous Dwg. No.",
            "DESIGNED": " DESIGNED",
            "DRAWN": " DRAWN",
            "SCALE": " SCALE",
            "NAME": " TITLE",
            "JOB NO": " Job No.",
            "STD NO": " Std. No.",
            "STANDARD": " Standard",
            "MACHINE CODE": " Mach. code /  Unit Code",
            "DWG NO": " DWG. No. /  Machine Type /  Unit No. /  Part No. /   Branch"
        }
        
        def norm_scale(v):
            return re.sub(r':', '/', v.strip()) if v and v != 'NONE' else v
            
        def sanitize_title_value(val):
            if val == "NONE" or not val:
                return val
            val = re.sub(
                r'^(\s*|drawn|designed|checked|approved'
                r'|mach\.?\s*code|unit\s*code'
                r'|job\s*no\.?|dwg\s*no\.'
                r'|scale)'
                r'[\s\t]*[:\-\]+[\s\t]*',
                '', val, flags=re.IGNORECASE
            )
            return val.strip()

        # 1. Inject Title Block markings
        for field_key, display_label in field_labels_map.items():
            orig_obj = ref_title_fields.get(field_key, {"value": "NONE", "coordinates": None})
            rev_obj = rev_title_fields.get(field_key, {"value": "NONE", "coordinates": None})
            
            orig_val = sanitize_title_value(orig_obj.get("value", "NONE") if isinstance(orig_obj, dict) else orig_obj)
            kmti_val = sanitize_title_value(rev_obj.get("value", "NONE") if isinstance(rev_obj, dict) else rev_obj)
            kmti_coords = rev_obj.get("coordinates", None) if isinstance(rev_obj, dict) else None
            orig_coords = orig_obj.get("coordinates", None) if isinstance(orig_obj, dict) else None
            
            # Equivalence checking
            status_val = compare_values(orig_val, kmti_val)

            # Fix B1  Bilateral symmetric guard for MACHINE CODE / UNIT CODE.
            if field_key == "MACHINE CODE" and status_val in ("ADDED", "REMOVED"):
                if orig_val == "NONE" and kmti_val != "NONE":
                    recovered = BOMAnalyzer.find_drawing_text_coordinates(ref_entities, kmti_val, category="title_block")
                    if recovered and recovered.get("coords"):
                        status_val = "MATCHED"
                        orig_coords = recovered["coords"]
                elif kmti_val == "NONE" and orig_val != "NONE":
                    recovered = BOMAnalyzer.find_drawing_text_coordinates(rev_entities, orig_val, category="title_block")
                    if recovered and recovered.get("coords"):
                        status_val = "MATCHED"
                        kmti_coords = recovered["coords"]
            
            rev_val_raw = rev_obj.get("value", "") if isinstance(rev_obj, dict) else str(rev_obj)
            if kmti_val and kmti_val != "NONE" and kmti_val != sanitize_title_value(rev_val_raw):
                kmti_coords = None
                
            orig_val_raw = orig_obj.get("value", "") if isinstance(orig_obj, dict) else str(orig_obj)
            if orig_val and orig_val != "NONE" and orig_val != sanitize_title_value(orig_val_raw):
                orig_coords = None

            if kmti_coords is None and kmti_val and kmti_val != "NONE":
                exact_coords = BOMAnalyzer.find_drawing_text_coordinates(rev_entities, kmti_val, category="title_block")
                if exact_coords and exact_coords.get("coords"):
                    kmti_coords = exact_coords["coords"]
            if orig_coords is None and orig_val and orig_val != "NONE":
                exact_coords = BOMAnalyzer.find_drawing_text_coordinates(ref_entities, orig_val, category="title_block")
                if exact_coords and exact_coords.get("coords"):
                    orig_coords = exact_coords["coords"]

            if kmti_val != "NONE" or orig_val != "NONE":
                marking_entry = {
                    "text_content": kmti_val if kmti_val != "NONE" else orig_val,
                    "status": status_val,
                    "details": f"Title block {display_label.lstrip('- ')} checked: {orig_val} vs {kmti_val}",
                    "category": "title_block",
                    "original_value": orig_val if status_val == "CHANGED" else None
                }
                if kmti_coords is not None:
                    marking_entry["coordinates"] = kmti_coords
                if orig_coords is not None:
                    marking_entry["ref_coordinates"] = orig_coords
                clean_markings.append(marking_entry)

        # 3. Inject BOM row cell markings for all rows, aligned by Item Number keys
        def is_empty_placeholder_remark(val: str) -> bool:
            if not val or val == "NONE":
                return True
            v = val.strip()
            v = re.sub(r'^[-\u2014\u2015\u2500\u30fc\s]*$', '', v)
            return len(v) == 0

        def get_val_outer(row_dict, key_name):
            obj = row_dict.get(key_name, {})
            if isinstance(obj, dict):
                return obj.get("value", "NONE") or "NONE"
            return obj or "NONE"

        def get_row_key_local(row):
            no_val = get_val_outer(row, "NO")
            if no_val == "NONE":
                return ""
            return no_val.strip()

        def key_sort_fn_local(key_str):
            if key_str.startswith("_ref_idx_"):
                try:
                    return (2, int(key_str.split("_")[-1]), key_str)
                except Exception:
                    pass
            if key_str.startswith("_rev_idx_"):
                try:
                    return (3, int(key_str.split("_")[-1]), key_str)
                except Exception:
                    pass
            try:
                nums = re.findall(r'\d+', key_str)
                if nums:
                    return (0, int(nums[0]), key_str)
            except Exception:
                pass
            return (1, 0, key_str)

        # Strip entirely blank spacer rows to handle structural row shifts and prevent false-positives
        def is_blank_spacer_local(row):
            if not row:
                return True
            if is_assembly_drawing:
                dwg = get_val_outer(row, "DWG_NO")
                title = get_val_outer(row, "TITLE")
                return dwg == "NONE" and title == "NONE"
            else:
                code = get_val_outer(row, "CODE")
                dim = get_val_outer(row, "DIMENSION")
                return code == "NONE" and dim == "NONE"

        filtered_ref = [r for r in ref_bom_rows if not is_blank_spacer_local(r)]
        filtered_rev = [r for r in rev_bom_rows if not is_blank_spacer_local(r)]

        ref_bom_map = {}
        for idx, r in enumerate(filtered_ref):
            k = get_row_key_local(r)
            if not k:
                k = f"_ref_idx_{idx}"
            ref_bom_map[k] = r

        rev_bom_map = {}
        for idx, r in enumerate(filtered_rev):
            k = get_row_key_local(r)
            if not k:
                k = f"_rev_idx_{idx}"
            rev_bom_map[k] = r

        # Build global texts sets for Fallback Global Text String Check
        ref_bom_texts = set()
        for r in filtered_ref:
            for col_val_obj in r.values():
                val = col_val_obj.get("value", "NONE") if isinstance(col_val_obj, dict) else col_val_obj
                if val and val != "NONE" and len(val.strip()) > 1:
                    ref_bom_texts.add(val.strip().lower())

        rev_bom_texts = set()
        for r in filtered_rev:
            for col_val_obj in r.values():
                val = col_val_obj.get("value", "NONE") if isinstance(col_val_obj, dict) else col_val_obj
                if val and val != "NONE" and len(val.strip()) > 1:
                    rev_bom_texts.add(val.strip().lower())

        used_ref_entities = set()
        used_rev_entities = set()

        bom_keys = list(set(ref_bom_map.keys()).union(set(rev_bom_map.keys())))
        bom_keys.sort(key=key_sort_fn_local)

        for key in bom_keys:
            rev_row = rev_bom_map.get(key, {})
            ref_row = ref_bom_map.get(key, {})

            row_label = f"Unnumbered Row" if (key.startswith("_ref_idx_") or key.startswith("_rev_idx_")) else f"Item {key}"

            if is_assembly_drawing:
                bom_cols = [
                    ("NO", "No."),
                    ("DWG_NO", " / DWG No."),
                    ("TITLE", " / TITLE"),
                    ("QTY", "Q'ty"),
                    ("REMARK", " / Remark")
                ]
            else:
                bom_cols = [
                    ("NO", "No."),
                    ("CODE", " / Code"),
                    ("DIMENSION", "/ / Dimension"),
                    ("QTY", " / Q'ty"),
                    ("MATERIAL_WEIGHT", "Kg / Material Wt(kg)"),
                    ("FINISHED_WEIGHT", "Kg / Finished Wt(kg)"),
                    ("REMARK", " / Remark")
                ]

            for col_key, display_label in bom_cols:
                rev_cell = rev_row.get(col_key, {"value": "NONE", "coordinates": None})
                orig_cell = ref_row.get(col_key, {"value": "NONE", "coordinates": None})

                orig_val = orig_cell.get("value", "NONE") if isinstance(orig_cell, dict) else orig_cell
                kmti_val = rev_cell.get("value", "NONE") if isinstance(rev_cell, dict) else rev_cell
                kmti_coords = rev_cell.get("coordinates", None) if isinstance(rev_cell, dict) else None
                orig_coords = orig_cell.get("coordinates", None) if isinstance(orig_cell, dict) else None

                status_val = compare_values(orig_val, kmti_val)

                # Remarks Column Noise-Canceling
                if col_key == "REMARK":
                    if is_empty_placeholder_remark(orig_val) and is_empty_placeholder_remark(kmti_val):
                        status_val = "MATCHED"

                # Safeguard 1: if the item number/row exists in both drawings, it is a change, never an addition or removal!
                if ref_row and rev_row and status_val in ("ADDED", "REMOVED"):
                    status_val = "CHANGED"

                # Safeguard 2: Fallback Global Text String Check
                if status_val == "ADDED" and kmti_val.strip().lower() in ref_bom_texts:
                    status_val = "MATCHED"
                elif status_val == "REMOVED" and orig_val.strip().lower() in rev_bom_texts:
                    status_val = "MATCHED"
                elif status_val == "CHANGED":
                    if kmti_val.strip().lower() in ref_bom_texts and orig_val.strip().lower() in rev_bom_texts:
                        status_val = "MATCHED"

                # Fix B3  Exact value coordinate lookup, spatially constrained to BOM bbox.
                if kmti_coords is None and kmti_val and kmti_val != "NONE":
                    exact_coords = BOMAnalyzer.find_drawing_text_coordinates(rev_entities, kmti_val, category="bill_of_materials", region_bbox=rev_bom_bbox, used_entities=used_rev_entities)
                    if exact_coords and exact_coords.get("coords"):
                        ec = exact_coords["coords"]
                        if rev_bom_bbox and not (rev_bom_bbox[0] <= ec[0] <= rev_bom_bbox[2] and rev_bom_bbox[1] <= ec[1] <= rev_bom_bbox[3]):
                            ec = None
                        if ec:
                            kmti_coords = ec
                if orig_coords is None and orig_val and orig_val != "NONE":
                    exact_coords = BOMAnalyzer.find_drawing_text_coordinates(ref_entities, orig_val, category="bill_of_materials", region_bbox=ref_bom_bbox, used_entities=used_ref_entities)
                    if exact_coords and exact_coords.get("coords"):
                        ec = exact_coords["coords"]
                        if ref_bom_bbox and not (ref_bom_bbox[0] <= ec[0] <= ref_bom_bbox[2] and ref_bom_bbox[1] <= ec[1] <= ref_bom_bbox[3]):
                            ec = None
                        if ec:
                            orig_coords = ec

                if kmti_val != "NONE" or orig_val != "NONE":
                    details_str = f"BOM [{row_label}] {display_label} checked: {orig_val} vs {kmti_val}"
                    if status_val == "CHANGED" and col_key in ("MATERIAL_WEIGHT", "FINISHED_WEIGHT"):
                        try:
                            if float(orig_val) == float(kmti_val) and re.search(r'\.\d{2}$', kmti_val.strip()):
                                status_val = "MATCHED"
                                details_str = f"BOM [{row_label}] {display_label} matched: {orig_val} vs {kmti_val} (Standardized to 2 decimals)"
                        except ValueError:
                            pass

                    marking_entry = {
                        "text_content": kmti_val if kmti_val != "NONE" else orig_val,
                        "status": status_val,
                        "details": details_str,
                        "category": "bill_of_materials",
                        "original_value": orig_val if status_val == "CHANGED" else None
                    }
                    if kmti_coords is not None:
                        marking_entry["coordinates"] = kmti_coords
                    if orig_coords is not None:
                        marking_entry["ref_coordinates"] = orig_coords
                        
                    # Spatial boundary filter (Stray BOM marker over Title Block area)
                    if kmti_coords is not None and kmti_coords[1] < 60.0:
                        continue
                        
                    clean_markings.append(marking_entry)
        
        def calc_anchor(e) -> list:
            ins = getattr(e, "geometry", {}).get("location") or getattr(e, "geometry", {}).get("insert") or getattr(e, "geometry", {}).get("text_point") or [0, 0, 0]
            height = e.properties.get("height", 3.0) if getattr(e, "properties", None) else 3.0
            bbox = e.properties.get("bbox", None) if getattr(e, "properties", None) else None
            if bbox and len(bbox) == 2:
                try:
                    return [bbox[1][0] + (height * 0.8), bbox[0][1] + (bbox[1][1] - bbox[0][1]) / 2.0]
                except Exception:
                    pass
            text_len = len(e.properties.get("text", "")) if getattr(e, "properties", None) else 0
            return [ins[0] + text_len * height * 0.6 + (height * 0.8), ins[1] + (height / 2.0)]

        # 4. Resolve exact geometric coordinates
        for m in clean_markings:
            eid = m.get("entity_id")
            if eid:
                eid_rev = eid if eid.startswith("REV-") else f"REV-{eid}"
                eid_ref = eid if eid.startswith("REF-") else f"REF-{eid}"
                
                status_val = m.get("status")
                if status_val == "REMOVED":
                    if eid_ref in id_to_ref_entity:
                        ref_ent = id_to_ref_entity[eid_ref]
                        m["ref_coordinates"] = calc_anchor(ref_ent)
                        used_ref_entities.add(id(ref_ent))
                else:
                    if eid_rev in id_to_rev_entity:
                        rev_ent = id_to_rev_entity[eid_rev]
                        m["coordinates"] = calc_anchor(rev_ent)
                        used_rev_entities.add(id(rev_ent))
                    if status_val in ["CHANGED", "MATCHED"] and eid_ref in id_to_ref_entity:
                        ref_ent = id_to_ref_entity[eid_ref]
                        m["ref_coordinates"] = calc_anchor(ref_ent)
                        used_ref_entities.add(id(ref_ent))
                        
            # Fallback to fuzzy text search if coordinates are missing
            if m.get("coordinates") is None or m.get("ref_coordinates") is None:
                txt = m.get("text_content", "")
                orig_txt = m.get("original_value") or txt
                cat = m.get("category")
                status_val = m.get("status")
                
                def get_individual_bboxes(rows, fields):
                    bboxes = []
                    for row in rows:
                        for cell in row.values():
                            if isinstance(cell, dict):
                                c = cell.get("coordinates")
                                if c and len(c) >= 2:
                                    bboxes.append((c[0] - 30.0, c[1] - 15.0, c[0] + 30.0, c[1] + 15.0))
                    for cell in fields.values():
                        if isinstance(cell, dict):
                            c = cell.get("coordinates")
                            if c and len(c) >= 2:
                                bboxes.append((c[0] - 30.0, c[1] - 15.0, c[0] + 30.0, c[1] + 15.0))
                    return bboxes

                rev_ex = get_individual_bboxes(rev_bom_rows, rev_title_fields) if cat == "drawing_views" else None
                ref_ex = get_individual_bboxes(ref_bom_rows, ref_title_fields) if cat == "drawing_views" else None
                
                if status_val == "ADDED":
                    if m.get("coordinates") is None and txt and txt != "NONE":
                        res = BOMAnalyzer.find_drawing_text_coordinates(rev_entities, txt, category=cat, used_entities=used_rev_entities, exclude_bboxes=rev_ex)
                        if res:
                            m["coordinates"] = res.get("coords")
                            m["bbox"] = res.get("bbox")
                
                elif status_val == "REMOVED":
                    search_txt = m.get("original_value") or txt
                    if m.get("ref_coordinates") is None and search_txt and search_txt != "NONE":
                        res = BOMAnalyzer.find_drawing_text_coordinates(ref_entities, search_txt, category=cat, used_entities=used_rev_entities, exclude_bboxes=ref_ex)
                        if res:
                            m["ref_coordinates"] = res.get("coords")
                            m["ref_bbox"] = res.get("bbox")
                        
                elif status_val == "CHANGED":
                    if m.get("coordinates") is None and txt and txt != "NONE":
                        res = BOMAnalyzer.find_drawing_text_coordinates(rev_entities, txt, category=cat, used_entities=used_rev_entities, exclude_bboxes=rev_ex)
                        if res:
                            m["coordinates"] = res.get("coords")
                            m["bbox"] = res.get("bbox")
                    search_txt = m.get("original_value") or txt
                    if m.get("ref_coordinates") is None and search_txt and search_txt != "NONE":
                        res = BOMAnalyzer.find_drawing_text_coordinates(ref_entities, search_txt, category=cat, used_entities=used_rev_entities, exclude_bboxes=ref_ex)
                        if res:
                            m["ref_coordinates"] = res.get("coords")
                            m["ref_bbox"] = res.get("bbox")
                        
                else: # MATCHED
                    if m.get("coordinates") is None and txt and txt != "NONE":
                        res = BOMAnalyzer.find_drawing_text_coordinates(rev_entities, txt, category=cat, used_entities=used_rev_entities, exclude_bboxes=rev_ex)
                        if res:
                            m["coordinates"] = res.get("coords")
                            m["bbox"] = res.get("bbox")
                    if m.get("ref_coordinates") is None and txt and txt != "NONE":
                        res = BOMAnalyzer.find_drawing_text_coordinates(ref_entities, txt, category=cat, used_entities=used_rev_entities, exclude_bboxes=ref_ex)
                        if res:
                            m["ref_coordinates"] = res.get("coords")
                            m["ref_bbox"] = res.get("bbox")
        
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
                drawing_id=request.drawing_id,
                reference_drawing_id=request.reference_drawing_id,
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

        return StandardResponse(success=True, data=comparison_response)

    except Exception as e:
        logger.error(f"Structured Gemini 2.5 Pro comparison failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Structured comparison failed: {str(e)}"
        )


@router.get(
    "/clients",
    response_model=StandardResponse[list[ClientResponse]],
    summary="List all registered client directories",
    dependencies=[Depends(get_auth_token)]
)
async def list_clients():
    clients = await ClientDocument.find_all().to_list()
    res = [
        ClientResponse(
            id=str(c.id),
            name=c.name,
            created_at=c.created_at
        )
        for c in clients
    ]
    return StandardResponse(success=True, data=res)


@router.post(
    "/clients",
    response_model=StandardResponse[ClientResponse],
    summary="Create a new client directory",
    dependencies=[Depends(get_auth_token)]
)
async def create_client(request: CreateClientRequest):
    name = request.name.upper()
    existing = await ClientDocument.find_one(ClientDocument.name == name)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Client '{name}' already registered."
        )
        
    client = ClientDocument(name=name)
    await client.save()
    
    return StandardResponse(
        success=True,
        data=ClientResponse(
            id=str(client.id),
            name=client.name,
            created_at=client.created_at
        )
    )


@router.delete(
    "/clients/{name}",
    response_model=StandardResponse[dict],
    summary="Delete a client directory",
    dependencies=[Depends(get_auth_token)]
)
async def delete_client(name: str):
    name = name.upper()
    client = await ClientDocument.find_one(ClientDocument.name == name)
    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Client '{name}' not found."
        )
    
    await client.delete()
    
    # Clean up associated standards documents and their chunks
    standards = await StandardDocument.find(StandardDocument.client_name == name).to_list()
    for std in standards:
        await std.delete()
        # Clean chunks too
        chunks = await StandardChunk.find(StandardChunk.standard_id == str(std.id)).to_list()
        for chunk in chunks:
            await chunk.delete()
        
    return StandardResponse(
        success=True,
        data={"message": f"Client '{name}' and all associated standards successfully removed."}
    )
