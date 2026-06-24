# -*- coding: utf-8 -*-
import time
import os
import uuid
import hashlib
import re
import aiofiles
from google import genai
from google.genai import types
from pathlib import Path
from fastapi import APIRouter, Depends, status, HTTPException, File, UploadFile, Form, Header
from fastapi.responses import FileResponse
from typing import List, Optional
from .dependencies import get_auth_token
from ..infrastructure.audit.report_generator import ReportGenerator
from .schemas import (
    StandardResponse,
    SystemStatusResponse,
    DatabaseHealthDetails,
    StorageHealthDetails,
    DrawingResponse,
    JobResponse,
    UploadResponse,
    StandardDocumentResponse,
    LaunchAuditRequest,
    AuditSessionResponse,
    UpdateAuditSessionRequest,
    AuditViolationResponse,
    ClientResponse,
    CreateClientRequest,
    PhysicalComparisonRequest,
    PhysicalComparisonResponse,
    CategoryComparison,
    CanvasMarking
)
from ..infrastructure.database.health import check_database_health
from ..infrastructure.storage.storage_health import get_storage_diagnostics
from ..infrastructure.storage.cleanup import purge_temp_files, purge_cache_files
from ..infrastructure.storage.path_resolver import get_storage_root
from ..core.security import validate_sandboxed_path
from ..infrastructure.cad.processing_queue import processing_queue
from ..infrastructure.cad.diagnostics import CADDiagnostics
from ..domain.models.drawing_document import DrawingDocument
from ..domain.models.extraction_job import ExtractionJob
from ..domain.models.standard_document import StandardDocument
from ..domain.models.standard_chunk import StandardChunk
from ..domain.models.audit_session import AuditSession
from ..domain.models.audit_violation import AuditViolation
from ..domain.models.extracted_entity import ExtractedEntity
from ..domain.models.client import ClientDocument
from ..infrastructure.rendering.geometry_serializer import GeometrySerializer
from ..infrastructure.audit.standards_loader import StandardsLoader
from ..infrastructure.audit.audit_pipeline import audit_queue
from ..infrastructure.audit.diagnostics import AuditDiagnostics
from ..config import settings
from ..logger import logger

router = APIRouter(prefix="/api/v1")

@router.get(
    "/health",
    response_model=StandardResponse[SystemStatusResponse],
    summary="Global health status checker"
)
async def global_health():
    """
    Diagnostic healthcheck endpoint. Returns system and sidecar status details.
    Does not require authentication to allow the frontend connection manager to check connectivity.
    """
    db_health = await check_database_health()
    storage_diag = get_storage_diagnostics()
    
    return StandardResponse(
        success=True,
        data=SystemStatusResponse(
            status="healthy" if db_health["connected"] and storage_diag["write_permission"] else "degraded",
            version=settings.VERSION,
            name=settings.PROJECT_NAME,
            timestamp=time.time()
        )
    )

@router.get(
    "/system/database",
    response_model=StandardResponse[DatabaseHealthDetails],
    summary="Retrieve detailed MongoDB health diagnostics",
    dependencies=[Depends(get_auth_token)]
)
async def database_health():
    """
    Requires active local API Token authorization.
    Runs direct loopback diagnostic pings and returns schema status.
    """
    health = await check_database_health()
    
    if health["status"] == "unreachable":
        return StandardResponse(
            success=False,
            error={
                "code": "DATABASE_UNREACHABLE",
                "message": "The local MongoDB server is offline or unreachable.",
                "detail": health.get("error")
            }
        )
        
    return StandardResponse(
        success=True,
        data=DatabaseHealthDetails(
            status=health["status"],
            latency_ms=health["latency_ms"],
            connected=health["connected"],
            database_name=health.get("database_name"),
            error=health.get("error")
        )
    )

@router.get(
    "/system/storage",
    response_model=StandardResponse[StorageHealthDetails],
    summary="Retrieve storage system diagnostics",
    dependencies=[Depends(get_auth_token)]
)
async def storage_health():
    """
    Requires active local API Token authorization.
    Returns directories structure, file counts, and disk capacity sizes.
    """
    diag = get_storage_diagnostics()
    
    if diag["status"] == "unreachable" or not diag["write_permission"]:
        return StandardResponse(
            success=False,
            error={
                "code": "STORAGE_INTEGRITY_FAILED",
                "message": "Storage system bootstrap verification failed.",
                "detail": diag.get("error")
            }
        )
        
    return StandardResponse(
        success=True,
        data=StorageHealthDetails(
            status=diag["status"],
            write_permission=diag["write_permission"],
            storage_root=diag["storage_root"],
            disk_usage=diag["disk_usage"],
            directories=diag["directories"],
            error=diag.get("error")
        )
    )

@router.post(
    "/system/storage/cleanup",
    response_model=StandardResponse[dict],
    summary="Manually trigger temporary file and cache storage purging",
    dependencies=[Depends(get_auth_token)]
)
async def trigger_storage_cleanup(max_age_seconds: int = 86400):
    """
    Requires active local API Token authorization.
    Flushes temp files older than specified age and clears the cache directory.
    """
    try:
        temp_metrics = purge_temp_files(max_age_seconds=max_age_seconds)
        cache_metrics = purge_cache_files()
        
        combined_metrics = {
            "temp_purged": temp_metrics,
            "cache_purged": cache_metrics
        }
        return StandardResponse(
            success=True,
            data=combined_metrics
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Storage cleanup execution failed: {str(e)}"
        )


@router.post(
    "/drawings/upload",
    response_model=StandardResponse[UploadResponse],
    summary="Upload a local CAD drawing (DWG or DXF) and trigger parsing",
    dependencies=[Depends(get_auth_token)]
)
async def upload_drawing(file: UploadFile = File(...)):
    """
    Enforces local secure authorization, checks file extension limits, streams file,
    computes SHA-256 hash, and queues it for background ODA/DXF extraction.
    """
    filename = file.filename or ""
    file_ext = filename.split(".")[-1].lower() if "." in filename else ""
    
    if file_ext not in ("dwg", "dxf", "pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported file format. Only proprietary .dwg, open .dxf drawings, or .pdf files are accepted."
        )

    # Stream upload to temp folder within the secure sandbox
    sha256 = hashlib.sha256()
    total_size = 0
    temp_filename = f"upload_{uuid.uuid4().hex}.tmp"
    temp_upload_path = get_storage_root() / "temp" / temp_filename
    
    try:
        async with aiofiles.open(temp_upload_path, "wb") as out_file:
            while chunk := await file.read(1024 * 1024):  # 1MB buffer
                total_size += len(chunk)
                if total_size > settings.MAX_FILE_SIZE_MB * 1024 * 1024:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"Drawing file size exceeds maximum limit of {settings.MAX_FILE_SIZE_MB}MB."
                    )
                sha256.update(chunk)
                await out_file.write(chunk)
    except Exception as e:
        if temp_upload_path.exists():
            try:
                temp_upload_path.unlink()
            except Exception:
                pass
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Drawing upload failed: {str(e)}"
        )

    file_hash = sha256.hexdigest()
    
    # Check for duplicate Drawing hash in database
    existing_drawing = await DrawingDocument.find_one(DrawingDocument.file_hash == file_hash)
    if existing_drawing:
        # We need to overwrite the secure filename and update the document, just in case the previous ingestion left it in a broken state
        secure_filename = f"{file_hash}.{file_ext}"
        final_upload_path = get_storage_root() / "uploads" / secure_filename
        
        try:
            # Move the new temp file to the secure location (overwriting if exists)
            if final_upload_path.exists():
                final_upload_path.unlink()
            temp_upload_path.rename(final_upload_path)
        except Exception:
            # If rename fails, the original file might still be there, just delete the temp file
            try:
                temp_upload_path.unlink()
            except Exception:
                pass

        # Force re-ingestion: Clear stale extracted entities to ensure fresh parsing logic is executed
        await ExtractedEntity.find(ExtractedEntity.drawing_id == str(existing_drawing.id)).delete()
        
        # Reset the drawing record properties for a clean extraction run
        existing_drawing.status = "queued"
        existing_drawing.entity_counts = {}
        existing_drawing.metadata = {}
        existing_drawing.file_path = f"uploads/{secure_filename}"
        existing_drawing.format = file_ext
        await existing_drawing.save()
            
        # Create a fresh extraction job
        existing_job = ExtractionJob(drawing_id=str(existing_drawing.id), status="queued")
        await existing_job.save()
        
        # Queue the drawing for fresh ODA conversion and DXF layout/block explosion parsing
        await processing_queue.enqueue(str(existing_drawing.id), str(existing_job.id))
            
        return StandardResponse(
            success=True,
            data=UploadResponse(
                drawing=DrawingResponse(
                    id=str(existing_drawing.id),
                    file_name=existing_drawing.file_name,
                    file_path=existing_drawing.file_path,
                    file_hash=existing_drawing.file_hash,
                    file_size_bytes=existing_drawing.file_size_bytes,
                    format=existing_drawing.format,
                    status=existing_drawing.status,
                    entity_counts=existing_drawing.entity_counts,
                    metadata=existing_drawing.metadata,
                    created_at=existing_drawing.created_at,
                    updated_at=existing_drawing.updated_at
                ),
                job=JobResponse(
                    id=str(existing_job.id),
                    drawing_id=existing_job.drawing_id,
                    status=existing_job.status,
                    error_message=existing_job.error_message,
                    diagnostics=existing_job.diagnostics,
                    conversion_duration_seconds=existing_job.conversion_duration_seconds,
                    parsing_duration_seconds=existing_job.parsing_duration_seconds,
                    total_duration_seconds=existing_job.total_duration_seconds,
                    created_at=existing_job.created_at,
                    started_at=existing_job.started_at,
                    completed_at=existing_job.completed_at
                ),
                is_duplicate=True
            )
        )

    # Secure persistent placement inside storage/uploads sandbox
    secure_filename = f"{file_hash}.{file_ext}"
    final_upload_path = get_storage_root() / "uploads" / secure_filename
    
    try:
        # Move temporary file to final sandboxed target path
        if final_upload_path.exists():
            final_upload_path.unlink()
        temp_upload_path.rename(final_upload_path)
    except Exception as e:
        if temp_upload_path.exists():
            try:
                temp_upload_path.unlink()
            except Exception:
                pass
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to securely store uploaded drawing: {str(e)}"
        )

    # Normalize relative path inside workspace storage root
    relative_path = os.path.relpath(final_upload_path, get_storage_root())

    drawing = DrawingDocument(
        file_name=filename,
        file_path=relative_path,
        file_hash=file_hash,
        file_size_bytes=total_size,
        format=file_ext,
        status="queued"
    )
    await drawing.save()

    job = ExtractionJob(drawing_id=str(drawing.id), status="queued")
    await job.save()

    # Enqueue task for background thread parsing
    await processing_queue.enqueue(str(drawing.id), str(job.id))

    return StandardResponse(
        success=True,
        data=UploadResponse(
            drawing=DrawingResponse(
                id=str(drawing.id),
                file_name=drawing.file_name,
                file_path=drawing.file_path,
                file_hash=drawing.file_hash,
                file_size_bytes=drawing.file_size_bytes,
                format=drawing.format,
                status=drawing.status,
                entity_counts=drawing.entity_counts,
                metadata=drawing.metadata,
                created_at=drawing.created_at,
                updated_at=drawing.updated_at
            ),
            job=JobResponse(
                id=str(job.id),
                drawing_id=job.drawing_id,
                status=job.status,
                error_message=job.error_message,
                diagnostics=job.diagnostics,
                conversion_duration_seconds=job.conversion_duration_seconds,
                parsing_duration_seconds=job.parsing_duration_seconds,
                total_duration_seconds=job.total_duration_seconds,
                created_at=job.created_at,
                started_at=job.started_at,
                completed_at=job.completed_at
            ),
            is_duplicate=False
        )
    )

@router.get(
    "/drawings",
    response_model=StandardResponse[List[DrawingResponse]],
    summary="List all registered drawing documents",
    dependencies=[Depends(get_auth_token)]
)
async def list_drawings():
    """
    Fetches all registered drawings from the local MongoDB registry.
    """
    docs = await DrawingDocument.find_all().to_list()
    res = [
        DrawingResponse(
            id=str(d.id),
            file_name=d.file_name,
            file_path=d.file_path,
            file_hash=d.file_hash,
            file_size_bytes=d.file_size_bytes,
            format=d.format,
            status=d.status,
            entity_counts=d.entity_counts,
            metadata=d.metadata,
            created_at=d.created_at,
            updated_at=d.updated_at
        )
        for d in docs
    ]
    return StandardResponse(success=True, data=res)

@router.get(
    "/drawings/{id}",
    response_model=StandardResponse[DrawingResponse],
    summary="Retrieve details of a DrawingDocument",
    dependencies=[Depends(get_auth_token)]
)
async def get_drawing(id: str):
    drawing = await DrawingDocument.get(id)
    if not drawing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Drawing document not found for ID: {id}"
        )
    return StandardResponse(
        success=True,
        data=DrawingResponse(
            id=str(drawing.id),
            file_name=drawing.file_name,
            file_path=drawing.file_path,
            file_hash=drawing.file_hash,
            file_size_bytes=drawing.file_size_bytes,
            format=drawing.format,
            status=drawing.status,
            entity_counts=drawing.entity_counts,
            metadata=drawing.metadata,
            created_at=drawing.created_at,
            updated_at=drawing.updated_at
        )
    )

@router.get(
    "/drawings/{id}/layers",
    response_model=StandardResponse[dict],
    summary="Retrieve serialized geometry layers for a drawing",
    dependencies=[Depends(get_auth_token)]
)
async def get_drawing_layers(id: str):
    drawing = await DrawingDocument.get(id)
    if not drawing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Drawing document not found for ID: {id}"
        )
    entities = await ExtractedEntity.find(ExtractedEntity.drawing_id == id).to_list()
    
    if not entities:
        # No entities are available yet — the extraction job is still running or has not started.
        # Return a structured error so the client can surface the correct waiting state.
        # Never inject mock geometry as a fallback for a real ingestion pipeline.
        return StandardResponse(
            success=False,
            error={
                "code": "ENTITIES_NOT_READY",
                "message": "Drawing entities have not been extracted yet. Please wait for the extraction job to complete."
            },
            data={"layers": {}}
        )

    layers_data = GeometrySerializer.serialize_entities(entities)
    return StandardResponse(success=True, data=layers_data)

@router.get(
    "/drawings/{id}/rendering",
    summary="Get high-fidelity PNG rendering of drawing background",
    dependencies=[Depends(get_auth_token)]
)
async def get_drawing_rendering(id: str):
    drawing = await DrawingDocument.get(id)
    if not drawing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Drawing document not found for ID: {id}"
        )
    rendering_path = get_storage_root() / "renderings" / f"{id}.png"
    if not rendering_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="High-fidelity rendering image not generated for this drawing."
        )
    return FileResponse(str(rendering_path), media_type="image/png")

@router.get(
    "/jobs/{id}",
    response_model=StandardResponse[JobResponse],
    summary="Retrieve status of an ExtractionJob",
    dependencies=[Depends(get_auth_token)]
)
async def get_job(id: str):
    job = await ExtractionJob.get(id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Extraction job not found for ID: {id}"
        )
    return StandardResponse(
        success=True,
        data=JobResponse(
            id=str(job.id),
            drawing_id=job.drawing_id,
            status=job.status,
            error_message=job.error_message,
            diagnostics=job.diagnostics,
            conversion_duration_seconds=job.conversion_duration_seconds,
            parsing_duration_seconds=job.parsing_duration_seconds,
            total_duration_seconds=job.total_duration_seconds,
            created_at=job.created_at,
            started_at=job.started_at,
            completed_at=job.completed_at
        )
    )

@router.get(
    "/jobs/{id}/diagnostics",
    response_model=StandardResponse[dict],
    summary="Retrieve timing and entity metrics for a job",
    dependencies=[Depends(get_auth_token)]
)
async def get_job_diagnostics(id: str):
    diagnostics = await CADDiagnostics.get_job_diagnostics(id)
    if not diagnostics.get("success", False):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=diagnostics.get("error", "Job diagnostics not resolved.")
        )
    return StandardResponse(
        success=True,
        data=diagnostics
    )

# ====================================================
# PHASE 4 — STANDARDS & AUDIT SYSTEM ROUTERS
# ====================================================

@router.post(
    "/standards/upload",
    response_model=StandardResponse[StandardDocumentResponse],
    summary="Upload and ingest a new Engineering Standard document",
    dependencies=[Depends(get_auth_token)]
)
async def upload_standard(
    file: UploadFile = File(..., description="PDF, TXT, or Markdown standard document"),
    name: str = Form(..., description="Unique title identifier of the standard"),
    scope: str = Form("client_specific", description="Scope of standard: 'universal' or 'client_specific'"),
    client_name: Optional[str] = Form(None, description="Associated client name if scope is client_specific"),
    category: Optional[str] = Form(None, description="Optional category label (e.g. Dimensions)"),
    description: Optional[str] = Form(None, description="Optional detail context summary")
):
    """
    Saves the uploaded engineering standard file, verifies limits,
    processes text sections, chunks contents, and persists data inside MongoDB Beanie collections.
    """
    ext = os.path.splitext(file.filename)[1].lower().lstrip(".")
    if ext not in ("pdf", "txt", "md", "xlsx", "xls"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported format: Standards must be PDF, TXT, Excel, or Markdown (.md, .txt, .xlsx, .xls)."
        )

    # 1. Enforce sandbox boundary temp file writes
    temp_dir = Path(get_storage_root()) / "temp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    
    unique_id = uuid.uuid4().hex
    temp_file_path = temp_dir / f"std_upload_{unique_id}.{ext}"
    validate_sandboxed_path(temp_file_path)

    try:
        # Write to temporary sandboxed file
        async with aiofiles.open(temp_file_path, "wb") as f_out:
            while chunk := await file.read(65536):
                await f_out.write(chunk)

        # Ingest, hash, chunk, and save in database
        doc, is_duplicate = await StandardsLoader.ingest_standard(
            src_file_path=temp_file_path,
            name=name,
            scope=scope,
            client_name=client_name,
            category=category,
            description=description
        )

        return StandardResponse(
            success=True,
            data=StandardDocumentResponse(
                id=str(doc.id),
                name=doc.name,
                file_path=doc.file_path,
                standard_hash=doc.standard_hash,
                file_size_bytes=doc.file_size_bytes,
                format=doc.format,
                scope=doc.scope,
                client_name=doc.client_name,
                category=doc.category,
                description=doc.description,
                metadata=doc.metadata,
                created_at=doc.created_at
            )
        )

    except Exception as e:
        logger.error(f"Failed standard document ingestion: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ingestion process failed: {str(e)}"
        )
    finally:
        # Clean temporary file
        if temp_file_path.exists():
            try:
                temp_file_path.unlink()
            except Exception as clean_err:
                logger.warning(f"Failed to delete standard upload temp file: {str(clean_err)}")

@router.get(
    "/standards",
    response_model=StandardResponse[List[StandardDocumentResponse]],
    summary="List all registered engineering standards documents",
    dependencies=[Depends(get_auth_token)]
)
async def list_standards():
    """
    Fetches all registered standards from the local MongoDB registry.
    """
    docs = await StandardDocument.find_all().to_list()
    res = [
        StandardDocumentResponse(
            id=str(d.id),
            name=d.name,
            file_path=d.file_path,
            standard_hash=d.standard_hash,
            file_size_bytes=d.file_size_bytes,
            format=d.format,
            scope=d.scope,
            client_name=d.client_name,
            category=d.category,
            description=d.description,
            metadata=d.metadata,
            created_at=d.created_at
        )
        for d in docs
    ]
    return StandardResponse(success=True, data=res)

@router.delete(
    "/standards/{id}",
    response_model=StandardResponse[dict],
    summary="Delete a registered engineering standard and its chunks",
    dependencies=[Depends(get_auth_token)]
)
async def delete_standard(id: str):
    """
    Permanently removes a StandardDocument and all associated StandardChunk records
    from MongoDB. The source file on disk is also removed if it exists.
    """
    doc = await StandardDocument.get(id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Standard document not found for ID: {id}"
        )

    # Remove all associated text chunks from the vector store
    chunks = await StandardChunk.find(StandardChunk.standard_id == id).to_list()
    for chunk in chunks:
        await chunk.delete()

    # Remove source file from disk if it exists
    try:
        file_path = get_storage_root() / doc.file_path
        if file_path.exists():
            file_path.unlink()
    except Exception as e:
        logger.warning(f"Could not remove standard source file: {str(e)}")

    await doc.delete()
    return StandardResponse(
        success=True,
        data={"message": f"Standard '{doc.name}' and all its chunks have been permanently removed."}
    )

@router.patch(
    "/standards/{id}",
    response_model=StandardResponse[StandardDocumentResponse],
    summary="Update metadata fields of a registered engineering standard",
    dependencies=[Depends(get_auth_token)]
)
async def update_standard(id: str, name: Optional[str] = None, category: Optional[str] = None, description: Optional[str] = None):
    """
    Updates the editable metadata fields (name, category, description) of an existing standard.
    """
    doc = await StandardDocument.get(id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Standard document not found for ID: {id}"
        )

    if name is not None:
        doc.name = name.strip()
    if category is not None:
        doc.category = category.strip() or None
    if description is not None:
        doc.description = description.strip() or None

    await doc.save()
    return StandardResponse(
        success=True,
        data=StandardDocumentResponse(
            id=str(doc.id),
            name=doc.name,
            file_path=doc.file_path,
            standard_hash=doc.standard_hash,
            file_size_bytes=doc.file_size_bytes,
            format=doc.format,
            scope=doc.scope,
            client_name=doc.client_name,
            category=doc.category,
            description=doc.description,
            metadata=doc.metadata,
            created_at=doc.created_at
        )
    )


@router.get(
    "/clients",
    response_model=StandardResponse[List[ClientResponse]],
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
async def create_client(req: CreateClientRequest):
    name = req.name.strip().upper()
    if not name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Client name cannot be empty."
        )
    
    existing = await ClientDocument.find_one(ClientDocument.name == name)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Client '{name}' already exists."
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

@router.post(
    "/audits/launch",
    response_model=StandardResponse[AuditSessionResponse],
    summary="Initialize and enqueue drawing audit process session",
    dependencies=[Depends(get_auth_token)]
)
async def launch_audit(
    request: LaunchAuditRequest, 
    token: str = Depends(get_auth_token),
    x_session_token: Optional[str] = Header(None, alias="X-Session-Token")
):
    """
    Registers a new AuditSession document in database in 'queued' state and pushes the task to
    the background processing queue, returning immediately to the client.
    """
    # Decode token to get username
    username = None
    try:
        if x_session_token:
            from ..core.auth import verify_jwt_token
            payload = verify_jwt_token(x_session_token)
            username = payload.get("username")
    except Exception:
        pass
    # Verify drawing document exists
    drawing = await DrawingDocument.get(request.drawing_id)
    if not drawing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Drawing not found in database: {request.drawing_id}"
        )

    if request.client_name:
        client = await ClientDocument.find_one(ClientDocument.name == request.client_name.upper())
        if not client:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Client directory '{request.client_name}' not registered in database."
            )
    elif request.standard_id:
        standard = await StandardDocument.get(request.standard_id)
        if not standard:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Engineering standard not found in database: {request.standard_id}"
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either standard_id or client_name must be specified to run compliance audit."
        )

    # Build and register AuditSession in MongoDB
    session = AuditSession(
        drawing_id=request.drawing_id,
        reference_drawing_id=request.reference_drawing_id,
        standard_id=request.standard_id,
        client_name=request.client_name.upper() if request.client_name else None,
        status="queued",
        username=username
    )
    await session.save()

    # Enqueue task in background audit worker pipeline queue
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
            error_message=session.error_message,
            timings=session.timings,
            diagnostics=session.diagnostics,
            created_at=session.created_at,
            started_at=session.started_at,
            completed_at=session.completed_at,
            remarks=session.remarks,
            username=session.username,
            is_deleted=session.is_deleted,
            deleted_at=session.deleted_at,
            deleted_by=session.deleted_by,
            is_restored=session.is_restored
        )
    )

def safe_decode(text):
    import re
    if not text:
        return ""
    # If text already contains valid Japanese, return as-is to avoid Mojibake
    if re.search(r'[\u4e00-\u9faf\u3040-\u309f\u30a0-\u30ff]', text):
        return text
    try:
        b = text.encode('latin1')
        dec = b.decode('cp932')
        return dec
    except Exception:
        try:
            b = text.encode('utf-8')
            dec = b.decode('cp932')
            if re.search(r'[\u4e00-\u9faf\u3040-\u309f\u30a0-\u30ff]', dec):
                return dec
            return text
        except Exception:
            return text

def extract_semantic_text_groups(entities: list, prefix: str = "") -> dict:
    geometry_annotations = []
    notes_zone_text = []
    bom_zone_text = []
    title_block_data = []
    
    def strip_mtext(t: str) -> str:
        return re.sub(r'\\[A-Za-z0-9\-~|.]+;', '', t.replace('{', '').replace('}', '')).strip()
    
    # Pre-scan for structural label coordinates (Unit No, Part No, etc.) to securely bypass their values
    structural_coords = []
    tolerance_coords = []
    for e in entities:
        if e.entity_type == "text":
            raw_txt = e.properties.get("text")
            if raw_txt:
                txt_val = strip_mtext(safe_decode(str(raw_txt)))
                txt_lower = txt_val.lower()
                # Structural block scan
                if any(kw in txt_lower for kw in ["unit no", "ユニットno", "part no", "コードno", "stock q'ty", "総製作個数", "t. q'ty", "共通番号"]):
                    ins = e.geometry.get("insert")
                    if ins and len(ins) >= 2:
                        structural_coords.append((ins[0], ins[1]))
                # Tolerance table scan
                txt_no_space = txt_lower.replace(" ", "")
                # Use both text headers AND tolerance table grid numeric patterns to locate the table robustly
                if any(kw in txt_no_space for kw in ["表示外公差", "仕上げ記号", "機械加工", "板金加工", "寸法区分"]) or \
                   ("100s" in txt_lower and "50s" in txt_lower) or \
                   ("1005" in txt_lower and "505" in txt_lower) or \
                   ("25s" in txt_lower and "12.5s" in txt_lower) or \
                   ("255" in txt_lower and "12.55" in txt_lower) or \
                   re.search(r'^\d+\.?\d*\s*[~〜～\-`\?]\s*\d+\.?\d*$', txt_val) or \
                   re.search(r'^\d+\.?\d*[sS]\s*[~〜～\-`\?]\s*\d+\.?\d*[sS]$', txt_val) or \
                   re.search(r'^}\s*\d+\.?\d*$', txt_val):
                    ins = e.geometry.get("insert")
                    if ins and len(ins) >= 2:
                        tolerance_coords.append((ins[0], ins[1]))
                        
    min_x, min_y = float('inf'), float('inf')
    max_x, max_y = float('-inf'), float('-inf')
    for e in entities:
        if e.entity_type == "text" and e.geometry:
            ins = e.geometry.get("insert")
            if ins and len(ins) >= 2:
                min_x = min(min_x, ins[0])
                max_x = max(max_x, ins[0])
                min_y = min(min_y, ins[1])
                max_y = max(max_y, ins[1])
                
    width = max_x - min_x if max_x > min_x else 1000.0
    height = max_y - min_y if max_y > min_y else 1000.0
    dx_margin = width * 0.04
    dy_margin = height * 0.04
    
    for e in entities:
        if e.entity_type != "text" or not e.geometry:
            continue
            
        raw_txt = e.properties.get("text")
        if raw_txt is None:
            continue
            
        text_val = strip_mtext(safe_decode(str(raw_txt)))
        if not text_val:
            continue
            
        layer_lower = e.layer.lower() if e.layer else ""
        text_lower = text_val.lower().strip()

        # Hard Filter 1: Strip Outer Border grid markers (A, B, 1, 2) mathematically
        is_outer_border = False
        ins = e.geometry.get("insert")
        if ins and len(ins) >= 2:
            is_outer_border = (
                ins[0] <= min_x + dx_margin or ins[0] >= max_x - dx_margin or
                ins[1] <= min_y + dy_margin or ins[1] >= max_y - dy_margin
            )
            
        if len(text_val) <= 2 and is_outer_border:
            continue
            
        # Hard Filter 2: Strip Column Headers and Category Labels robustly
        norm_txt = text_lower.replace(" ", "").replace("　", "").replace("’", "'").replace(":", "/")
        column_headers = {
            "no.", "no", "code", "dimension", "q'ty", "remark", "title", "dwgno.", "dwgno", 
            "材質", "寸法", "個数", "重量", "備考", "名称", "図面番号", "材料寸法", "材料個数", "素材重量", "仕上重量",
            "material", "weight", "qty", "unitcode", "unit/total", "t.q'ty", "stockq'ty",
            "drawn", "製図", "approved", "承認", "checked", "照査", "designed", "設計",
            "scale", "尺度", "jobno.", "工事番号", "mach.code", "unitno.", "partno.", "型式",
            "材質/code", "材料寸法/型式/dimension", "材料個数/q'ty", "素材重量kg/materialwt(kg)", 
            "仕上重量kg/finishedwt(kg)", "備考/remark", "図面番号/dwgno.", "名称/title"
        }
        
        is_header = False
        for part in norm_txt.split("/"):
            if part in column_headers:
                is_header = True
                break
        if is_header:
            continue
            
        # If the header is combined with a slash (e.g. "型式 / Code"), check its parts
        if "/" in norm_txt:
            parts = [p for p in norm_txt.split("/") if p]
            if parts and all(p in column_headers for p in parts):
                continue
                
        # Hard Filter 3: General Tolerance Table
        # The tolerance table is a dense grid of numbers and ranges.
        is_tolerance_value = False
        if tolerance_coords:
            ins = e.geometry.get("insert")
            if ins and len(ins) >= 2:
                for cx, cy in tolerance_coords:
                    # If it's within a tightly bounded box of any tolerance header
                    if abs(ins[0] - cx) < max(500.0, width * 0.15) and abs(ins[1] - cy) < max(350.0, height * 0.15):
                        # Filter out isolated numbers, decimals, ranges, and finish symbols
                        if re.search(r'^\d+(\.\d+)?$', text_val) or \
                           re.search(r'^\d+\.?\d*\s*~\s*\d+\.?\d*$', text_val) or \
                           re.search(r'^}\s*\d+\.?\d*$', text_val) or \
                           re.search(r'^\d+\.?\d*[sS]\s*~\s*\d+\.?\d*[sS]$', text_val) or \
                           norm_txt in ["表示外公差", "仕上げ記号", "機械加工", "板金加工", "寸法区分", "角度", "長さ", "削り加工", "参考", "example", "finishsymbol"]:
                            is_tolerance_value = True
                            break
        if is_tolerance_value:
            continue

        # Check if the text is one of the structural labels
        is_structural_label = any(kw in text_lower for kw in ["unit no", "ユニットno", "part no", "コードno", "stock q'ty", "在庫棚入庫", "t. q'ty", "総製作個数"])
        
        # Spatial check: if this text is physically near any of the structural labels, it's a metadata value.
        is_structural_value = False
        is_tolerance_value = False
        ins = e.geometry.get("insert")
        if ins and len(ins) >= 2:
            for cx, cy in structural_coords:
                # Same row (Y-alignment) within 5% of drawing height, and physically to the right (or nearby)
                if abs(ins[1] - cy) < max(100.0, height * 0.05):
                    # As long as it's not wildly far away (e.g., width * 0.8)
                    if abs(ins[0] - cx) < max(1500.0, width * 0.6):
                        is_structural_value = True
                        break
                        
            # Tolerance table spatial filter: obliterate any generic numbers physically close to the table anchors
            for cx, cy in tolerance_coords:
                if abs(ins[0] - cx) < max(500.0, width * 0.15) and abs(ins[1] - cy) < max(450.0, height * 0.20):
                    # Only delete them if they are typical tolerance table boilerplate (numbers, short codes)
                    if len(text_val) < 15 and (re.search(r'^\d+(\.\d+)?$', text_val) or "s" in text_lower or "~" in text_val or "〜" in text_val or "-" in text_val or "5" in text_val or "0" in text_val):
                        is_tolerance_value = True
                        break
        
        # Completely bypass all categories for Unit No, Part No, etc. AND Tolerance Tables
        if is_structural_label or is_structural_value or is_tolerance_value:
            continue

        # 1. Title Block Data
        is_title = (
            "title" in layer_lower or "header" in layer_lower or "border" in layer_lower or 
            "stamp" in layer_lower or "admin" in layer_lower or "block" in layer_lower or 
            "logo" in layer_lower or "dwg" in layer_lower or "rev" in layer_lower or "qty" in layer_lower or
            "date" in layer_lower or "approved" in layer_lower or "checked" in layer_lower or
            "scale" in layer_lower or
            "approved" in text_lower or "checked" in text_lower or "designed" in text_lower or
            "drawn" in text_lower or "scale" in text_lower or "dwg no" in text_lower or
            "job no" in text_lower or "cross ref" in text_lower or "prev" in text_lower or
            any(kw in text_val for kw in ["日下部", "設計", "製図", "尺度", "図番", "図名", "品名", "年月日", "日付", "共通番号", "機番", "計画図", "総製作個数", "個数", "T. Q'ty", "T. Q’ty", "ユニットNo.", "Unit No.", "コードNo.", "Part No."]) or
            re.search(r'\b(?:REV|revision)\.?\s*([A-Z0-9]+)\b', text_val, re.IGNORECASE) or
            re.search(r'^\d{4}/\d{2}/\d{2}$', text_val) or
            re.search(r'^\d{4}-\d{1,2}-\d{1,2}$', text_val) or
            # Include text/numbers if they reside on a Title/Header/Border layer
            (("title" in layer_lower or "header" in layer_lower or "border" in layer_lower or "admin" in layer_lower or "stamp" in layer_lower or "block" in layer_lower) and 
             (re.search(r'^[A-Z0-9_-]+$', text_val) or re.search(r'^\d+(\.\d+)?$', text_val)))
        )
        if "在庫棚入庫" in text_val or "stock q'ty" in text_lower or "stock" in text_lower:
            is_title = True  # Map Stock Qty specifically to title block to prevent leaks
        if is_title:
            title_block_data.append(text_val)
            continue
            
        # 2. BOM Zone Text
        is_bom = (
            "bom" in layer_lower or "bill" in layer_lower or "material" in layer_lower or 
            "table" in layer_lower or "parts" in layer_lower or "qty" in layer_lower or "legend" in layer_lower or
            "weight" in text_lower or "material" in text_lower or "qty" in text_lower or
            "fin.wt" in text_lower or "finished weight" in text_lower or "remark" in text_lower or
            "ss400" in text_lower or "sus304" in text_lower or "s235jr" in text_lower or
            "s355jr" in text_lower or "a6061" in text_lower or "alumin" in text_lower or
            "unit no." in text_lower or "part no." in text_lower or
            any(kw in text_val for kw in ["材質", "寸法", "型式", "素材重量", "仕上重量", "備考", "単／全", "コードNo.", "ユニットNo."]) or
            re.search(r'\b(?:qty|qt|quantity)\b', text_lower) or
            re.search(r'\b\d+\s*(?:[xX\*×]|\u00d7)\s*\d+\s*(?:[xX\*×]|\u00d7)\s*\d+\b', text_val) or
            # Include weights, counts and other cell contents if they are on a BOM/Table/Parts layer
            (("bom" in layer_lower or "bill" in layer_lower or "table" in layer_lower or "parts" in layer_lower or "material" in layer_lower) and 
             (re.search(r'^\d+(\.\d+)?$', text_val) or text_val in ["-", "—", "トオシ", "通シ"]))
        )
        if is_bom:
            bom_zone_text.append(text_val)
            continue
 
        # 3. Geometry Annotations
        is_geom = (
            "dim" in layer_lower or "dimension" in layer_lower or "callout" in layer_lower or 
            "geometry" in layer_lower or "anno" in layer_lower or
            "キリ" in text_val or "トオシ" in text_val or "通シ" in text_val or 
            "深サ" in text_val or "ザグリ" in text_val or "面取" in text_val or
            re.search(r'^\d+-\d+キリ', text_val) or
            re.search(r'^\d+X\d+-M\d+', text_val) or
            re.search(r'^M\d+', text_val) or
            re.search(r'^\d+-\d+-[A-Z]', text_val)
        )
        
        handle = e.properties.get("handle", "UNK") if e.properties else "UNK"
        id_str = f"{prefix}-{handle}" if prefix else handle
        ins = e.geometry.get("insert", [0, 0]) if e.geometry else [0, 0]
        formatted_txt = f"[ID: {id_str}, X: {int(ins[0])}, Y: {int(ins[1])}] {text_val}"

        if is_geom:
            geometry_annotations.append(formatted_txt)
            continue
 
        # 4. Notes Zone Text
        is_note = (
            "note" in layer_lower or "rule" in layer_lower or "instruction" in layer_lower or
            "text" in layer_lower or
            re.search(r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF]', text_val)
        )
        is_tolerance_row = re.search(r'^\d+\.?\d*\s*~\s*\d+\.?\d*$', text_val) or re.search(r'^±\s*\d+\.?\d*$', text_val)
        
        if is_note and not is_tolerance_row:
            notes_zone_text.append(text_val)
            continue
 
        if re.search(r'^\d+(\.\d+)?$', text_val) or layer_lower in ["0", "defpoints"]:
            geometry_annotations.append(formatted_txt)
        else:
            notes_zone_text.append(formatted_txt)
            
    return {
        "geometry_annotations": "\n".join(geometry_annotations),
        "notes_zone_text": "\n".join(notes_zone_text),
        "bom_zone_text": "\n".join(bom_zone_text),
        "title_block_data": "\n".join(title_block_data),
    }

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

    # 1. Fetch extracted entities to perform data-driven analysis
    ref_entities = await ExtractedEntity.find(ExtractedEntity.drawing_id == request.reference_drawing_id).to_list()
    rev_entities = await ExtractedEntity.find(ExtractedEntity.drawing_id == request.drawing_id).to_list()

    # Pre-extract mathematical title block coordinates to globally block them from coordinate snapping and marking
    global_blocked_coords = []
    global_blocked_values = set()
    try:
        from .v1 import extract_title_fields  # Ensure availability
        is_assembly_drawing = True # Safe assumption for pre-extraction
        temp_ref_title = extract_title_fields(ref_entities, is_assembly=is_assembly_drawing)
        temp_rev_title = extract_title_fields(rev_entities, is_assembly=is_assembly_drawing)
        for temp_tb in [temp_ref_title, temp_rev_title]:
            for key in ["Unit No", "Part No", "Total Q'ty", "MACHINE CODE", "DWG NO"]:
                obj = temp_tb.get(key, {})
                coords = obj.get("coordinates")
                val = obj.get("value")
                if coords and len(coords) >= 2:
                    global_blocked_coords.append((coords[0], coords[1]))
                if val and str(val).strip() and str(val).strip() != "NONE":
                    global_blocked_values.add(str(val).strip())
    except Exception as e:
        pass


    def map_signature_value(text: str) -> str:
        # Pass-through only — safe_decode handles encoding normalization upstream.
        # No project-specific string remapping is permitted here.
        if not text:
            return "NONE"
        return text.strip()

    def compare_values(orig_val: str, kmti_val: str) -> str:
        """Compare two cell or block values and classify: MATCHED, ADDED, CHANGED, or REMOVED."""
        import re
        o = (orig_val or "NONE").strip()
        k = (kmti_val or "NONE").strip()
        
        if o == k:
            return "MATCHED"
            
        def normalize(val: str) -> str:
            if not val or val == "NONE":
                return ""
            v = val.lower().strip()
            # Removed CP932 heuristic replacement
            # Treat lowercase x, uppercase X, and × multiplication symbol identically
            v = re.sub(r'[xX×]', 'x', v)
            # Treat colons : and slashes / identically
            v = re.sub(r':', '/', v)
            return v
            
        norm_o = normalize(o)
        norm_k = normalize(k)
        
        if norm_o == norm_k:
            return "MATCHED"
            
        # ADDED Marker rule
        if (not norm_o or norm_o == "") and (norm_k and norm_k != ""):
            return "ADDED"
            
        # REMOVED Marker rule
        if (norm_o and norm_o != "") and (not norm_k or norm_k == ""):
            return "REMOVED"
            
        # CHANGED / REMOVED Marker rule when both values exist but they are different:
        if norm_o and norm_k:
            return "CHANGED"
            
        return "REMOVED"

    def find_drawing_text_coordinates(
            entities: list,
            target_text: str,
            category: Optional[str] = None,
            region_bbox: Optional[tuple] = None,
            used_entities: set = None
    ) -> Optional[list[float]]:
        """Locate the screen anchor coordinate for a given text value.

        Search passes:
          1. Exact match within the spatial region bbox AND category-layer entities.
          2. Exact match across all entities (global).
          3. Containment substring match (target appears inside the drawing text).
             The reverse clause ``dec_norm in target_norm`` is removed to prevent
             short primitives ("0", "1") from matching longer targets ("SS400", "800").

        Args:
            region_bbox: Optional (xmin, ymin, xmax, ymax) in model-space. When
                         provided, entities whose insertion point falls inside this
                         box are searched first; other entities are searched as a
                         global fallback.  This is the primary mechanism for drawings
                         where all entities share a generic layer name.
        """
        if not target_text or target_text == "NONE":
            return None
            
        import unicodedata
        target_norm = unicodedata.normalize('NFKC', target_text).strip().replace(" ", "").replace("\n", "").lower()

        def get_anchor(e) -> list[float]:
            ins = e.geometry.get("insert") or [0, 0, 0]
            height = e.properties.get("height", 3.0)
            bbox = e.properties.get("bbox", None)
            if bbox:
                try:
                    xmin, ymin = bbox[0]
                    xmax, ymax = bbox[1]
                    box_height = ymax - ymin
                    return [xmax + (height * 0.8), ymin + (box_height / 2.0)]
                except Exception:
                    pass
            # Estimate text width if bbox is missing or invalid
            text_len = len(e.properties.get("text", ""))
            estimated_width = text_len * height * 0.6
            return [ins[0] + estimated_width + (height * 0.8), ins[1] + (height / 2.0)]

        def in_region(e) -> bool:
            """True if the entity's insertion point is inside region_bbox."""
            if not region_bbox:
                return False
            ins = e.geometry.get("insert") or [0, 0, 0]
            rx0, ry0, rx1, ry1 = region_bbox
            return rx0 <= ins[0] <= rx1 and ry0 <= ins[1] <= ry1

        def layer_matches_category(layer_str: str, cat: Optional[str]) -> bool:
            if not cat:
                return False
            l = (layer_str or "").lower()
            if cat == "title_block":
                return any(x in l for x in ("title", "border", "stamp", "attr", "admin", "block", "header", "logo", "dwg", "rev", "approved", "checked", "designed", "drawn", "scale"))
            if cat == "bill_of_materials":
                return any(x in l for x in ("bom", "parts", "material", "partslist", "materials"))
            if cat == "notes_section":
                return any(x in l for x in ("note", "anno", "comment", "annotation", "text"))
            return False

        # Partition entities: region-bbox match > layer match > everything else
        inside_region = []
        layer_priority = []
        elsewhere = []
        for e in entities:
            if e.entity_type != "text" or not e.geometry:
                continue
                
            # --- PREVENT SNAPPING TO TITLE BLOCK METADATA ---
            ins = e.geometry.get("insert")
            if ins and len(ins) >= 2:
                is_blocked = False
                for bx, by in global_blocked_coords:
                    if abs(ins[0] - bx) < 5.0 and abs(ins[1] - by) < 5.0:
                        is_blocked = True
                        break
                if is_blocked:
                    continue
            layer = getattr(e, "layer", "") or ""
            if region_bbox and in_region(e):
                inside_region.append(e)
            elif layer_matches_category(layer, category):
                layer_priority.append(e)
            else:
                # Prevent cross-contamination: if it belongs explicitly to a different category, SKIP IT!
                is_cross_contaminated = False
                for other_cat in ["title_block", "bill_of_materials"]:
                    if category != other_cat and layer_matches_category(layer, other_cat):
                        is_cross_contaminated = True
                        break
                if not is_cross_contaminated:
                    elsewhere.append(e)

        # Search order: spatially-correct region first, then named-layer match, then global
        search_order = inside_region + layer_priority + elsewhere

        def strip_mtext(t: str) -> str:
            import re
            return re.sub(r'\\[A-Za-z0-9\-~|.]+;', '', t.replace('{', '').replace('}', '')).strip()

        # Pass 1 – Exact match
        for e in search_order:
            if used_entities is not None and id(e) in used_entities:
                continue
            raw_txt = e.properties.get("text", "")
            if raw_txt:
                decoded = strip_mtext(safe_decode(raw_txt))
                dec_norm = unicodedata.normalize('NFKC', decoded).strip().replace(" ", "").replace("\n", "").lower()
                if dec_norm == target_norm:
                    if used_entities is not None:
                        used_entities.add(id(e))
                    return get_anchor(e)

        # Pass 2 – Containment substring match (target inside drawing text only)
        for e in search_order:
            if used_entities is not None and id(e) in used_entities:
                continue
            # Squelch elsewhere fallback for super short strings in strict bounded regions only for containment matches
            if len(target_norm) < 3 and region_bbox and e in elsewhere:
                continue
            raw_txt = e.properties.get("text", "")
            if raw_txt:
                decoded = strip_mtext(safe_decode(raw_txt))
                dec_norm = unicodedata.normalize('NFKC', decoded).strip().replace(" ", "").replace("\n", "").lower()
                if target_norm in dec_norm:
                    if len(target_norm) > 2:
                        if used_entities is not None:
                            used_entities.add(id(e))
                        return get_anchor(e)
                    else:
                        import re
                        # For short strings (like "10" or "m6"), only allow if surrounded by non-digits or start/end
                        # This prevents "10" from matching "100"
                        if re.search(r'(^|\D)' + re.escape(target_norm) + r'(\D|$)', dec_norm):
                            if used_entities is not None:
                                used_entities.add(id(e))
                            return get_anchor(e)

        # Pass 3 – Fallback partial match for fragmented CAD text (e.g. single characters)
        if len(target_norm) >= 3:
            prefix = target_norm[:2]
            for e in search_order:
                if used_entities is not None and id(e) in used_entities:
                    continue
                raw_txt = e.properties.get("text", "")
                if raw_txt:
                    decoded = strip_mtext(safe_decode(raw_txt))
                    dec_norm = unicodedata.normalize('NFKC', decoded).strip().replace(" ", "").replace("\n", "").lower()
                    # If the CAD entity is just the first 1 or 2 characters of our target
                    if dec_norm and (dec_norm in prefix or prefix in dec_norm):
                        if used_entities is not None:
                            used_entities.add(id(e))
                        return get_anchor(e)

        return None

    # --- DYNAMIC 100% ACCURATE REAL PARSING ---
    ref_has_real_entities = len(ref_entities) > 0 or (ref_drawing.entity_counts and sum(ref_drawing.entity_counts.values()) > 0)
    rev_has_real_entities = len(rev_entities) > 0 or (rev_drawing.entity_counts and sum(rev_drawing.entity_counts.values()) > 0)
    
    if not ref_has_real_entities or not rev_has_real_entities:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The uploaded drawing files do not contain any parsed CAD vector text entities. Automated physical checklist overlays require drawing files with readable vector text metadata. Please import standard vector drawings."
        )

    # Extract dynamic revision codes and title strings
    ref_rev = "A"
    rev_rev = "A"
    
    for e in ref_entities:
        if e.entity_type == "text":
            raw_txt = e.properties.get("text")
            if raw_txt is not None:
                txt = str(raw_txt).strip()
                m = re.search(r'\b(?:REV|revision)\.?\s*([A-Z0-9]+)\b', txt, re.IGNORECASE)
                if m:
                    ref_rev = m.group(1)
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

    def build_title_block_table(ref_fields, rev_fields):
        def status(orig, kmti, field_name=''):
            s = compare_values(orig, kmti)
            return 'MATCHED' if s == 'MATCHED' else 'MISMATCHED'

        def get_val(fields, key):
            val_obj = fields.get(key, "NONE")
            if isinstance(val_obj, dict):
                val = val_obj.get("value", "NONE")
            else:
                val = val_obj
                
            val_str = str(val).strip()
            if val_str == "NONE":
                return val_str
                
            if key == 'DRAWN':
                val_str = re.sub(r'^(?:作\s*成|製\s*図|DRAWN)\s*:?\s*', '', val_str, flags=re.IGNORECASE).strip()
            elif key == 'DESIGNED':
                val_str = re.sub(r'^(?:設\s*計|DESIGNED)\s*:?\s*', '', val_str, flags=re.IGNORECASE).strip()
            elif key == 'JOB NO':
                val_str = re.sub(r'^(?:工\s*事\s*番\s*号|JOB\s*NO\.?)\s*:?\s*', '', val_str, flags=re.IGNORECASE).strip()
            elif key == 'MACHINE CODE':
                val_str = re.sub(r'^(?:機\s*器\s*/?\s*ユ\s*ニ\s*ッ\s*ト\s*記\s*号|機\s*器\s*記\s*号|ユ\s*ニ\s*ッ\s*ト\s*記\s*号|Mach\.?\s*code|Unit\s*Code)\s*:?\s*', '', val_str, flags=re.IGNORECASE).strip()
            elif key == 'DWG NO':
                val_str = re.sub(r'^(?:図\s*面\s*番\s*号|DWG\.?\s*No\.?|機\s*種|Machine\s*Type|ユ\s*ニ\s*ッ\s*ト|Unit\s*No\.?|部\s*品|Part\s*No\.?|特\s*性|派\s*生|Branch)\s*:?\s*', '', val_str, flags=re.IGNORECASE).strip()
            elif key == 'TITLE':
                val_str = re.sub(r'^(?:名\s*称|TITLE)\s*:?\s*', '', val_str, flags=re.IGNORECASE).strip()
            elif key == 'QTY':
                val_str = re.sub(r'^(?:総\s*製\s*作\s*個\s*数|T\.\s*Q\'ty|Total\s*Quantity)\s*:?\s*', '', val_str, flags=re.IGNORECASE).strip()
                
            return val_str or "NONE"

        ref_des = get_val(ref_fields, 'DESIGNED')
        ref_drw = get_val(ref_fields, 'DRAWN')
        rev_des = get_val(rev_fields, 'DESIGNED')
        rev_drw = get_val(rev_fields, 'DRAWN')

        rows = [
            ('総製作個数 T. Q\'ty (Total Quantity)', get_val(ref_fields, 'QTY'),             get_val(rev_fields, 'QTY'),             'QTY'),
            ('共通番号 Cross ref No.',             get_val(ref_fields, 'CROSS REF NO'),     get_val(rev_fields, 'CROSS REF NO'),     ''),
            ('旧図面番号 Previous Dwg. No.',       get_val(ref_fields, 'PREVIOUS DWG NO'),  get_val(rev_fields, 'PREVIOUS DWG NO'),  ''),
            ('設計 DESIGNED / 作成 DRAWN',          f"{ref_des} / {ref_drw}",                f"{rev_des} / {rev_drw}",                ''),
            ('尺度 SCALE',                          get_val(ref_fields, 'SCALE'),            get_val(rev_fields, 'SCALE'),            'SCALE'),
            ('工事番号 Job No.',                    get_val(ref_fields, 'JOB NO'),           get_val(rev_fields, 'JOB NO'),           ''),
            ('標準図番号 Std. No.',                  get_val(ref_fields, 'STD NO'),           get_val(rev_fields, 'STD NO'),           ''),
            ('機器記号 Mach. code / ユニット記号 Unit Code', get_val(ref_fields, 'MACHINE CODE'), get_val(rev_fields, 'MACHINE CODE'), ''),
            ('図面番号 DWG. No. / 機種 Machine Type / ユニット Unit No. / 部品 Part No. / 特性 派生 Branch', get_val(ref_fields, 'DWG NO'), get_val(rev_fields, 'DWG NO'), 'DWG NO'),
            ('名称 TITLE',                          get_val(ref_fields, 'TITLE'),            get_val(rev_fields, 'TITLE'),            ''),
        ]
        header = f"{'FIELD':<96}| {'ORIGINAL':<28}| {'KMTI':<28}| MARKED"
        sep    = '-' * len(header)
        lines  = [header, sep]
        for label, orig, kmti, fn in rows:
            s = status(orig, kmti, fn)
            lines.append(f"{label:<96}| {orig:<28}| {kmti:<28}| {s}")
        return '\n'.join(lines)

    # -----------------------------------------------------------------------
    # BOM TABLE EXTRACTION (Parts Drawing & Assembly Drawing)
    # -----------------------------------------------------------------------
    def extract_dynamic_regions(entities: list) -> dict:
        """
        Phase 3: Dynamic Layout Analysis Engine
        Scans for outermost continuous LWPOLYLINE or LINE entities to determine true sheet boundary.
        Classifies Title Block and BOM based on dense clusters of lines.
        Returns normalized fractional bounding boxes [0.0 - 1.0].
        """
        # Find all line segments
        lines = []
        for e in entities:
            if getattr(e, "entity_type", "") == "line":
                geo = getattr(e, "geometry", {})
                if "start" in geo and "end" in geo:
                    lines.append((geo["start"], geo["end"]))
            elif getattr(e, "entity_type", "") == "polyline":
                geo = getattr(e, "geometry", {})
                if "vertices" in geo:
                    pts = geo["vertices"]
                    for i in range(len(pts) - 1):
                        lines.append((pts[i], pts[i+1]))
                elif "points" in geo:
                    pts = geo["points"]
                    for i in range(len(pts) - 1):
                        lines.append((pts[i], pts[i+1]))

        # Fallback to hardcoded regions if no lines exist
        default_regions = {
            "views":         { "xMin": 0.04, "xMax": 0.68, "yMin": 0.12, "yMax": 0.88 },
            "notes":         { "xMin": 0.04, "xMax": 0.38, "yMin": 0.18, "yMax": 0.62 },
            "bom":           { "xMin": 0.62, "xMax": 0.98, "yMin": 0.04, "yMax": 0.44 },
            "title":         { "xMin": 0.38, "xMax": 0.98, "yMin": 0.72, "yMax": 0.98 },
            "titleUpperLeft":{ "xMin": 0.02, "xMax": 0.35, "yMin": 0.02, "yMax": 0.35 },
            "iso":           { "xMin": 0.62, "xMax": 0.98, "yMin": 0.42, "yMax": 0.74 }
        }
    
        if not lines:
            return default_regions

        # 1. Determine True Sheet Boundary
        min_x = min(min(p1[0], p2[0]) for p1, p2 in lines)
        max_x = max(max(p1[0], p2[0]) for p1, p2 in lines)
        min_y = min(min(p1[1], p2[1]) for p1, p2 in lines)
        max_y = max(max(p1[1], p2[1]) for p1, p2 in lines)
    
        width = max_x - min_x
        height = max_y - min_y
        if width <= 0 or height <= 0:
            return default_regions

        # Basic dynamic bounds assumption:
        # 2. Topological Component Recognition
        tr_lines = [l for l in lines if (l[0][0]-min_x)/width > 0.6 and (l[0][1]-min_y)/height < 0.5]
        br_lines = [l for l in lines if (l[0][0]-min_x)/width > 0.4 and (l[0][1]-min_y)/height > 0.6]
    
        def get_bounds(quad_lines, default_box):
            if not quad_lines:
                return default_box
            qx_min = min(min(p1[0], p2[0]) for p1, p2 in quad_lines)
            qx_max = max(max(p1[0], p2[0]) for p1, p2 in quad_lines)
            qy_min = min(min(p1[1], p2[1]) for p1, p2 in quad_lines)
            qy_max = max(max(p1[1], p2[1]) for p1, p2 in quad_lines)
            return {
                "xMin": max(0.0, (qx_min - min_x) / width - 0.01),
                "xMax": min(1.0, (qx_max - min_x) / width + 0.01),
                "yMin": max(0.0, (qy_min - min_y) / height - 0.01),
                "yMax": min(1.0, (qy_max - min_y) / height + 0.01)
            }

        bom_bounds = get_bounds(tr_lines, default_regions["bom"])
        title_bounds = get_bounds(br_lines, default_regions["title"])
    
        return {
            "views":         default_regions["views"],
            "notes":         default_regions["notes"],
            "bom":           bom_bounds,
            "title":         title_bounds,
            "titleUpperLeft":default_regions["titleUpperLeft"],
            "iso":           default_regions["iso"]
        }

    def extract_bom_fields(entities: list, render_bounds: Optional[list] = None) -> tuple:
        """Auto-detect drawing type (Parts vs Assembly) and extract all BOM rows.
        Returns (extracted_rows, is_assembly) where extracted_rows is a list of dicts,
        each dict mapping column_key -> {'value': str, 'coordinates': [x, y] | None}.
        """
        import math

        bom_coord_scale = 1.0
        if render_bounds and len(render_bounds) >= 4:
            if render_bounds[2] - render_bounds[0] > 1200:
                bom_coord_scale = 2.0
        else:
            for e in entities:
                if e.entity_type == "text" and e.geometry:
                    ins = e.geometry.get("insert") or [0, 0, 0]
                    if 1000 < ins[0] < 5000:
                        bom_coord_scale = 2.0
                        break

        def bom_norm(text: str) -> str:
            return text.strip().replace(" ", "").lower()

        # Compute drawing sheet height and max Y limit to filter out out-of-bounds Mojibake text
        all_ys = [(e.geometry or {}).get("insert", [0, 0, 0])[1]
                  for e in entities if e.entity_type == "text" and e.geometry]
        
        if render_bounds and len(render_bounds) >= 4:
            drawing_height = render_bounds[3] - render_bounds[1]
            max_y_limit = render_bounds[3]
        else:
            # Fallback outlier-robust Y calculations
            sorted_ys = sorted(all_ys)
            if sorted_ys:
                p90_y = sorted_ys[int(len(sorted_ys) * 0.90)]
                min_y = sorted_ys[0]
                drawing_height = p90_y - min_y if p90_y > min_y else 1000.0
                max_y_limit = p90_y
            else:
                drawing_height = 1000.0
                max_y_limit = 1000.0

        # ---- STEP 1: LOCATE BOM REGION ----
        anchor_kws = [
            "no.", "remark", "\u5099\u8003", "material", "\u7d20\u6750", "\u4ed5\u4e0a",
            "dimension", "code", "\u6750\u8cea", "dwg no", "dwg.no", "\u56f3\u9762\u756a\u53f7",
            "title", "\u540d\u79f0", "/type",
        ]
        candidate_ys = []
        for e in entities:
            if e.entity_type != "text" or not e.geometry:
                continue
            ins = e.geometry.get("insert") or [0, 0, 0]
            vy = ins[1]
            # Ignore any text way above the sheet boundary (out-of-bounds noise)
            if vy > max_y_limit + 10.0 * bom_coord_scale:
                continue
            # Ignore any text in the lower half of the drawing sheet (BOM is always top-right)
            if vy < max_y_limit - drawing_height * 0.5:
                continue
                
            raw = e.properties.get("text", "").strip()
            decoded = safe_decode(raw).strip()
            n = bom_norm(decoded)
            for kw in anchor_kws:
                if bom_norm(kw) in n and len(n) < 45:
                    candidate_ys.append(vy)
                    break

        bom_y_min = 0.0
        if candidate_ys:
            max_y = max(candidate_ys)
            bom_y_min = max_y - (drawing_height * 0.15)

        def find_col_header(patterns: list):
            for pat_group in patterns:
                group_matches = []
                for e in entities:
                    if e.entity_type != "text" or not e.geometry:
                        continue
                    ins = e.geometry.get("insert") or [0, 0, 0]
                    if ins[1] < bom_y_min:
                        continue
                    raw = e.properties.get("text", "").strip()
                    decoded = safe_decode(raw).strip()
                    for p in pat_group:
                        if bom_norm(p) == bom_norm(raw) or bom_norm(p) == bom_norm(decoded):
                            group_matches.append((ins[1], e))
                            break
                if group_matches:
                    group_matches.sort(key=lambda m: m[0], reverse=True)
                    return group_matches[0][1]
            for pat_group in patterns:
                group_matches = []
                for e in entities:
                    if e.entity_type != "text" or not e.geometry:
                        continue
                    ins = e.geometry.get("insert") or [0, 0, 0]
                    if ins[1] < bom_y_min:
                        continue
                    raw = e.properties.get("text", "").strip()
                    decoded = safe_decode(raw).strip()
                    for p in pat_group:
                        np = bom_norm(p)
                        if len(np) > 2 and (np in bom_norm(raw) or np in bom_norm(decoded)):
                            group_matches.append((ins[1], e))
                            break
                if group_matches:
                    group_matches.sort(key=lambda m: m[0], reverse=True)
                    return group_matches[0][1]
            return None

        # ---- STEP 2: AUTO-DETECT DRAWING TYPE ----
        asm_signals = ["\u56f3\u9762\u756a\u53f7", "dwgno.", "dwg.no."]
        is_assembly = False
        for e in entities:
            if e.entity_type != "text" or not e.geometry:
                continue
            ins = e.geometry.get("insert") or [0, 0, 0]
            if ins[1] < bom_y_min:
                continue
            raw = e.properties.get("text", "").strip()
            decoded = safe_decode(raw).strip()
            n = bom_norm(decoded)
            for sig in asm_signals:
                if bom_norm(sig) in n:
                    is_assembly = True
                    break
            if is_assembly:
                break
        if not is_assembly:
            for e in entities:
                if e.entity_type != "text" or not e.geometry:
                    continue
                ins = e.geometry.get("insert") or [0, 0, 0]
                if ins[1] < bom_y_min:
                    continue
                raw = e.properties.get("text", "").strip()
                decoded = safe_decode(raw).strip()
                if bom_norm("DWG No.") in bom_norm(decoded) or bom_norm("DWG No.") in bom_norm(raw):
                    is_assembly = True
                    break

        # ---- STEP 3: COLUMN SCHEMAS ----
        if is_assembly:
            col_defs = [
                ("NO",     [["No."]], 15.0),
                ("DWG_NO", [["\u56f3\u9762\u756a\u53f7"], ["DWG No.", "DWG.No.", "DWGNo."]], 50.0),
                ("TITLE",  [["\u540d\u79f0"], ["TITLE"]], 50.0),
                ("QTY",    [["Q'ty", "\u500b\u6570", "Q\u2019ty"]], 20.0),
                ("REMARK", [["\u5099\u8003", "Remark"]], 20.0),
            ]
        else:
            col_defs = [
                ("NO",              [["No."]], 12.0),
                ("CODE",            [["Code", "\u6750\u8cea"]], 15.0),
                ("DIMENSION",       [["Dimension/Model No.", "\u6750\u6599\u5bf8\u6cd5/\u578b\u5f0f", "Dimension/Model"]], 25.0),
                ("QTY",             [["Q'ty", "\u6750\u6599\u500b\u6570", "\u500b\u6570"]], 15.0),
                ("MATERIAL_WEIGHT", [["Material Weight(kg)", "Materjal Weight (kg)", "\u7d20\u6750\u91cd\u91cfKg", "MaterialWeight"]], 25.0),
                ("FINISHED_WEIGHT", [["Finished Weight(kg)", "\u4ed5\u4e0a\u91cd\u91cfkg", "\u4ed5\u4e0a\u91cd\u91cf", "FinishedWeight"]], 25.0),
                ("REMARK",          [["Remark", "\u5099\u8003"]], 20.0),
            ]

        # Find headers
        headers = {}
        for col_key, pat_groups, dx_tol in col_defs:
            h_ent = find_col_header(pat_groups)
            if h_ent and h_ent.geometry:
                h_ins = h_ent.geometry.get("insert") or [0, 0, 0]
                headers[col_key] = {"hx": h_ins[0], "hy": h_ins[1], "dx_tol": dx_tol}

        if not headers:
            return [], is_assembly

        # Compute dynamic row1_max_y from matched headers
        h_ys = [h["hy"] for h in headers.values()]
        row1_max_y = min(h_ys) - (0.5 * bom_coord_scale)

        # Gather data entities below headers
        h_xs = [h["hx"] for h in headers.values()]
        x_min = min(h_xs) - 30.0 * bom_coord_scale
        x_max = max(h_xs) + 40.0 * bom_coord_scale

        data_ents = []
        circled_digits = set(chr(c) for c in range(0x2460, 0x2474))
        for e in entities:
            if e.entity_type != "text" or not e.geometry:
                continue
            ins = e.geometry.get("insert") or [0, 0, 0]
            vx, vy = ins[0], ins[1]
            if vy >= row1_max_y:
                continue
            if vy < bom_y_min:
                continue
            if not (x_min <= vx <= x_max):
                continue
            raw = e.properties.get("text", "").strip()
            decoded = safe_decode(raw).strip()
            if not decoded:
                continue
            if len(decoded) == 1 and decoded in circled_digits:
                continue
            data_ents.append(e)

        # Fix B2: Dynamic Anchor-Key BOM Matrix Alignment
        # Group data entities by anchoring them to the "No." column entries.
        no_col = headers.get("NO")
        no_x = no_col["hx"] if no_col else 0
        no_dx = (col_defs[0][2] * bom_coord_scale) if no_col else 15.0 * bom_coord_scale
        
        anchors = []
        for e in data_ents:
            ins = e.geometry.get("insert") or [0, 0, 0]
            if abs(ins[0] - no_x) <= no_dx:
                anchors.append({
                    "entity": e,
                    "y": ins[1],
                    "row_ents": [e]
                })
        
        for e in data_ents:
            if any(e == a["entity"] for a in anchors):
                continue
            ins = e.geometry.get("insert") or [0, 0, 0]
            ey = ins[1]
            if anchors:
                closest_anchor = min(anchors, key=lambda a: abs(a["y"] - ey))
                if abs(closest_anchor["y"] - ey) <= 15.0 * bom_coord_scale:
                    closest_anchor["row_ents"].append(e)
                else:
                    anchors.append({"entity": None, "y": ey, "row_ents": [e]})
            else:
                anchors.append({"entity": None, "y": ey, "row_ents": [e]})
                
        anchors.sort(key=lambda a: a["y"], reverse=True)
        rows_grouped = [a["row_ents"] for a in anchors]

        extracted_rows = []
        for group in rows_grouped:
            avg_y = sum(g.geometry.get("insert", [0, 0, 0])[1] for g in group) / len(group)
            row_fields = {}
            row_has_data = False
            
            for col_key, col_def in headers.items():
                hx = col_def["hx"]
                dx_tol = col_def["dx_tol"]
                sdx_tol = dx_tol * bom_coord_scale
                
                col_candidates = []
                for e in group:
                    ins = e.geometry.get("insert") or [0, 0, 0]
                    vx, vy = ins[0], ins[1]
                    dx = abs(vx - hx)
                    if dx <= sdx_tol:
                        dist = math.sqrt((4.0 * (vx - hx)) ** 2 + (vy - avg_y) ** 2)
                        height = e.properties.get("height", 3.0)
                        bbox = e.properties.get("bbox", None)
                        if bbox:
                            try:
                                xmin, ymin = bbox[0]
                                xmax, ymax = bbox[1]
                                box_height = ymax - ymin
                                coords = [xmin - (height * 0.5), ymin + (box_height / 2.0)]
                            except Exception:
                                coords = [vx - (height * 1.5), vy + (height / 2.0)]
                        else:
                            coords = [vx - (height * 1.5), vy + (height / 2.0)]
                        
                        col_candidates.append((dist, e.properties.get("text", "").strip(), coords))
                
                if col_candidates:
                    col_candidates.sort(key=lambda c: c[0])
                    val = col_candidates[0][1]
                    coords = col_candidates[0][2]
                    clean_val = map_signature_value(val)
                    if clean_val != "NONE":
                        row_has_data = True
                else:
                    val = "NONE"
                    coords = [hx, avg_y]
                    clean_val = "NONE"
                
                row_fields[col_key] = {"value": clean_val, "coordinates": coords}
            
            # Only append the row if it contains at least one non-NONE value
            if row_has_data:
                extracted_rows.append(row_fields)

        return extracted_rows, is_assembly

    def build_bom_table(ref_rows: list, rev_rows: list, is_assembly: bool) -> str:
        """Build dynamic ASCII BOM comparison table for all rows (Parts or Assembly format)."""
        def get_val(row_dict, key):
            obj = row_dict.get(key, {})
            if isinstance(obj, dict):
                return obj.get("value", "NONE") or "NONE"
            return obj or "NONE"

        def is_blank_spacer(row):
            if not row:
                return True
            if is_assembly:
                dwg = get_val(row, "DWG_NO")
                title = get_val(row, "TITLE")
                return dwg == "NONE" and title == "NONE"
            else:
                code = get_val(row, "CODE")
                dim = get_val(row, "DIMENSION")
                return code == "NONE" and dim == "NONE"

        # Strip entirely blank spacer rows to handle structural row shifts
        filtered_ref = [r for r in ref_rows if not is_blank_spacer(r)]
        filtered_rev = [r for r in rev_rows if not is_blank_spacer(r)]

        def get_row_key(row):
            no_val = get_val(row, "NO")
            if no_val == "NONE":
                return ""
            return no_val.strip()

        ref_map = {}
        for idx, r in enumerate(filtered_ref):
            k = get_row_key(r)
            if not k:
                k = f"_ref_idx_{idx}"
            ref_map[k] = r

        rev_map = {}
        for idx, r in enumerate(filtered_rev):
            k = get_row_key(r)
            if not k:
                k = f"_rev_idx_{idx}"
            rev_map[k] = r

        all_keys = list(set(ref_map.keys()).union(set(rev_map.keys())))
        
        def key_sort_fn(key_str):
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
        all_keys.sort(key=key_sort_fn)

        def cmp_status(orig, kmti):
            s = compare_values(orig, kmti)
            return "MATCHED" if s == "MATCHED" else "MISMATCHED"

        header = f"{'COLUMN':<32}| {'ORIGINAL':<20}| {'KMTI':<20}| MARKED"
        sep = '-' * len(header)
        lines = [header, sep]

        for key in all_keys:
            ref_row = ref_map.get(key, {})
            rev_row = rev_map.get(key, {})

            row_label = f"Unnumbered Row" if (key.startswith("_ref_idx_") or key.startswith("_rev_idx_")) else f"Item {key}"

            if is_assembly:
                cols = [
                    ("No.",                  "NO"),
                    ("図面番号 / DWG No.",   "DWG_NO"),
                    ("名称 / TITLE",         "TITLE"),
                    ("Q'ty",                "QTY"),
                    ("備考 / Remark",        "REMARK"),
                ]
            else:
                cols = [
                    ("No.",                          "NO"),
                    ("材質 / Code",                  "CODE"),
                    ("材料寸法/型式 / Dimension",     "DIMENSION"),
                    ("材料個数 / Q'ty",              "QTY"),
                    ("素材重量Kg / Material Wt(kg)", "MATERIAL_WEIGHT"),
                    ("仕上重量Kg / Finished Wt(kg)", "FINISHED_WEIGHT"),
                    ("備考 / Remark",                "REMARK"),
                ]

            for label, key_col in cols:
                orig = get_val(ref_row, key_col)
                kmti = get_val(rev_row, key_col)
                s = cmp_status(orig, kmti)
                full_label = f"[{row_label}] {label}"
                lines.append(f"{full_label:<32}| {orig:<20}| {kmti:<20}| {s}")

        return '\n'.join(lines)


    def extract_title_fields(entities: list, all_text_list: list) -> dict:
        """Dynamically search the drawing text tokens for each of the 11 title block fields.
        Returns a dict mapping field name -> extracted value (or 'NONE').
        """
        import math
        import re

        # Phase 4: Native DXF Structural Parsing (Title Block Attributes)
        # Scan for native INSERT block attributes that match Title Block fields
        native_fields = {
            "QTY": "NONE", "CROSS REF NO": "NONE", "PREVIOUS DWG NO": "NONE",
            "DESIGNED": "NONE", "DRAWN": "NONE", "SCALE": "NONE", "NAME": "NONE",
            "TITLE": "NONE", "JOB NO": "NONE", "MACHINE CODE": "NONE", 
            "DWG NO": "NONE", "UNIT NO": "NONE", "PART NO": "NONE", 
            "STOCK QTY": "NONE", "STD NO": "NONE"
        }
        native_coords = {k: None for k in native_fields}
        found_native = False

        for e in entities:
            if getattr(e, "entity_type", "") == "block":
                attrs = getattr(e, "properties", {}).get("attributes", {})
                if attrs:
                    # Mapping generic block attribute tags to our standardized keys
                    for tag, val in attrs.items():
                        t_upper = tag.upper().strip()
                        matched_key = None
                        if "TITLE" in t_upper or "NAME" in t_upper:
                            matched_key = "TITLE"
                        elif "DWG" in t_upper and "NO" in t_upper and "PREV" not in t_upper:
                            matched_key = "DWG NO"
                        elif "PART" in t_upper and "NO" in t_upper:
                            matched_key = "PART NO"
                        elif "QTY" in t_upper and "TOTAL" in t_upper:
                            matched_key = "QTY"
                        elif "SCALE" in t_upper:
                            matched_key = "SCALE"
                        elif "DRAWN" in t_upper:
                            matched_key = "DRAWN"
                        elif "DESIGN" in t_upper:
                            matched_key = "DESIGNED"
                        
                        if matched_key:
                            native_fields[matched_key] = val
                            found_native = True
                            ins = getattr(e, "geometry", {}).get("insert")
                            if ins:
                                native_coords[matched_key] = [ins[0], ins[1]]

        if found_native:
            # Format the output identically to the legacy heuristic output
            res = {}
            for k in native_fields:
                res[k] = {"value": native_fields[k], "coordinates": native_coords[k]}
            return res

        decoded_texts = [safe_decode(t).strip() for t in all_text_list if t.strip()]
        
        # Detect coordinate scale from text entities only
        coord_scale = 1.0
        for e in entities:
            if e.entity_type == "text" and e.geometry:
                ins = e.geometry.get("insert") or [0, 0, 0]
                if ins[0] > 1000:
                    coord_scale = 2.0
                    break

        def is_garbage_value(text: str) -> bool:
            if not text:
                return True
            t = text.strip()
            if len(t) == 0:
                return True
            norm = t.replace(" ", "").lower()
            
            label_keywords = [
                "designed", "設計", "drawn", "製図", "approved", "承認", "checked", "照査",
                "scale", "尺度", "title", "図面名", "図名", "名称", "jobname",
                "jobno.", "工事番号", "unitcode", "mach.code", "ユニット記号", "機番記号", "機器記号",
                "dwg.no.", "図面番号", "dwgno", "previousdwg.no,", "旧図面番号", "crossrefno.", "共通番号",
                "符号", "年月日", "y/m/d", "amd.", "designchgno.", "dir.", "branch", "std.no.", "標準図番号",
                "machine type", "machinetype", "unit no.", "unitno.", "part no.", "partno.", "dir.", "branch", "amd.", "standard",
                "kusakabe", "electric", "machinery", "co.,ltd", "日下部電機", "t.q'ty", "t.q’ty", "総製作個数", "個数", "q'ty", "stockq'ty",
                "機種", "ユニット", "部品", "特性", "訂正符号"
            ]
            
            for kw in label_keywords:
                norm_kw = kw.replace(" ", "").lower()
                if norm_kw == norm or norm_kw in norm or norm in norm_kw:
                    return True
                    
            if len(t) <= 2:
                if not re.search(r'[a-zA-Z0-9\u4e00-\u9faf\u3040-\u309f\u30a0-\u30ff]', t):
                    return True
                ignored_chars = [
                    "工", "事", "番", "号", "発", "尺", "度", "設", "計",
                    "製", "図", "名", "称", "面", "個", "数", "単", "位", "前"
                ]
                for ic in ignored_chars:
                    if ic in t:
                        return True
                        
            if len(t) == 1:
                if re.search(r'[\u4e00-\u9faf\u3040-\u309f\u30a0-\u30ff]', t):
                    return True
                    
            return False

        def extract_proximity_value(label_patterns, direction='below', dx_tol=8.0, dy_tol=25.0, dy_min=1.0, exclude_patterns=None, prefer_lowest_y=False, prefer_highest_y=False):
            scaled_dx_tol = dx_tol * coord_scale
            scaled_dy_tol = dy_tol * coord_scale
            scaled_dy_min = dy_min * coord_scale
            
            label_entities = []
            
            # Exact Match Pass
            for e in entities:
                txt = e.properties.get("text", "").strip()
                decoded = safe_decode(txt).strip()
                norm_txt = txt.replace(" ", "").lower()
                norm_dec = decoded.replace(" ", "").lower()
                
                for pat in label_patterns:
                    norm_pat = pat.replace(" ", "").lower()
                    if norm_pat == norm_txt or norm_pat == norm_dec:
                        if exclude_patterns:
                            exclude_found = False
                            for excl in exclude_patterns:
                                norm_excl = excl.replace(" ", "").lower()
                                if norm_excl in norm_txt or norm_excl in norm_dec:
                                    exclude_found = True
                                    break
                            if exclude_found:
                                continue
                        label_entities.append(e)
                        break
                        
            # Substring Match Pass (fallback)
            if not label_entities:
                for e in entities:
                    txt = e.properties.get("text", "").strip()
                    decoded = safe_decode(txt).strip()
                    norm_txt = txt.replace(" ", "").lower()
                    norm_dec = decoded.replace(" ", "").lower()
                    
                    for pat in label_patterns:
                        norm_pat = pat.replace(" ", "").lower()
                        if len(norm_pat) > 2 and (norm_pat in norm_txt or norm_pat in norm_dec):
                            if exclude_patterns:
                                exclude_found = False
                                for excl in exclude_patterns:
                                    norm_excl = excl.replace(" ", "").lower()
                                    if norm_excl in norm_txt or norm_excl in norm_dec:
                                        exclude_found = True
                                        break
                                if exclude_found:
                                    continue
                            label_entities.append(e)
                            break
                            
            if not label_entities:
                return "NONE", None
                
            if prefer_lowest_y:
                def get_y(ent):
                    geom = ent.geometry or {}
                    ins = geom.get("insert") or [0, 0, 0]
                    return ins[1]
                label_entities.sort(key=get_y)
            elif prefer_highest_y:
                def get_y(ent):
                    geom = ent.geometry or {}
                    ins = geom.get("insert") or [0, 0, 0]
                    return ins[1]
                label_entities.sort(key=get_y, reverse=True)
                
            label_entity = label_entities[0]
            
            geom = label_entity.geometry or {}
            ins = geom.get("insert") or [0, 0, 0]
            lx, ly = ins[0], ins[1]
            
            candidates = []
            for e in entities:
                if e == label_entity:
                    continue
                txt = e.properties.get("text", "").strip()
                if not txt:
                    continue
                    
                decoded = safe_decode(txt).strip()
                if is_garbage_value(decoded):
                    continue
                    
                if exclude_patterns:
                    exclude_found = False
                    norm_txt_c = txt.replace(" ", "").lower()
                    norm_dec_c = decoded.replace(" ", "").lower()
                    for excl in exclude_patterns:
                        norm_excl = excl.replace(" ", "").lower()
                        if norm_excl in norm_txt_c or norm_excl in norm_dec_c:
                            exclude_found = True
                            break
                    if exclude_found:
                        continue
                        
                e_geom = e.geometry or {}
                e_ins = e_geom.get("insert") or [0, 0, 0]
                vx, vy = e_ins[0], e_ins[1]
                
                if direction == 'below':
                    if abs(vx - lx) <= scaled_dx_tol and scaled_dy_min <= (ly - vy) <= scaled_dy_tol:
                        dist = math.sqrt((4.0 * (vx - lx))**2 + (vy - ly)**2)
                        h = e.properties.get("height", 3.0)
                        bbox = e.properties.get("bbox")
                        if bbox and len(bbox) >= 2:
                            xmax, ymin, ymax = bbox[1][0], bbox[0][1], bbox[1][1]
                            candidates.append((dist, decoded, [xmax + (h * 0.8), ymin + ((ymax - ymin) / 2.0)]))
                        else:
                            candidates.append((dist, decoded, [vx + (h * 0.8), vy + (h * 0.5)]))
                elif direction == 'right':
                    effective_dy_tol = max(scaled_dy_tol, 25.0 * coord_scale)
                    if abs(vy - ly) <= effective_dy_tol and scaled_dy_min <= (vx - lx) <= scaled_dx_tol:
                        dist = math.sqrt((vx - lx)**2 + (4.0 * (vy - ly))**2)
                        h = e.properties.get("height", 3.0)
                        bbox = e.properties.get("bbox")
                        if bbox and len(bbox) >= 2:
                            xmax, ymin, ymax = bbox[1][0], bbox[0][1], bbox[1][1]
                            candidates.append((dist, decoded, [xmax + (h * 0.8), ymin + ((ymax - ymin) / 2.0)]))
                        else:
                            candidates.append((dist, decoded, [vx + (h * 0.8), vy + (h * 0.5)]))
                        
            if not candidates:
                return "NONE", [lx, ly]
                
            candidates.sort(key=lambda item: item[0])
            closest_candidate = candidates[0]
            cx, cy = closest_candidate[2][0], closest_candidate[2][1]
            
            # Find all vertically stacked text entities sharing a similar column
            grouped_ents = []
            seen_texts = set()
            for e in entities:
                if e.entity_type != "text":
                    continue
                txt = e.properties.get("text", "").strip()
                if not txt:
                    continue
                decoded = safe_decode(txt).strip()
                if is_garbage_value(decoded):
                    continue
                
                e_geom = e.geometry or {}
                e_ins = e_geom.get("insert") or [0, 0, 0]
                vx, vy = e_ins[0], e_ins[1]
                
                if exclude_patterns:
                    exclude_found = False
                    norm_txt_c = txt.replace(" ", "").lower()
                    norm_dec_c = decoded.replace(" ", "").lower()
                    for excl in exclude_patterns:
                        norm_excl = excl.replace(" ", "").lower()
                        if norm_excl in norm_txt_c or norm_excl in norm_dec_c:
                            exclude_found = True
                            break
                    if exclude_found:
                        continue
                
                
                # Check horizontal proximity to label and vertical proximity to closest candidate
                # Fix B2a: Widen horizontal entry gate from 5.0→30.0 units. In compact title blocks
                # the value text can appear at the same X as, or slightly LEFT of, the label anchor.
                # Without this widening, the stacking loop never captures the second row of 名称 TITLE.
                # Fix B3: Expand the vertical grouping step cluster radius from 35.0 to 80.0
                if vx >= lx - 30.0 * coord_scale and (vx - lx) <= scaled_dx_tol:
                    if abs(vx - cx) <= 10.0 * coord_scale and abs(vy - cy) <= 80.0 * coord_scale:
                        if decoded not in seen_texts:
                            seen_texts.add(decoded)
                            h = e.properties.get("height", 3.0)
                            bbox = e.properties.get("bbox")
                            if bbox and len(bbox) >= 2:
                                xmax, ymin, ymax = bbox[1][0], bbox[0][1], bbox[1][1]
                                grouped_ents.append((vy, decoded, [xmax + (h * 0.8), ymin + ((ymax - ymin) / 2.0)]))
                            else:
                                grouped_ents.append((vy, decoded, [vx + (h * 0.8), vy + (h * 0.5)]))
            
            # Include the closest candidate in the grouped entities if it's not already there
            if not any(item[1] == closest_candidate[1] for item in grouped_ents):
                grouped_ents.append((cy, closest_candidate[1], closest_candidate[2]))

            if len(grouped_ents) > 0:
                # Sort from top to bottom (Y descending, since DXF Y-upwards means top row has higher Y)
                grouped_ents.sort(key=lambda item: item[0], reverse=True)
                merged_text = "\n".join([item[1] for item in grouped_ents])
                # Use the coordinates of the top-most entity
                return merged_text, grouped_ents[0][2]
            else:
                return closest_candidate[1], closest_candidate[2]

        def find_entity_coords(target_text: str) -> Optional[list[float]]:
            if not target_text or target_text == "NONE":
                return None
            target_norm = target_text.strip().replace(" ", "").replace("\n", "").lower()
            
            def get_centered_coords(e):
                h = e.properties.get("height", 3.0)
                bbox = e.properties.get("bbox")
                if bbox and len(bbox) >= 2:
                    return [bbox[1][0] + (h * 0.8), bbox[0][1] + ((bbox[1][1] - bbox[0][1]) / 2.0)]
                e_geom = e.geometry or {}
                e_ins = e_geom.get("insert") or [0, 0, 0]
                return [e_ins[0] + (h * 0.8), e_ins[1] + (h * 0.5)]

            # Try to match in title layers first to avoid snapping to zone numbers or other text
            for e in entities:
                if e.entity_type == "text":
                    layer_lower = e.layer.lower() if e.layer else ""
                    is_title_layer = any(x in layer_lower for x in ["title", "header", "border", "stamp", "admin", "block", "logo", "dwg", "rev", "qty", "date"])
                    if is_title_layer:
                        raw_txt = e.properties.get("text", "")
                        if raw_txt:
                            decoded = safe_decode(raw_txt).strip()
                            if decoded.lower() == target_norm:
                                return get_centered_coords(e)
            # Try exact match in all layers
            for e in entities:
                if e.entity_type == "text":
                    raw_txt = e.properties.get("text", "")
                    if raw_txt:
                        decoded = safe_decode(raw_txt).strip()
                        if decoded.lower() == target_norm:
                            return get_centered_coords(e)
            # Substring match in title layers
            for e in entities:
                if e.entity_type == "text":
                    layer_lower = e.layer.lower() if e.layer else ""
                    is_title_layer = any(x in layer_lower for x in ["title", "header", "border", "stamp", "admin", "block", "logo", "dwg", "rev", "qty", "date"])
                    if is_title_layer:
                        raw_txt = e.properties.get("text", "")
                        if raw_txt:
                            decoded = safe_decode(raw_txt).strip()
                            if target_norm in decoded.lower():
                                return get_centered_coords(e)
            # Substring match in all layers
            for e in entities:
                if e.entity_type == "text":
                    raw_txt = e.properties.get("text", "")
                    if raw_txt:
                        decoded = safe_decode(raw_txt).strip()
                        if target_norm in decoded.lower():
                            return get_centered_coords(e)
            return None

        qty, qty_coords = extract_proximity_value(["T. Q'ty", "T. Q\u2019ty", "総製作個数"], "right", 150.0, 6.0, 1.0, ["Stock", "在庫", "棚入庫"], prefer_highest_y=True)
        cross_ref, cross_ref_coords = extract_proximity_value(["Cross ref No.", "共通番号"], "below", 5.0, 30.0, 1.0, ["Previous", "旧"], prefer_lowest_y=True)
        prev_dwg, prev_dwg_coords = extract_proximity_value(["Previous Dwg. No,", "Previous Dwg. No.", "旧図面番号"], "below", 5.0, 30.0, 1.0, prefer_lowest_y=True)
        designed, designed_coords = extract_proximity_value(["DESIGNED", "設計"], "below", 10.0, 30.0, 1.0, prefer_lowest_y=True)
        drawn, drawn_coords = extract_proximity_value(["DRAWN", "製図"], "below", 10.0, 30.0, 1.0, prefer_lowest_y=True)
        scale, scale_coords = extract_proximity_value(["SCALE", "尺度"], "below", 10.0, 30.0, 1.0, prefer_lowest_y=True)
        name, name_coords = extract_proximity_value(["名称", "名 称"], "right", 150.0, 6.0, 1.0, prefer_lowest_y=True)
        title, title_coords = extract_proximity_value(["TITLE", "図面名", "図 名"], "right", 150.0, 6.0, 1.0, prefer_lowest_y=True)
        job_no, job_no_coords = extract_proximity_value(["Job No.", "工事番号"], "right", 80.0, 6.0, 1.0, prefer_lowest_y=True)
        mach_code, mach_code_coords = extract_proximity_value(["Unit Code", "Mach. code", "ユニット記号", "機番記号"], "below", 20.0, 30.0, 1.0, prefer_lowest_y=True)
        dwg_no, dwg_no_coords = extract_proximity_value(["DWG.No.", "図面番号"], "right", 100.0, 6.0, 1.0, ["Previous", "旧"], prefer_lowest_y=True)
        unit_no, unit_no_coords = extract_proximity_value(["Unit No.", "ユニットNo."], "below", 20.0, 30.0, 1.0, prefer_highest_y=True)
        part_no, part_no_coords = extract_proximity_value(["Part No.", "コードNo."], "below", 20.0, 30.0, 1.0, prefer_highest_y=True)
        stock_qty, stock_qty_coords = extract_proximity_value(["Stock Q'ty", "在庫棚入庫"], "below", 20.0, 30.0, 1.0, prefer_highest_y=True)
        std_no, std_no_coords = extract_proximity_value(["Std. No.", "標準図番号"], "below", 20.0, 30.0, 1.0, prefer_highest_y=True)

        # Apply signature mapping to mapped clean values
        qty = map_signature_value(qty)
        cross_ref = map_signature_value(cross_ref)
        prev_dwg = map_signature_value(prev_dwg)
        designed = map_signature_value(designed)
        drawn = map_signature_value(drawn)
        scale = map_signature_value(scale)
        name = map_signature_value(name)
        title = map_signature_value(title)
        job_no = map_signature_value(job_no)
        mach_code = map_signature_value(mach_code)
        dwg_no = map_signature_value(dwg_no)
        unit_no = map_signature_value(unit_no)
        part_no = map_signature_value(part_no)
        stock_qty = map_signature_value(stock_qty)
        std_no = map_signature_value(std_no)

        # Dynamic fallbacks using decoded text list — NO hardcoded project values.
        # Each field uses structural/format patterns to identify the correct value
        # from whatever text tokens are present in this specific drawing.

        # QTY: accept any small positive integer (1–999) that appears in the text list.
        if qty == "NONE" or is_garbage_value(qty) or qty.lower() in ["t.q'ty", "個数", "総製作個数", "stockq'ty"]:
            for t in decoded_texts:
                if re.match(r'^\d{1,3}$', t.strip()) and 1 <= int(t.strip()) <= 999:
                    fallback_coords = find_entity_coords(t.strip())
                    if fallback_coords is not None:
                        qty = t.strip()
                        qty_coords = fallback_coords
                        break

        # DESIGNED / DRAWN: accept any CJK-name-like token or short Latin initialism
        # that appears near the extracted label. Do not inject specific person names.
        # The extract_proximity_value call above already covers the primary extraction.
        # Only clear garbage values; leave "NONE" as-is if proximity search returned nothing.
        if designed != "NONE" and is_garbage_value(designed):
            designed = "NONE"
            designed_coords = None
        if drawn != "NONE" and is_garbage_value(drawn):
            drawn = "NONE"
            drawn_coords = None

        # SCALE: match any ratio-formatted token (e.g. "1:2", "2:1", "1/4", "1/10").
        if scale == "NONE" or is_garbage_value(scale) or scale.lower() in ["scale", "尺度"]:
            for t in decoded_texts:
                if re.match(r'^\d+\s*[:/]\s*\d+$', t.strip()):
                    fallback_coords = find_entity_coords(t.strip())
                    if fallback_coords is not None:
                        scale = t.strip()
                        scale_coords = fallback_coords
                        break

        # NAME: accept the longest non-garbage token that contains at least one CJK character
        # and is not a label keyword — works for any drawing, any product name.
        if name == "NONE" or is_garbage_value(name) or any(x in name for x in ["名称", "name", "機種"]):
            name_candidates = [
                t for t in decoded_texts
                if re.search(r'[\u3000-\u9fff\uff00-\uffef]', t)
                and not is_garbage_value(t)
                and len(t) >= 3
            ]
            if name_candidates:
                name_candidates.sort(key=lambda s: len(s), reverse=True)
                for cand in name_candidates:
                    fallback_coords = find_entity_coords(cand)
                    if fallback_coords is not None:
                        name = cand
                        name_coords = fallback_coords
                        break

        # TITLE: same pattern as NAME but look for a second distinct long CJK token
        # (the drawing title is often a different string from the name/job-name field).
        if title == "NONE" or is_garbage_value(title) or any(x in title for x in ["title", "図面名", "図名"]):
            title_candidates = [
                t for t in decoded_texts
                if re.search(r'[\u3000-\u9fff\uff00-\uffef]', t)
                and not is_garbage_value(t)
                and len(t) >= 3
                and t != name  # avoid duplicating the NAME field value
            ]
            if title_candidates:
                title_candidates.sort(key=lambda s: len(s), reverse=True)
                for cand in title_candidates:
                    fallback_coords = find_entity_coords(cand)
                    if fallback_coords is not None:
                        title = cand
                        title_coords = fallback_coords
                        break

        # JOB NO: accept any 4-to-8-digit numeric token that is not already used as qty.
        if job_no == "NONE" or is_garbage_value(job_no) or job_no.lower() in ["job", "jobno."]:
            for t in decoded_texts:
                if re.match(r'^\d{4,8}$', t.strip()) and t.strip() != qty:
                    fallback_coords = find_entity_coords(t.strip())
                    if fallback_coords is not None:
                        job_no = t.strip()
                        job_no_coords = fallback_coords
                        break

        # MACH CODE: accept any short alphanumeric code token that contains at least
        # one letter and one digit (e.g. "RCGR4", "AXB-1", "CR-200"). Works for any
        # machine code format — not tied to a specific project's coding scheme.
        if mach_code == "NONE" or is_garbage_value(mach_code):
            for t in decoded_texts:
                t_clean = t.strip()
                if (re.match(r'^[A-Za-z0-9\-_]{2,16}$', t_clean)
                        and re.search(r'[A-Za-z]', t_clean)
                        and re.search(r'[0-9]', t_clean)):
                    fallback_coords = find_entity_coords(t_clean)
                    if fallback_coords is not None:
                        mach_code = t_clean
                        mach_code_coords = fallback_coords
                        break
        # Fix B1 fallback: if mach_code is still NONE but unit_no/part_no resolved a non-integer
        # code string (containing letters), promote it as the machine code. This handles DXF layouts
        # where the proximity scanner anchors on the wrong label entity for the MACHINE CODE column.
        if (mach_code == "NONE" or is_garbage_value(mach_code)) and unit_no != "NONE" and not unit_no.isdigit():
            mach_code = unit_no
            mach_code_coords = unit_no_coords
        if (mach_code == "NONE" or is_garbage_value(mach_code)) and part_no != "NONE" and not part_no.isdigit():
            mach_code = part_no
            mach_code_coords = part_no_coords

        # DWG NO: accept any token matching a typical drawing-number pattern —
        # alphanumeric with at least 4 characters, may include hyphens or dots.
        # This covers formats like "CR19061", "DW-2024-001", "A3-00123", etc.
        if dwg_no == "NONE" or is_garbage_value(dwg_no) or any(x in dwg_no for x in ["図", "圖", "図面", "機種"]):
            for t in decoded_texts:
                t_clean = t.strip()
                if (re.match(r'^[A-Za-z0-9][\w\-\.]{3,24}$', t_clean)
                        and re.search(r'[A-Za-z]', t_clean)
                        and re.search(r'[0-9]', t_clean)
                        and t_clean != mach_code
                        and t_clean != job_no):
                    fallback_coords = find_entity_coords(t_clean)
                    if fallback_coords is not None:
                        dwg_no = t_clean
                        dwg_no_coords = fallback_coords
                        break

        # Fallback coordinate lookup for any field value that doesn't have coordinates
        if qty != "NONE" and qty_coords is None:
            qty_coords = find_entity_coords(qty)
        if cross_ref != "NONE" and cross_ref_coords is None:
            cross_ref_coords = find_entity_coords(cross_ref)
        if prev_dwg != "NONE" and prev_dwg_coords is None:
            prev_dwg_coords = find_entity_coords(prev_dwg)
        if designed != "NONE" and designed_coords is None:
            designed_coords = find_entity_coords(designed)
        if drawn != "NONE" and drawn_coords is None:
            drawn_coords = find_entity_coords(drawn)
        if scale != "NONE" and scale_coords is None:
            scale_coords = find_entity_coords(scale)
        if name != "NONE" and name_coords is None:
            name_coords = find_entity_coords(name)
        if title != "NONE" and title_coords is None:
            title_coords = find_entity_coords(title)
        if job_no != "NONE" and job_no_coords is None:
            job_no_coords = find_entity_coords(job_no)
        if mach_code != "NONE" and mach_code_coords is None:
            mach_code_coords = find_entity_coords(mach_code)
        if dwg_no != "NONE" and dwg_no_coords is None:
            dwg_no_coords = find_entity_coords(dwg_no)
        if unit_no != "NONE" and unit_no_coords is None:
            unit_no_coords = find_entity_coords(unit_no)
        if part_no != "NONE" and part_no_coords is None:
            part_no_coords = find_entity_coords(part_no)
        if stock_qty != "NONE" and stock_qty_coords is None:
            stock_qty_coords = find_entity_coords(stock_qty)
        if std_no != "NONE" and std_no_coords is None:
            std_no_coords = find_entity_coords(std_no)

        res = {
            "QTY": {"value": qty, "coordinates": qty_coords},
            "CROSS REF NO": {"value": cross_ref, "coordinates": cross_ref_coords},
            "PREVIOUS DWG NO": {"value": prev_dwg, "coordinates": prev_dwg_coords},
            "DESIGNED": {"value": designed, "coordinates": designed_coords},
            "DRAWN": {"value": drawn, "coordinates": drawn_coords},
            "SCALE": {"value": scale, "coordinates": scale_coords},
            "NAME": {"value": name, "coordinates": name_coords},
            "TITLE": {"value": title, "coordinates": title_coords},
            "JOB NO": {"value": job_no, "coordinates": job_no_coords},
            "MACHINE CODE": {"value": mach_code, "coordinates": mach_code_coords},
            "DWG NO": {"value": dwg_no, "coordinates": dwg_no_coords},
            "UNIT NO": {"value": unit_no, "coordinates": unit_no_coords},
            "PART NO": {"value": part_no, "coordinates": part_no_coords},
            "STOCK QTY": {"value": stock_qty, "coordinates": stock_qty_coords},
            "STD NO": {"value": std_no, "coordinates": std_no_coords}
        }
        for k, v in res.items():
            if v["value"] is None or str(v["value"]).strip().lower() in ["none", ""]:
                res[k] = {"value": "NONE", "coordinates": v.get("coordinates")}
        return res

    ref_all_text_list = []
    for e in ref_entities:
        if e.entity_type == "text":
            raw_txt = e.properties.get("text")
            if raw_txt is not None:
                txt = str(raw_txt).strip()
                if txt:
                    ref_all_text_list.append(map_signature_value(safe_decode(txt)))
    ref_all_text = "\n".join(sorted(list(set(ref_all_text_list))))

    rev_all_text_list = []
    for e in rev_entities:
        if e.entity_type == "text":
            raw_txt = e.properties.get("text")
            if raw_txt is not None:
                txt = str(raw_txt).strip()
                if txt:
                    rev_all_text_list.append(map_signature_value(safe_decode(txt)))
    rev_all_text = "\n".join(sorted(list(set(rev_all_text_list))))

    # Build pre-computed Title Block field comparison table (Python-side, dynamically from actual drawing data)
    ref_title_fields = extract_title_fields(ref_entities, ref_all_text_list)
    rev_title_fields = extract_title_fields(rev_entities, rev_all_text_list)
    title_block_table = build_title_block_table(ref_title_fields, rev_title_fields)

    # Build pre-computed BOM table (Python-side, using actual drawing vector text)
    ref_bounds = ref_drawing.metadata.get("render_bounds") if ref_drawing and ref_drawing.metadata else None
    rev_bounds = rev_drawing.metadata.get("render_bounds") if rev_drawing and rev_drawing.metadata else None
    ref_bom_rows, ref_is_assembly = extract_bom_fields(ref_entities, render_bounds=ref_bounds)
    rev_bom_rows, rev_is_assembly = extract_bom_fields(rev_entities, render_bounds=rev_bounds)
    # Assembly if either drawing is classified as assembly
    is_assembly_drawing = ref_is_assembly or rev_is_assembly
    bom_comparison_table = build_bom_table(ref_bom_rows, rev_bom_rows, is_assembly_drawing)
    logger.info(f"BOM extraction complete - is_assembly={is_assembly_drawing}, ref_bom_rows={ref_bom_rows}, rev_bom_rows={rev_bom_rows}")
    # --- Compute spatial region bounding boxes for BOM and Title Block ---
    # These are used to constrain find_drawing_text_coordinates to the correct
    # geometric zone even when all entities share a generic layer name.
    def _spatial_region(rows: list, fields: dict, entities: list) -> Optional[tuple]:
        """Return (xmin, ymin, xmax, ymax) covering all BOM row coordinates and
        title-block field coordinates extracted from a drawing's entities."""
        xs, ys = [], []
        # BOM row coords
        for row in rows:
            for cell in row.values():
                if isinstance(cell, dict):
                    c = cell.get("coordinates")
                    if c and len(c) >= 2:
                        xs.append(c[0]); ys.append(c[1])
        # Title block coords
        for cell in fields.values():
            if isinstance(cell, dict):
                c = cell.get("coordinates")
                if c and len(c) >= 2:
                    xs.append(c[0]); ys.append(c[1])
        if not xs:
            return None
        pad = 50.0  # generous padding so nearby labels are included
        return (min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad)

    def _bom_region(rows: list, entities: list) -> Optional[tuple]:
        xs, ys = [], []
        for row in rows:
            for cell in row.values():
                if isinstance(cell, dict):
                    c = cell.get("coordinates")
                    if c and len(c) >= 2:
                        xs.append(c[0]); ys.append(c[1])
        if not xs:
            return None
        pad = 40.0
        return (min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad)

    def _title_region(fields: dict, entities: list) -> Optional[tuple]:
        xs, ys = [], []
        for cell in fields.values():
            if isinstance(cell, dict):
                c = cell.get("coordinates")
                if c and len(c) >= 2:
                    xs.append(c[0]); ys.append(c[1])
        if not xs:
            return None
        pad = 40.0
        return (min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad)

    ref_bom_bbox   = _bom_region(ref_bom_rows, ref_entities)
    rev_bom_bbox   = _bom_region(rev_bom_rows, rev_entities)
    ref_title_bbox = _title_region(ref_title_fields, ref_entities)
    rev_title_bbox = _title_region(rev_title_fields, rev_entities)

    logger.info(f"Spatial regions - rev BOM bbox: {rev_bom_bbox} | rev Title bbox: {rev_title_bbox}")

    if rev_bom_bbox and rev_title_bbox:
        _, bom_ymin, _, bom_ymax = rev_bom_bbox
        _, title_ymin, _, title_ymax = rev_title_bbox
        if not (bom_ymin > title_ymax or title_ymin > bom_ymax):
            logger.warning(f"Spatial region overlap detected! BOM: {rev_bom_bbox}, Title: {rev_title_bbox}")

    # Isometric View dynamic detection
    ref_has_iso = any("iso" in e.layer.lower() or "isometric" in e.layer.lower() for e in ref_entities)
    rev_has_iso = any("iso" in e.layer.lower() or "isometric" in e.layer.lower() for e in rev_entities)

    ref_iso_text = "Isometric View Present" if ref_has_iso else "No Isometric View"
    rev_iso_text = "Isometric View Present" if rev_has_iso else "No Isometric View"

    # --- ATTEMPT GEMINI 2.5 PRO VISUAL COMPARISON SCAN ---
    api_key = os.environ.get("GEMINI_API_KEY") or getattr(settings, "GEMINI_API_KEY", None)
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Gemini API Key is not configured on the backend server. Please add a valid GEMINI_API_KEY to your .env file."
        )

    try:
        logger.info("Initializing active google-genai structured comparison client...")
        client = genai.Client(api_key=api_key)
        
        system_instruction = (
            "You are a meticulous industrial manufacturing inspector and expert engineering drawing checker.\n"
            "Analyze technical drawings character-by-character for deep semantic differences. "
            "Do not provide generic high-level count summaries like 'lines: 250 vs 255'.\n"
            "You must perform a rigorous, exhaustive comparison of all technical contents and text, detecting procedural inconsistencies, and identifying manufacturing-impact changes.\n"
            "Treat even minor differences in decimal precision (e.g., '2.6' vs '2.60'), font spacing, line styles, case sensitivity, alignment, or dimension placements as explicit engineering discrepancies.\n"
            "Understand sheet templates and positioning variations: Notes and Isometric views do not have a fixed position, as they depend on which side of the template has a wide blank space. "
            "Note that Notes are mostly positioned below the upper-left title block, and Isometric views are typically positioned below the BOM on the upper-right.\n"
            "Understand that the main DRAWING VIEWS (orthographic, sectional, or detailed geometry) are typically positioned and displayed in the center of the sheet template. "
            "It is of critical, absolute importance to review and check all physical dimensions, precision tolerances, and geometric specifications character-by-character to prevent manufacturing defects."
        )


        prompt = (
            "Act as an automated engineering checker. Review and audit character-by-character the visual and structural differences between two technical drawing versions using the following semantic variables:\n\n"
            "1. DRAWING VIEWS (Main Geometry Area):\n"
            f"   Reference (Original): {ref_geom if ref_geom else 'No callouts detected'}\n"
            f"   Revision (KMTI): {rev_geom if rev_geom else 'No callouts detected'}\n\n"
            "2. NOTES SECTION (Manufacturing Instructions):\n"
            f"   Reference (Original): {ref_notes if ref_notes else 'No rules detected'}\n"
            f"   Revision (KMTI): {rev_notes if rev_notes else 'No rules detected'}\n\n"
            "3. BILL OF MATERIALS (BOM Table):\n"
            "   CATEGORY RULE: Every canvas_marking for a BOM item (No., Name, Q'ty, Material, "
            "Code, Weight, Remark) MUST use \"category\": \"bill_of_materials\". "
            "NEVER use \"title_block\" for BOM rows, even if the value (e.g. '1') also appears "
            "in the title block. The category is determined by the physical table location, not "
            "the string value.\n"
            f"   Reference (Original): {ref_bom if ref_bom else 'No BOM data detected'}\n"
            f"   Revision (KMTI): {rev_bom if rev_bom else 'No BOM data detected'}\n\n"
            "4. TITLE BLOCK (Pre-extracted 11-field comparison table — values are REAL, dynamically read from the actual drawings):\n"
            f"{title_block_table}\n\n"
            "5. ISOMETRIC VIEW (ISO View):\n"
            f"   Reference (Original): {ref_iso_text}\n"
            f"   Revision (KMTI): {rev_iso_text}\n\n"
            "6. OTHER ENGINEERING REFERENCES:\n"
            "   Reference (Original): Full grid frame line indicators across outer margins.\n"
            "   Revision (KMTI): Definitive CAD boundary ticks (┌ ┐) along print space margins.\n\n"

            "AUDIT INSTRUCTIONS FOR EACH CATEGORY:\n\n"
            "1. DRAWING VIEWS:\n"
            "   - Keep in mind that Drawing views (orthographic, sectional, or detailed geometry) are typically positioned/displayed in the center of the sheet template.\n"
            "   - It is of critical, absolute importance to review and check all physical dimensions, precision tolerance ranges, line weights, chamfer symbols (e.g. '2-C1' vs '4-C1'), hole labels (e.g. 'M24' vs 'M24通シ'), and geometric specifications character-by-character.\n"
            "   - You must detect and compare all orthographic views (Front/Top/Side views), cross-sectional views, detailed views, arrow directions, geometry layouts, shape structures, hole positions, dimensions, radius values, chamfers, weld symbols, surface symbols, geometric tolerances, line types, text styles, font spacing, dimension placements, and annotation placements.\n"
            "   - Fix B4: You MUST also detect and generate canvas_markings for the following structural annotation types which are critical for manufacturing verification:\n"
            "       * Balloon tags: circled item numbers (e.g. ①, ②, ③, or (1), (2), (3)) that reference BOM rows.\n"
            "       * Chamfer and radius annotations: e.g. 'C1', '2-C1', '4-C1', 'R5', '3XR2'. These are distinct from dimension lines.\n"
            "       * Machining symbols: surface finish callouts such as '▽', '6.3a', '▽▽', or symbols in parentheses indicating machining-before-welding sequence.\n"
            "       * Welding symbols: weld callout strings attached to seam lines, e.g. fillet size, weld type designators.\n"
            "       * GD&T control frame text: geometric tolerance values, datum reference letters (e.g. 'A', 'B', 'Ø0.05 A'), flatness, parallelism, or cylindricity callouts.\n"
            "   - Enforce exact drawing view comparison behavior:\n"
            "     * Detect missing views.\n"
            "     * Detect newly added views (e.g., if Original has no sectional view and KMTI has a sectional view, report status as ADDED with description 'ADDED VIEW').\n"
            "     * Detect moved geometry.\n"
            "     * Detect changed dimensions (e.g. if Original has 'Ø10 hole' and KMTI has 'Ø12 hole', report status as CHANGED with exact change notes).\n"
            "     * Detect symbol differences, spacing differences, and font differences.\n"
            "   - Smallest differences in symbols (e.g. 'Ø10' vs 'Ø12'), arrow alignments, text heights, or Katakana/Kanji changes ('M24' vs 'M24通シ') must be caught and reported under CHANGED status.\n"
            "   - You must review all main dimensions (e.g. 38, 12, 105, 65, etc.). Check the Full Text lists to verify if a dimension exists in both drawings. Do not report a dimension as deleted (ghost discrepancy) if it is present in the revised drawing's text list.\n\n"
            "2. NOTES SECTION:\n"
            "   - Keep in mind that the position of notes in the drawing may not always be in one place; they are positioned depending on the free space in the drawing template.\n"
            "   - Read instructions line-by-line and preserve formatting.\n"
            "   - ENFORCE STRICT PROCESS SEQUENCE: Process notes MUST be organized chronologically according to the processes the parts will undergo. Validate the following hierarchy:\n"
            "       a. Machining before welding (for welded parts): Ensure parts with a machining symbol inside parentheses indicate that machining must be processed first before welding.\n"
            "       b. Welding notes.\n"
            "       c. Annealing and Shot blasting process.\n"
            "       d. Surface treatment or Surface coating.\n"
            "       e. Additional drawing notes.\n"
            "       f. Standard notes (The standard notes MUST ALWAYS be placed at the very end/last part of the notes section).\n"
            "   - Detect added notes, removed notes, modified notes, formatting changes, symbol changes, or swapped line hierarchies that violate this process sequence.\n\n"
            "3. BILL OF MATERIALS (BOM):\n"
            "   - Compare row by row, column by column, cell by cell.\n"
            "   - Rigorously check all columns including: 'Unit No.', 'Part No.', 'T. Q'ty', 'Stock Q'ty', 'No.', 'Code', 'Dimension/Model No.', 'Material Weight (kg)', 'Finished Weight (kg)', and 'Remark'.\n"
            "   - Verify if a BOM is present in the original drawing by checking the original Full Text list. Do not report that the original drawing has no BOM if BOM keywords or material texts (e.g., 'SS400', 'Material', '材質') are present in its full text list.\n"
            "   - Any decimal precision change (e.g., '2.6' vs '2.60'), spacing difference, material type update ('SS400' vs 'SUS304'), or row counts mismatch must be flagged as CHANGED.\n\n"
            "4. TITLE BLOCK (Metadata cross-check):\n"
            "   - You MUST extract and cross-check the following 11 exact metadata fields one-by-one between reference (Original) and revised (KMTI) drawings:\n"
            "     * QTY (located in the upper-left administrative grid under '総製作個数' / 'T. Q\'ty')\n"
            "     * CROSS REF NO. (located in the bottom-right block under '共通番号' / 'Cross ref No.')\n"
            "     * PREVIOUS DWG NO (located in the bottom-right block under '旧図面番号' / 'Previous Dwg. No.')\n"
            "     * DESIGNED (located in the bottom-right block under '設計' / 'DESIGNED')\n"
            "     * DRAWN (located in the bottom-right block under '製図' / 'DRAWN')\n"
            "     * SCALE (located in the bottom-right block under '尺度' / 'SCALE')\n"
            "     * NAME (located in the bottom-right block under '名称' / 'Job Name' / 'Name')\n"
            "     * TITLE (located in the bottom-right block under '図面名' / 'TITLE')\n"
            "     * JOB NO. (located in the bottom-right block under '工事番号' / 'Job No.')\n"
            "     * MACHINE CODE / UNIT CODE (located in the bottom-right block under '機番記号' / 'ユニット記号' / 'Unit Code' / 'Machine Type')\n"
            "     * DWG NO. (located in the bottom-right block under '図面番号' / 'DWG. No.')\n"
            "   - Check each field carefully from the drawings text content.\n"
            "   - CRITICAL — DO NOT HARDCODE ANY VALUES: All values in the comparison table MUST be dynamically read from the actual drawing sheet text data. The table format shown below is only a structural template/example. Every <orig_val> and <kmti_val> placeholder MUST be replaced with the real extracted value from the drawings, or 'NONE' if that field is completely blank or absent. Check the Full Text lists to verify whether a value exists before setting it to NONE.\n"
            "   - SCALE FIELD EQUIVALENCE RULE: When comparing the SCALE field, treat the colon separator and the slash separator as identical notation formats. For example, '1:4' and '1/4' represent exactly the same scale ratio and MUST be marked as MATCHED — do not flag this as a mismatch. Normalize the scale value by replacing ':' with '/' (or vice versa) before comparison.\n"
            "   - For the `title_block` checklist category in your JSON response:\n"
            "     * Set `reference_content` and `revision_content` to the EXACT SAME beautifully aligned ASCII/text table comparing all 11 fields. This format below is only the STRUCTURAL TEMPLATE — replace every placeholder with real dynamic values extracted from the drawings:\n"
            "       ```\n"
            "                                         |  ORIGINAL       | KMTI            | MARKED\n"
            "       QTY                               | <actual_orig>   | <actual_kmti>   | <MATCHED/MISMATCHED>\n"
            "       CROSS REF NO.                     | <actual_orig>   | <actual_kmti>   | <MATCHED/MISMATCHED>\n"
            "       - PREVIOUS DWG NO                 | <actual_orig>   | <actual_kmti>   | <MATCHED/MISMATCHED>\n"
            "       - DESIGNED                        | <actual_orig>   | <actual_kmti>   | <MATCHED/MISMATCHED>\n"
            "       - DRAWN                           | <actual_orig>   | <actual_kmti>   | <MATCHED/MISMATCHED>\n"
            "       - SCALE                           | <actual_orig>   | <actual_kmti>   | <MATCHED/MISMATCHED>\n"
            "       - NAME                            | <actual_orig>   | <actual_kmti>   | <MATCHED/MISMATCHED>\n"
            "       - TITLE                           | <actual_orig>   | <actual_kmti>   | <MATCHED/MISMATCHED>\n"
            "       - JOB NO.                         | <actual_orig>   | <actual_kmti>   | <MATCHED/MISMATCHED>\n"
            "       - MACHINE CODE / UNIT CODE        | <actual_orig>   | <actual_kmti>   | <MATCHED/MISMATCHED>\n"
            "       - DWG NO.                         | <actual_orig>   | <actual_kmti>   | <MATCHED/MISMATCHED>\n"
            "       ```\n"
            "     * Enforce status rules: If any of the 11 fields has meaningfully different values between ORIGINAL and KMTI (after applying equivalence rules like scale notation), the overall status of `title_block` MUST be 'CHANGED'. If they are all equivalent, it is 'MATCHED'.\n"
            "     * Set `difference_summary` to a concise 1-2 sentence description summarizing the title block check outcome (e.g. 'All 11 metadata fields matched perfectly' or 'Title block check identified a mismatch: QTY differs between drawings').\n"
            "     * Set `engineering_discrepancy_details` to specific details about any mismatch found (e.g. 'QTY is 1 in original but 2 in KMTI') or 'All 11 title block fields matched successfully' if none.\n"
            "       - `category`: 'title_block'.\n\n"
            "5. ISOMETRIC VIEW:\n"
            "   - Keep in mind that the Isometric View does not have a standard templated position and its placement varies based on available sheet space. Typically, it is positioned below the BOM on the upper-right side.\n"
            "   - Detect orientation, scale, perspective structure, and placement quadrant (e.g., grid 'B-1').\n"
            "   - Report if it was ADDED or REMOVED, and detail how it changes sheet real-estate usage.\n"
            "   - The output should provide professional and comprehensive descriptions matching exact CAD alignments.\n\n"
            "6. OTHER ENGINEERING REFERENCES:\n"
            "   - Compare sheet borders grid patterns, margin tick configurations, Tree views, and drawing coordinates.\n\n"
            "Enforce status values strictly from: MATCHED, CHANGED, ADDED, REMOVED, MISSING.\n\n"
            "VISUAL CANVAS CHECKLIST MARKINGS (canvas_markings):\n"
            "You must perform a complete audit of all elements. To ensure every checked element gets an overlay check/pin on the active drawing canvas, you MUST populate the 'canvas_markings' list. For EVERY key notes text line and main dimension/symbol checked in the revised KMTI drawing:\n"
            "  - 'text_content': The exact, raw text string from the provided input data. You MUST NOT strip or remove the `[ID: <handle>]` tag! Include the entire string exactly as it appears (e.g. '[ID: 3FB] Ø12 hole'). This is absolutely critical for the backend to mathematically resolve exact CAD coordinates.\n"
            "  - 'status': Enforce one of: MATCHED, CHANGED, ADDED, REMOVED.\n"
            "  - 'original_value': If status is CHANGED or REMOVED, you MUST provide the exact raw text string from the ORIGINAL Reference Drawing (including its [ID: ...] tag if present). If status is MATCHED or ADDED, leave this blank or null.\n"
            "  - 'details': A brief 1-line description of the audit result containing the comparison text (e.g., 'Dimension Ø10 hole in original changed to Ø12 hole in KMTI' or 'Dimension 38 remains unchanged').\n"
            "  - 'category': The exact checklist segment this text belongs to. Enforce one of: 'drawing_views', 'notes_section', 'isometric_view'.\n"
            "CRITICAL EXCLUSIONS AND RULES:\n"
            "  1. DO NOT generate 'canvas_markings' for Bill of Materials ('bill_of_materials') or Title Block ('title_block') elements. The backend Python engine programmatically generates exact mathematical markers for these. You must completely skip them in the 'canvas_markings' list to prevent duplicate overlap bugs and header snapping.\n"
            "  2. ISOMETRIC VIEW TAGGING: When adding a marking for the 'isometric_view', you MUST use a specific identifiable text string that exists in the drawing (e.g. the actual isometric geometric block label like 'ISOMETRIC VIEW' or 'SCALE 1:1'), rather than using vague floating symbols like '1' or '①' which can snap to the wrong CAD features.\n"
            "  3. STRIP MARKERS FROM OUTER BORDER / TEMPLATE: Do NOT generate 'canvas_markings' for grid markers (e.g., A, B, C, 1, 2, 3) or template lines located along the extreme outer edges/margins of the drawing frame.\n"
            "  4. STRIP MARKERS FROM COLUMN HEADERS: Do NOT generate 'canvas_markings' for table headers or category labels (e.g., 'No.', 'Title', 'Q\\'ty', 'Remark', 'Unit No.', 'Part No.', 'Code'). These are structural templates, not inspected design values.\n"
            "  5. Do NOT output markers for items that are MATCHED! Only output canvas_markings for elements that have a status of CHANGED, ADDED, or REMOVED. The system will automatically assume anything you don't report is MATCHED. This saves output tokens."
        )

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

        # Construct multimodal contents sequence
        contents = []
        if ref_image_part and rev_image_part:
            contents.extend([
                "Reference Drawing Image (Original Baseline version):",
                ref_image_part,
                "Revised Drawing Image (Updated KMTI version):",
                rev_image_part,
                "Please compare the two drawings visually and semantically based on the rules."
            ])
        contents.append(prompt)

        cache_dir = get_storage_root() / "cache"
        cache_file = cache_dir / f"gemini_comparison_{request.reference_drawing_id}_{request.drawing_id}.json"
        
        response_text = None
        if cache_file.exists():
            try:
                async with aiofiles.open(cache_file, "r", encoding="utf-8") as cf:
                    response_text = await cf.read()
                logger.info(f"Loaded Gemini response from cache: {cache_file}")
            except Exception as cache_err:
                logger.warning(f"Failed to read from cache file: {str(cache_err)}")

        if not response_text:
            # Construct multimodal contents sequence
            contents = []
            if ref_image_part and rev_image_part:
                contents.extend([
                    "Reference Drawing Image (Original Baseline version):",
                    ref_image_part,
                    "Revised Drawing Image (Updated KMTI version):",
                    rev_image_part,
                    "Please compare the two drawings visually and semantically based on the rules."
                ])
            contents.append(prompt)

            # Cascade model list: try each in order, with exponential backoff on 503/UNAVAILABLE
            _model_cascade = ["gemini-2.5-pro", "gemini-2.5-flash", "gemini-1.5-pro"]
            _last_err: Exception | None = None
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
                    break  # Success — exit retry loop
                except Exception as _model_err:
                    _last_err = _model_err
                    _err_str = str(_model_err)
                    _is_overload = "503" in _err_str or "UNAVAILABLE" in _err_str or "overloaded" in _err_str.lower() or "high demand" in _err_str.lower()
                    if _is_overload and _attempt < len(_model_cascade) - 1:
                        _backoff = 2 ** (_attempt + 1)  # 2s, 4s, 8s
                        logger.warning(f"{_model} is unavailable (503/overload). Waiting {_backoff}s before trying next model...")
                        time.sleep(_backoff)
                        continue
                    # Non-retriable error or last model exhausted — propagate
                    raise _model_err
            if response is None:
                raise _last_err or RuntimeError("All Gemini models failed without a response.")
            response_text = response.text
            try:
                async with aiofiles.open(cache_file, "w", encoding="utf-8") as cf:
                    await cf.write(response_text)
                logger.info(f"Saved Gemini response to cache: {cache_file}")
            except Exception as cache_err:
                logger.warning(f"Failed to save to cache file: {str(cache_err)}")

        import json
        parsed = json.loads(response_text)
        logger.info("Successfully parsed structured Gemini 2.5 Pro comparison results.")

        # Override title_block and bill_of_materials comparative contents with Python-pre-built tables
        # (Gemini's free-form table output is unreliable — we guarantee real values here)
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
        
        # Insensitive checkers
        def is_title_block_category(cat: str) -> bool:
            c = str(cat or "").strip().lower().replace(" ", "_")
            return c in ["title_block", "titleblock"]
            
        def is_bom_category(cat: str) -> bool:
            c = str(cat or "").strip().lower().replace(" ", "_")
            return c in ["bill_of_materials", "billofmaterials", "bom"]
            
        def is_admin_bom_marking(m: dict) -> bool:
            txt = str(m.get("text_content", "")).strip().lower()
            details = str(m.get("details", "")).strip().lower()
            
            # Aggressively remove any Stock Q'ty or '0' markings across ALL categories (Fixes Issue 3)
            if any(x in txt or x in details for x in ["stock", "在庫", "棚", "0.0", "0.00"]):
                return True
            if txt == "0":
                return True
                
            cat = m.get("category", "")
            if not is_bom_category(cat):
                return False
            # Catch other admin cells and cell label headers
            admin_terms = [
                "2a", "114", "1", "unit no.", "part no.", "t. q'ty", "t. q’ty", "総製作個数", "コードno.", "ユニットno.",
                "no.", "図面番号", "dwg no.", "dwg.no.", "名称", "title", "個数", "備考", "remark",
                "材質", "code", "材料寸法", "型式", "dimension", "材料個数", "素材重量", "material wt", "仕上重量", "finished wt"
            ]
            return any(term in txt for term in admin_terms)

        # Clean title block and ALL Gemini-generated BOM markings to prevent duplicate and false-positive checks/pins
        clean_markings = [
            m for m in existing_markings 
            if not is_title_block_category(m.get("category")) 
            and not is_bom_category(m.get("category")) 
            and not is_admin_bom_marking(m)
            and str(m.get("text_content", "")).strip() not in global_blocked_values
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

        # Build allowed ID sets: Only IDs in drawing views and notes sections are allowed to have canvas_markings!
        allowed_rev_ids = set()
        for line in (rev_geom + "\n" + rev_notes).split('\n'):
            m_id = re.match(r'^\[ID:\s*([^,\]]+)[^\]]*\]', line.strip())
            if m_id: allowed_rev_ids.add(m_id.group(1).strip())
            
        allowed_ref_ids = set()
        for line in (ref_geom + "\n" + ref_notes).split('\n'):
            m_id = re.match(r'^\[ID:\s*([^,\]]+)[^\]]*\]', line.strip())
            if m_id: allowed_ref_ids.add(m_id.group(1).strip())

        # PHASE 2: Anti-Hallucination Guardrails
        rev_all_text_lower = rev_all_text.lower().replace(" ", "").replace("\n", "")
        ref_all_text_lower = ref_all_text.lower().replace(" ", "").replace("\n", "")
        
        guardrailed_markings = []
        for m in clean_markings:
            txt = str(m.get("text_content", "")).strip()
            if not txt:
                continue
            txt_clean = txt.lower().replace(" ", "").replace("\n", "")
            status = m.get("status")
            
            # Guardrail 1: Exact Spatial Allowed-List (Destroys ghost pins in Title Block / BOM margins)
            eid = m.get("entity_id")
            if eid:
                if eid.startswith("REV-") and eid not in allowed_rev_ids:
                    logger.warning(f"Guardrail intercepted marker {eid} because it is outside allowed drawing views (likely BOM/Title block hallucination).")
                    continue
                if eid.startswith("REF-") and eid not in allowed_ref_ids:
                    logger.warning(f"Guardrail intercepted marker {eid} because it is outside allowed drawing views (likely BOM/Title block hallucination).")
                    continue
            
            # Guardrail 2: Check if the exact claimed text actually exists in the CAD data
            if status in ["ADDED", "CHANGED"]:
                if txt_clean not in rev_all_text_lower:
                    logger.warning(f"Guardrail intercepted hallucinated {status} marker for '{txt}' (not found in rev drawing)")
                    continue
            elif status == "REMOVED":
                if txt_clean not in ref_all_text_lower:
                    logger.warning(f"Guardrail intercepted hallucinated REMOVED marker for '{txt}' (not found in ref drawing)")
                    continue

            guardrailed_markings.append(m)
        clean_markings = guardrailed_markings

        # PHASE 3: Python-Side MATCHED Map-Reduce
        # To save 50,000+ output tokens on large drawings, Gemini only outputs differences.
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
                    if not is_admin_bom_marking({"text_content": text_content, "category": "drawing_views"}) and str(text_content).strip() not in global_blocked_values:
                        clean_markings.append({
                            "entity_id": entity_id,
                            "text_content": text_content,
                            "status": "MATCHED",
                            "details": "Element verified and matches reference.",
                            "category": "drawing_views"
                        })
        
        
        field_labels_map = {
            "QTY": "総製作個数 T. Q'ty (Total Quantity)",
            "CROSS REF NO": "共通番号 Cross ref No.",
            "PREVIOUS DWG NO": "旧図面番号 Previous Dwg. No.",
            "DESIGNED": "設計 DESIGNED",
            "DRAWN": "作成 DRAWN",
            "SCALE": "尺度 SCALE",
            "NAME": "名称 TITLE",
            "JOB NO": "工事番号 Job No.",
            "STD NO": "標準図番号 Std. No.",
            "MACHINE CODE": "機器記号 Mach. code / ユニット記号 Unit Code",
            "DWG NO": "図面番号 DWG. No. / 機種 Machine Type / ユニット Unit No. / 部品 Part No. / 特性 派生 Branch"
        }
        
        def norm_scale(v):
            return re.sub(r':', '/', v.strip()) if v and v != 'NONE' else v
            
        def sanitize_title_value(val):
            # Strips label prefixes before comparison and assignment.
            # IMPORTANT: The separator group [:：\-\s]+ is REQUIRED after the keyword so that
            # bare code strings which happen to contain a label word (e.g. a machine code of the
            # form 'mach-XYZ') are NOT partially stripped. Without the mandatory separator,
            # 'machXYZ' would be trimmed to 'XYZ' by the regex.
            if val == "NONE" or not val:
                return val
            val = re.sub(
                r'^(作\s*成|設\s*計|drawn|designed|検\s*図|承\s*認|checked|approved'
                r'|機\s*器\s*記\s*号|機\s*番\s*記\s*号|ユ\s*ニ\s*ッ\s*ト\s*記\s*号'
                r'|mach\.?\s*code|unit\s*code'
                r'|工\s*事\s*番\s*号|job\s*no\.?'
                r'|図\s*面\s*番\s*号|dwg\s*no\.?|dwg\.no'
                r'|尺\s*度|scale)'
                r'[\s\t]*[:：\-\–]+[\s\t]*',  # mandatory separator — colon/dash required
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

            # Fix B1 — Bilateral symmetric guard for MACHINE CODE / UNIT CODE.
            # extract_proximity_value can anchor on the wrong label entity and return NONE for one
            # drawing while the other resolves correctly. If one side is NONE but the other has a
            # real value, search the "NONE" side's entities directly. If the value is present there,
            # the extraction missed it — demote to MATCHED and fill in the missing coordinate.
            if field_key == "MACHINE CODE" and status_val in ("ADDED", "REMOVED"):
                if orig_val == "NONE" and kmti_val != "NONE":
                    recovered = find_drawing_text_coordinates(ref_entities, kmti_val, category="title_block")
                    if recovered:
                        status_val = "MATCHED"
                        orig_coords = recovered
                elif kmti_val == "NONE" and orig_val != "NONE":
                    recovered = find_drawing_text_coordinates(rev_entities, orig_val, category="title_block")
                    if recovered:
                        status_val = "MATCHED"
                        kmti_coords = recovered
            
            # Exact value coordinate lookup — scoped to title_block spatial region first
            if kmti_coords is None and kmti_val and kmti_val != "NONE":
                exact_coords = find_drawing_text_coordinates(rev_entities, kmti_val, category="title_block")
                if exact_coords:
                    kmti_coords = exact_coords
            if orig_coords is None and orig_val and orig_val != "NONE":
                exact_coords = find_drawing_text_coordinates(ref_entities, orig_val, category="title_block")
                if exact_coords:
                    orig_coords = exact_coords

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

        # (Administrative BOM block markings removed: QTY is now handled in Title Block)

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

        def get_row_key(row):
            no_val = get_val_outer(row, "NO")
            if no_val == "NONE":
                return ""
            return no_val.strip()

        def key_sort_fn(key_str):
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
        def is_blank_spacer(row):
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

        filtered_ref = [r for r in ref_bom_rows if not is_blank_spacer(r)]
        filtered_rev = [r for r in rev_bom_rows if not is_blank_spacer(r)]

        ref_bom_map = {}
        for idx, r in enumerate(filtered_ref):
            k = get_row_key(r)
            if not k:
                k = f"_ref_idx_{idx}"
            ref_bom_map[k] = r

        rev_bom_map = {}
        for idx, r in enumerate(filtered_rev):
            k = get_row_key(r)
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
        bom_keys.sort(key=key_sort_fn)

        for key in bom_keys:
            rev_row = rev_bom_map.get(key, {})
            ref_row = ref_bom_map.get(key, {})

            row_label = f"Unnumbered Row" if (key.startswith("_ref_idx_") or key.startswith("_rev_idx_")) else f"Item {key}"

            if is_assembly_drawing:
                bom_cols = [
                    ("NO", "No."),
                    ("DWG_NO", "図面番号 / DWG No."),
                    ("TITLE", "名称 / TITLE"),
                    ("QTY", "Q'ty"),
                    ("REMARK", "備考 / Remark")
                ]
            else:
                bom_cols = [
                    ("NO", "No."),
                    ("CODE", "材質 / Code"),
                    ("DIMENSION", "材料寸法/型式 / Dimension"),
                    ("QTY", "材料個数 / Q'ty"),
                    ("MATERIAL_WEIGHT", "素材重量Kg / Material Wt(kg)"),
                    ("FINISHED_WEIGHT", "仕上重量Kg / Finished Wt(kg)"),
                    ("REMARK", "備考 / Remark")
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

                # Safeguard 2: Fallback Global Text String Check (protect identical texts from showing as different)
                if status_val == "ADDED" and kmti_val.strip().lower() in ref_bom_texts:
                    status_val = "MATCHED"
                elif status_val == "REMOVED" and orig_val.strip().lower() in rev_bom_texts:
                    status_val = "MATCHED"
                elif status_val == "CHANGED":
                    if kmti_val.strip().lower() in ref_bom_texts and orig_val.strip().lower() in rev_bom_texts:
                        status_val = "MATCHED"

                # Fix B3 — Exact value coordinate lookup, spatially constrained to BOM bbox.
                # The len > 2 guard is removed so short values (e.g. No.=1, Q'ty=2) are also
                # resolved via the BOM spatial scope and cannot snap to the Title Block region.
                if kmti_coords is None and kmti_val and kmti_val != "NONE":
                    exact_coords = find_drawing_text_coordinates(rev_entities, kmti_val, category="bill_of_materials", region_bbox=rev_bom_bbox, used_entities=used_rev_entities)
                    if exact_coords:
                        # Hard spatial rejection: discard if resolved coordinate falls outside BOM bbox.
                        if rev_bom_bbox and not (rev_bom_bbox[0] <= exact_coords[0] <= rev_bom_bbox[2] and rev_bom_bbox[1] <= exact_coords[1] <= rev_bom_bbox[3]):
                            exact_coords = None
                    if exact_coords:
                        kmti_coords = exact_coords
                if orig_coords is None and orig_val and orig_val != "NONE":
                    exact_coords = find_drawing_text_coordinates(ref_entities, orig_val, category="bill_of_materials", region_bbox=ref_bom_bbox, used_entities=used_ref_entities)
                    if exact_coords:
                        # Hard spatial rejection: discard if resolved coordinate falls outside BOM bbox.
                        if ref_bom_bbox and not (ref_bom_bbox[0] <= exact_coords[0] <= ref_bom_bbox[2] and ref_bom_bbox[1] <= exact_coords[1] <= ref_bom_bbox[3]):
                            exact_coords = None
                    if exact_coords:
                        orig_coords = exact_coords

                if kmti_val != "NONE" or orig_val != "NONE":
                    marking_entry = {
                        "text_content": kmti_val if kmti_val != "NONE" else orig_val,
                        "status": status_val,
                        "details": f"BOM [{row_label}] {display_label} checked: {orig_val} vs {kmti_val}",
                        "category": "bill_of_materials",
                        "original_value": orig_val if status_val == "CHANGED" else None
                    }
                    if kmti_coords is not None:
                        marking_entry["coordinates"] = kmti_coords
                    if orig_coords is not None:
                        marking_entry["ref_coordinates"] = orig_coords
                        
                    # Spatial boundary filter (Fixes Issue 6: Stray BOM marker over Title Block area)
                    if kmti_coords is not None and kmti_coords[1] < 60.0:
                        continue
                        
                    clean_markings.append(marking_entry)
        
        def calc_anchor(e) -> list:
            ins = e.geometry.get("insert") or [0, 0, 0]
            height = e.properties.get("height", 3.0)
            bbox = e.properties.get("bbox", None)
            if bbox and len(bbox) == 2:
                try:
                    return [bbox[1][0] + (height * 0.8), bbox[0][1] + (bbox[1][1] - bbox[0][1]) / 2.0]
                except Exception:
                    pass
            text_len = len(e.properties.get("text", ""))
            return [ins[0] + text_len * height * 0.6 + (height * 0.8), ins[1] + (height / 2.0)]

        # 4. Resolve exact geometric coordinates
        for m in clean_markings:
            # Map EXACT coordinates from entity_id! (Fixes fuzzy search inaccuracies like orange pins on Japanese notes)
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
                        
            # Fallback to fuzzy text search if coordinates are still missing (should be extremely rare now)
            if m.get("coordinates") is None or m.get("ref_coordinates") is None:
                txt = m.get("text_content", "")
                orig_txt = m.get("original_value") or txt
                cat = m.get("category")
                status_val = m.get("status")
                
                if status_val == "ADDED":
                    if m.get("coordinates") is None and txt and txt != "NONE":
                        m["coordinates"] = find_drawing_text_coordinates(rev_entities, txt, category=cat, used_entities=used_rev_entities)
                
                elif status_val == "REMOVED":
                    search_txt = m.get("original_value") or txt
                    if m.get("ref_coordinates") is None and search_txt and search_txt != "NONE":
                        m["ref_coordinates"] = find_drawing_text_coordinates(ref_entities, search_txt, category=cat, used_entities=used_ref_entities)
                        
                elif status_val == "CHANGED":
                    if m.get("coordinates") is None and txt and txt != "NONE":
                        m["coordinates"] = find_drawing_text_coordinates(rev_entities, txt, category=cat, used_entities=used_rev_entities)
                    search_txt = m.get("original_value") or txt
                    if m.get("ref_coordinates") is None and search_txt and search_txt != "NONE":
                        m["ref_coordinates"] = find_drawing_text_coordinates(ref_entities, search_txt, category=cat, used_entities=used_ref_entities)
                        
                else: # MATCHED
                    if m.get("coordinates") is None and txt and txt != "NONE":
                        m["coordinates"] = find_drawing_text_coordinates(rev_entities, txt, category=cat, used_entities=used_rev_entities)
                    if m.get("ref_coordinates") is None and txt and txt != "NONE":
                        m["ref_coordinates"] = find_drawing_text_coordinates(ref_entities, txt, category=cat, used_entities=used_ref_entities)
        
        parsed["canvas_markings"] = clean_markings

        return StandardResponse(
            success=True,
            data=PhysicalComparisonResponse(
                drawing_views=CategoryComparison(**parsed["drawing_views"]),
                notes_section=CategoryComparison(**parsed["notes_section"]),
                bill_of_materials=CategoryComparison(**parsed["bill_of_materials"]),
                title_block=CategoryComparison(**parsed["title_block"]),
                isometric_view=CategoryComparison(**parsed["isometric_view"]),
                other_engineering_references=CategoryComparison(**parsed["other_engineering_references"]),
                canvas_markings=[CanvasMarking(**item) for item in parsed.get("canvas_markings", [])]
            )
        )
    except Exception as e:
        logger.error(f"Structured Gemini 2.5 Pro comparison failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Gemini API structured physical comparison failed: {str(e)}. Please verify your network connection, API key validity, or billing quota status."
        )


@router.get(
    "/audits/sessions/{id}",
    response_model=StandardResponse[AuditSessionResponse],
    summary="Retrieve status details of an AuditSession",
    dependencies=[Depends(get_auth_token)]
)
async def get_audit_session(id: str):
    """
    Retrieves the execution status of the background compliance audit.
    """
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
            error_message=session.error_message,
            timings=session.timings,
            diagnostics=session.diagnostics,
            created_at=session.created_at,
            started_at=session.started_at,
            completed_at=session.completed_at,
            remarks=session.remarks,
            username=session.username,
            is_deleted=session.is_deleted,
            deleted_at=session.deleted_at,
            deleted_by=session.deleted_by,
            is_restored=session.is_restored
        )
    )

@router.get(
    "/audits/sessions/{id}/violations",
    response_model=StandardResponse[List[AuditViolationResponse]],
    summary="Retrieve list of engineering standard violations detected",
    dependencies=[Depends(get_auth_token)]
)
async def get_audit_violations(id: str):
    """
    Retrieves the full list of rule-based and AI-grounded engineering infractions
    compiled for the specified audit session.
    """
    session = await AuditSession.get(id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Audit session not found: {id}"
        )

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

@router.post(
    "/audits/sessions/{id}/report",
    summary="Compile and download compliance audit reports",
    dependencies=[Depends(get_auth_token)]
)
async def generate_session_report(id: str, format: str = "pdf"):
    """
    Compiles PDF or Excel compliance reports for the specified auditing session
    and yields the downloadable binary stream.
    """
    session = await AuditSession.get(id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Audit session not found: {id}"
        )
        
    try:
        generator = ReportGenerator()
        paths = await generator.generate_reports(id)
        
        target_format = format.lower()
        if target_format not in paths:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported export format: {format}. Must be 'pdf' or 'xlsx'."
            )
            
        file_path = paths[target_format]
        validate_sandboxed_path(file_path)
        
        media_type = "application/pdf" if target_format == "pdf" else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        
        return FileResponse(
            path=str(file_path),
            media_type=media_type,
            filename=file_path.name
        )
    except Exception as err:
        logger.error(f"Failed to compile report for session {id}: {str(err)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Export generation failed: {str(err)}"
        )

@router.get(
    "/audits/sessions/{id}/diagnostics",
    response_model=StandardResponse[dict],
    summary="Retrieve detailed execution timings and analytical metrics",
    dependencies=[Depends(get_auth_token)]
)
async def get_audit_diagnostics(id: str):
    """
    Aggregates analytical metrics for the specified completed audit session.
    """
    try:
        diag = await AuditDiagnostics.get_session_diagnostics(id)
        return StandardResponse(success=True, data=diag)
    except FileNotFoundError as fnf:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(fnf)
        )
    except Exception as e:
        logger.error(f"Failed to gather audit diagnostics: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Diagnostics aggregation failed: {str(e)}"
        )

@router.get(
    "/audits/sessions",
    response_model=StandardResponse[List[AuditSessionResponse]],
    summary="List all audit sessions",
    dependencies=[Depends(get_auth_token)]
)
async def list_audit_sessions(is_deleted: bool = False, username: Optional[str] = None):
    """
    Fetches all AuditSession documents from MongoDB matching filters sorted by created_at descending.
    """
    query = AuditSession.find(AuditSession.is_deleted == is_deleted)
    if username:
        query = query.find(AuditSession.username == username)
        
    sessions = await query.sort("-created_at").to_list()
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
            error_message=s.error_message,
            timings=s.timings,
            diagnostics=s.diagnostics,
            created_at=s.created_at,
            started_at=s.started_at,
            completed_at=s.completed_at,
            remarks=s.remarks,
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
        from ..core.auth import verify_jwt_token
        payload = verify_jwt_token(token)
        username = payload.get("username")
    except Exception:
        pass
    
    from datetime import datetime
    session.is_deleted = True
    session.deleted_at = datetime.utcnow()
    session.deleted_by = username
    await session.save()
    
    return StandardResponse(
        success=True,
        data={"message": f"Audit session {id} successfully moved to trashbin."}
    )

@router.post(
    "/audits/sessions/{id}/restore",
    response_model=StandardResponse[dict],
    summary="Restore a soft-deleted audit session",
    dependencies=[Depends(get_auth_token)]
)
async def restore_audit_session(id: str):
    session = await AuditSession.get(id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Audit session not found: {id}"
        )
    
    session.is_deleted = False
    session.deleted_at = None
    session.deleted_by = None
    session.is_restored = True
    await session.save()
    
    return StandardResponse(
        success=True,
        data={"message": f"Audit session {id} successfully restored."}
    )

@router.patch(
    "/audits/sessions/{id}",
    response_model=StandardResponse[AuditSessionResponse],
    summary="Update remarks for an audit session",
    dependencies=[Depends(get_auth_token)]
)
async def update_audit_session_remarks(id: str, request: UpdateAuditSessionRequest):
    """
    Updates the remarks field for the specified audit session.
    """
    session = await AuditSession.get(id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Audit session not found: {id}"
        )
    
    session.remarks = request.remarks
    await session.save()
    
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
            error_message=session.error_message,
            timings=session.timings,
            diagnostics=session.diagnostics,
            created_at=session.created_at,
            started_at=session.started_at,
            completed_at=session.completed_at,
            remarks=session.remarks,
            username=session.username,
            is_deleted=session.is_deleted,
            deleted_at=session.deleted_at,
            deleted_by=session.deleted_by,
            is_restored=session.is_restored
        )
    )

# ====================================================
# PHASE 11 — AUTH & USER ADMINISTRATION ROUTERS
# ====================================================

from datetime import datetime
from ..core.auth import hash_password, verify_password, create_jwt_token
from ..domain.models.user_account import UserAccountDocument
from ..domain.models.user_session import UserSessionDocument
from .dependencies import get_current_user, require_role
from .schemas import LoginRequest, LoginResponse, UserAccountResponse, CreateUserRequest, UpdateUserRequest
from ..infrastructure.database.connection import db_manager

@router.post(
    "/auth/login",
    response_model=StandardResponse[LoginResponse],
    summary="Login user and issue session token"
)
async def login_user(request: LoginRequest):
    if not db_manager.is_connected:
        return StandardResponse(
            success=False,
            error={
                "code": "DATABASE_OFFLINE",
                "message": "Local MongoDB database is offline. Please start the database service using 'start-mongo.ps1' or contact the administrator."
            }
        )

    user = await UserAccountDocument.find_one(UserAccountDocument.username == request.username)
    if not user or not user.active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password."
        )
        
    if not verify_password(request.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password."
        )
        
    # Generate token
    token, expires_at = create_jwt_token({
        "username": user.username,
        "role": user.role
    })
    
    # Save session
    session = UserSessionDocument(
        token=token,
        user_id=str(user.id),
        username=user.username,
        role=user.role,
        expires_at=expires_at
    )
    await session.save()
    
    # Update last login
    user.last_login = datetime.utcnow()
    await user.save()
    
    return StandardResponse(
        success=True,
        data=LoginResponse(
            session_token=token,
            username=user.username,
            role=user.role
        )
    )

@router.get(
    "/auth/me",
    response_model=StandardResponse[UserAccountResponse],
    summary="Get profile of currently logged-in user"
)
async def get_my_profile(current_user: UserAccountDocument = Depends(get_current_user)):
    return StandardResponse(
        success=True,
        data=UserAccountResponse(
            id=str(current_user.id),
            username=current_user.username,
            role=current_user.role,
            active=current_user.active,
            created_at=current_user.created_at,
            permissions=current_user.permissions
        )
    )

@router.get(
    "/admin/users",
    response_model=StandardResponse[List[UserAccountResponse]],
    summary="List all registered enterprise accounts",
    dependencies=[Depends(require_role("admin"))]
)
async def list_enterprise_users():
    users = await UserAccountDocument.find_all().to_list()
    res = [
        UserAccountResponse(
            id=str(u.id),
            username=u.username,
            role=u.role,
            active=u.active,
            created_at=u.created_at,
            permissions=u.permissions
        )
        for u in users
    ]
    return StandardResponse(success=True, data=res)

@router.post(
    "/admin/users",
    response_model=StandardResponse[UserAccountResponse],
    summary="Create a new enterprise account",
    dependencies=[Depends(require_role("admin"))]
)
async def create_enterprise_user(request: CreateUserRequest):
    existing = await UserAccountDocument.find_one(UserAccountDocument.username == request.username)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered."
        )
        
    user = UserAccountDocument(
        username=request.username,
        hashed_password=hash_password(request.password),
        role=request.role,
        permissions=["audit"] if request.role == "user" else ["all"]
    )
    await user.save()
    
    return StandardResponse(
        success=True,
        data=UserAccountResponse(
            id=str(user.id),
            username=user.username,
            role=user.role,
            active=user.active,
            created_at=user.created_at,
            permissions=user.permissions
        )
    )

@router.delete(
    "/admin/users/{username}",
    response_model=StandardResponse[dict],
    summary="Deactivate or delete an enterprise account",
    dependencies=[Depends(require_role("admin"))]
)
async def delete_enterprise_user(username: str):
    if username == "admin":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete the default administrator account."
        )
        
    user = await UserAccountDocument.find_one(UserAccountDocument.username == username)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User account not found."
        )
        
    await user.delete()
    return StandardResponse(success=True, data={"message": f"Successfully deleted user: {username}"})


@router.patch(
    "/admin/users/{username}",
    response_model=StandardResponse[UserAccountResponse],
    summary="Update an enterprise account's parameters or reset password",
    dependencies=[Depends(require_role("admin"))]
)
async def update_enterprise_user(username: str, request: UpdateUserRequest):
    user = await UserAccountDocument.find_one(UserAccountDocument.username == username)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User account not found."
        )
        
    if username == "admin":
        if request.active is not None and request.active is False:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot deactivate the default administrator account."
            )
        if request.role is not None and request.role != "admin":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot demote the default administrator account."
            )

    if request.active is not None:
        user.active = request.active
        
    if request.role is not None:
        user.role = request.role
        user.permissions = ["all"] if request.role == "admin" else ["audit"]
        
    if request.password is not None:
        user.hashed_password = hash_password(request.password)
        
    await user.save()
    
    return StandardResponse(
        success=True,
        data=UserAccountResponse(
            id=str(user.id),
            username=user.username,
            role=user.role,
            active=user.active,
            created_at=user.created_at,
            permissions=user.permissions
        )
    )

