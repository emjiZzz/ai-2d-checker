import asyncio
import json
import os
import time
import re
import aiofiles
from datetime import datetime, timezone, UTC
from typing import Optional
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status, Header, Form
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from google import genai
from google.genai import types

from ...domain.models.annotation_document import AnnotationDocument
from ...domain.models.audit_session import AuditSession
from ...domain.models.audit_violation import AuditViolation
from ...domain.models.drawing_document import DrawingDocument
from ...domain.models.extracted_entity import ExtractedEntity
from ...domain.models.client import ClientDocument
from ...domain.models.standard_document import StandardDocument
from ...domain.models.standard_chunk import StandardChunk
from ...infrastructure.audit.audit_pipeline import audit_queue
from ...infrastructure.cad.redline_writer import RedlineWriter, build_findings
from ...infrastructure.cad.viewport_transform import ViewportTransform
from ...infrastructure.storage.path_resolver import get_storage_root
from ...infrastructure.audit.report_generator import ReportGenerator
from ...infrastructure.utils.text import (
    safe_decode,
    strip_mtext,
    compare_values,
    extract_semantic_text_groups,
    build_title_block_table,
)
from ...logger import logger, correlation_id_var
from ...config import settings
from ..dependencies import get_auth_token, get_or_404
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
    AuditFeedbackRequest,
    AuditFeedbackResponse,
    CategoryComparison,
    CanvasMarking,
)

router = APIRouter()

# Strong references to in-flight SSE comparison tasks — see stream_physical_comparison.
_COMPARISON_STREAM_TASKS: set[asyncio.Task] = set()


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
            from ...core.auth import verify_session_token
            payload = verify_session_token(x_session_token)
            username = payload.get("username")
    except Exception:
        pass

    drawing = await get_or_404(
        DrawingDocument, request.drawing_id, f"Drawing document not found: {request.drawing_id}"
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
    session = await get_or_404(AuditSession, id, f"Audit session not found: {id}")
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
async def delete_audit_session(
    id: str,
    token: str = Depends(get_auth_token),
    x_session_token: str | None = Header(None, alias="X-Session-Token")
):
    """
    Soft deletes the specified audit session from MongoDB.
    """
    session = await get_or_404(AuditSession, id, f"Audit session not found: {id}")

    username = None
    try:
        if x_session_token:
            from ...core.auth import verify_session_token
            payload = verify_session_token(x_session_token)
            username = payload.get("username")
    except Exception:
        pass
    
    session.is_deleted = True
    session.deleted_at = datetime.now(timezone.utc)
    session.deleted_by = username
    await session.save()
    
    # Invalidate cache for associated drawings to prevent stale comparison results
    from ...infrastructure.audit.comparison.cache_manager import ComparisonCacheManager
    if session.drawing_id:
        ComparisonCacheManager.clear_cache_for_drawing(session.drawing_id)
    if session.reference_drawing_id:
        ComparisonCacheManager.clear_cache_for_drawing(session.reference_drawing_id)
    
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
    violation = await get_or_404(AuditViolation, id, "Audit violation not found.")

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
    "/reports/{session_id}/redline.dxf",
    summary="Export audit findings as a redline layer in a copy of the source DXF",
    dependencies=[Depends(get_auth_token)]
)
async def export_redline_dxf(session_id: str):
    """Write this session's findings into a new layer on a copy of the source drawing.

    The original file is never modified and never rebuilt from extracted entities: it is
    opened, one layer is added, and the result is saved elsewhere. Everything the
    extraction does not capture therefore survives untouched.

    DXF sources only. A DWG-sourced drawing would need the ODA converter on the write
    path, which is deliberately not a dependency here.
    """
    session = await get_or_404(AuditSession, session_id, f"Audit session not found: {session_id}")
    drawing = await get_or_404(
        DrawingDocument, session.drawing_id, f"Drawing not found for session: {session_id}"
    )

    if (drawing.format or "").lower() != "dxf":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Redline export requires a DXF source; this drawing is '{drawing.format}'. "
                "DWG export is not currently supported."
            ),
        )

    source_path = get_storage_root() / drawing.file_path
    if not source_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Source drawing file is no longer present on disk.",
        )

    violations = await AuditViolation.find(AuditViolation.audit_session_id == session_id).to_list()
    annotations = await AnnotationDocument.find(
        AnnotationDocument.drawing_id == session.drawing_id
    ).to_list()

    findings = build_findings(violations, annotations)
    if not findings:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="This session has no findings with coordinates to redline.",
        )

    transform = ViewportTransform.from_dict((drawing.metadata or {}).get("viewport_transform"))
    output_path = get_storage_root() / "redlines" / f"redline_{session_id}.dxf"

    try:
        writer = RedlineWriter(source_path, transform)
        summary = await asyncio.to_thread(writer.write, findings, session_id, output_path)
    except Exception as err:
        corr_id = correlation_id_var.get()
        logger.exception(f"[{corr_id}] Redline export failed for session {session_id}: {err}")
        raise HTTPException(
            status_code=500, detail=f"Redline export failed. Reference: {corr_id}"
        )

    logger.info(f"Redline export for session {session_id}: {summary}")
    return FileResponse(
        str(output_path),
        media_type="application/dxf",
        filename=f"AI-2D-Checker_Redline_{session_id}.dxf",
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
        corr_id = correlation_id_var.get()
        logger.exception(f"[{corr_id}] Failed to compile report for session {session_id}: {str(err)}")
        raise HTTPException(status_code=500, detail=f"PDF compilation failed. Reference: {corr_id}")


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
        corr_id = correlation_id_var.get()
        logger.exception(f"[{corr_id}] Failed to compile Excel report for session {session_id}: {str(err)}")
        raise HTTPException(status_code=500, detail=f"XLSX export failed. Reference: {corr_id}")


async def _load_comparison_inputs(request: PhysicalComparisonRequest):
    """Shared preamble for both comparison endpoints: the two drawings and their entities."""
    ref_drawing = await get_or_404(
        DrawingDocument, request.reference_drawing_id, "Reference drawing not found."
    )
    rev_drawing = await get_or_404(
        DrawingDocument, request.drawing_id, "Revised drawing not found."
    )

    ref_entities = await ExtractedEntity.find(ExtractedEntity.drawing_id == request.reference_drawing_id).to_list()
    rev_entities = await ExtractedEntity.find(ExtractedEntity.drawing_id == request.drawing_id).to_list()

    return ref_drawing, rev_drawing, ref_entities, rev_entities


async def _dispatch_comparison(
    request: PhysicalComparisonRequest,
    ref_drawing, rev_drawing, ref_entities, rev_entities,
    method: str,
    progress_callback=None,
) -> PhysicalComparisonResponse:
    """Routes a comparison_method to its orchestrator.

    Single source of truth for the routing table, because the streaming and non-streaming
    endpoints must agree on which method maps to which engine — two copies would let one
    silently serve a different engine than the other for the same room.
    """
    if method in ("rag_ai", "ai_vision"):
        from ...infrastructure.audit.comparison.full_ai_orchestrator import perform_full_ai_comparison
        return await perform_full_ai_comparison(
            request, ref_drawing, rev_drawing, ref_entities, rev_entities,
            method=method, progress_callback=progress_callback,
        )
    if method == "hybrid":
        from ...infrastructure.audit.comparison.hybrid_orchestrator import perform_hybrid_comparison
        return await perform_hybrid_comparison(
            request, ref_drawing, rev_drawing, ref_entities, rev_entities,
            progress_callback=progress_callback,
        )
    from ...infrastructure.audit.comparison.orchestrator import perform_drawing_comparison
    return await perform_drawing_comparison(
        request, ref_drawing, rev_drawing, ref_entities, rev_entities,
        progress_callback=progress_callback,
    )


@router.post(
    "/audits/physical-comparison",
    response_model=StandardResponse[PhysicalComparisonResponse],
    summary="Perform dynamic AI-grounded engineering physical comparison of drawing files",
    dependencies=[Depends(get_auth_token)]
)
async def perform_physical_comparison(request: PhysicalComparisonRequest):
    ref_drawing, rev_drawing, ref_entities, rev_entities = await _load_comparison_inputs(request)

    method = getattr(request, "comparison_method", "rag")
    logger.info(f"Physical comparison dispatched with method='{method}' for drawing {request.drawing_id}")

    try:
        comparison_response = await _dispatch_comparison(
            request, ref_drawing, rev_drawing, ref_entities, rev_entities, method
        )
        return StandardResponse(success=True, data=comparison_response)
    except ValueError as val_err:
        logger.warning(f"Comparison configuration error: {val_err}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Gemini API Key is not configured. Please supply a valid GEMINI_API_KEY inside the system environment."
        )
    except Exception as e:
        corr_id = correlation_id_var.get()
        logger.error(f"[{corr_id}] Structured comparison failed ({method}): {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Structured comparison failed. Reference: {corr_id}"
        )


@router.post(
    "/audits/physical-comparison/stream",
    summary="Stream live real-time SSE progress events for AI physical drawing comparison",
    dependencies=[Depends(get_auth_token)]
)
async def stream_physical_comparison(request: PhysicalComparisonRequest):
    ref_drawing, rev_drawing, ref_entities, rev_entities = await _load_comparison_inputs(request)

    method = getattr(request, "comparison_method", "rag")
    logger.info(f"Physical comparison stream dispatched with method='{method}' for drawing {request.drawing_id}")

    async def event_generator():
        queue: asyncio.Queue = asyncio.Queue()

        async def progress_callback(stage: str, progress_pct: int, label: str = ""):
            await queue.put({
                "type": "progress",
                "stage": stage,
                "progress_pct": progress_pct,
                "label": label
            })

        async def run_task():
            try:
                comparison_response = await _dispatch_comparison(
                    request, ref_drawing, rev_drawing, ref_entities, rev_entities,
                    method, progress_callback=progress_callback,
                )
                await queue.put({
                    "type": "complete",
                    "stage": "completed",
                    "progress_pct": 100,
                    "result": comparison_response.model_dump()
                })
            except Exception as e:
                corr_id = correlation_id_var.get()
                logger.error(f"[{corr_id}] Structured comparison stream failed ({method}): {str(e)}", exc_info=True)
                await queue.put({
                    "type": "error",
                    "error": str(e)
                })

        # Held in a module-level set until it completes. asyncio only keeps a weak reference
        # to a running task, so a bare create_task() here can be garbage-collected mid-run and
        # the stream would hang on an empty queue forever. Deliberately NOT cancelled when the
        # client disconnects: a comparison is expensive and writes its own cache entry, so
        # letting an abandoned run finish means the user's retry is a cache hit.
        task = asyncio.create_task(run_task())
        _COMPARISON_STREAM_TASKS.add(task)
        task.add_done_callback(_COMPARISON_STREAM_TASKS.discard)

        while True:
            item = await queue.get()
            if item["type"] in ("progress", "complete", "error"):
                yield f"data: {json.dumps(item)}\n\n"
            if item["type"] in ("complete", "error"):
                break

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.post(
    "/audits/feedback",
    response_model=StandardResponse[AuditFeedbackResponse],
    summary="Submit human engineer feedback and trigger active learning auto-documentation",
    dependencies=[Depends(get_auth_token)]
)
async def submit_audit_feedback(request: AuditFeedbackRequest, background_tasks: BackgroundTasks):
    from ...domain.models.audit_feedback import AuditFeedbackDocument
    from ...infrastructure.knowledge.auto_doc import AutoDocEngine

    feedback_doc = AuditFeedbackDocument(
        session_id=request.session_id,
        drawing_id=request.drawing_id,
        client_name=request.client_name,
        entity_text=request.entity_text,
        entity_handle=request.entity_handle,
        category=request.category,
        original_status=request.original_status,
        human_corrected_status=request.human_corrected_status,
        human_comment=request.human_comment,
        coordinates=request.coordinates,
        corrected_category=request.corrected_category,
        corrected_value=request.corrected_value,
        finding_snapshot=request.finding_snapshot.model_dump() if request.finding_snapshot else None,
    )
    await feedback_doc.save()

    # Trigger active learning auto-documentation engine (Pillar 3) — the legacy vault
    # dismissal path, kept as complementary suppression.
    was_auto_documented = await AutoDocEngine.process_feedback_event(feedback_doc)

    # Retrain the learned-correction model off the request path so the response stays fast.
    # Cheap (LogisticRegression on a few hundred rows) and idempotent; the model reload is
    # in-process so the very next comparison sees the update.
    from ...infrastructure.learning.trainer import train_from_feedback
    background_tasks.add_task(train_from_feedback)

    res = AuditFeedbackResponse(
        id=str(feedback_doc.id),
        status="recorded",
        auto_documented=was_auto_documented,
        message="Human feedback recorded successfully." + (" Auto-documented new learned rule to Obsidian Vault!" if was_auto_documented else "")
    )
    return StandardResponse(success=True, data=res)


@router.post(
    "/audits/learning/retrain",
    response_model=StandardResponse[dict],
    summary="Force an immediate retrain of the learned-correction model from human feedback",
    dependencies=[Depends(get_auth_token)],
)
async def retrain_learned_model():
    from ...infrastructure.learning.trainer import train_from_feedback
    try:
        result = await train_from_feedback()
        return StandardResponse(success=True, data=result)
    except Exception as e:
        corr_id = correlation_id_var.get()
        logger.error(f"[{corr_id}] Learned-model retrain failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Retrain failed. Reference: {corr_id}")


@router.get(
    "/audits/learning/status",
    response_model=StandardResponse[dict],
    summary="Report learned-correction model status: corrections count, readiness, metrics",
    dependencies=[Depends(get_auth_token)],
)
async def learned_model_status():
    from ...infrastructure.learning.model_holder import LearnedModelHolder
    return StandardResponse(success=True, data=LearnedModelHolder.get_instance().status())


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
