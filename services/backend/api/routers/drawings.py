import os
import hashlib
import uuid
import aiofiles
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel
from ...domain.models.drawing_document import DrawingDocument
from ...domain.models.extracted_entity import ExtractedEntity
from ...domain.models.extraction_job import ExtractionJob
from ...infrastructure.cad.processing_queue import processing_queue
from ...infrastructure.cad.diagnostics import CADDiagnostics
from ...infrastructure.rendering.geometry_serializer import GeometrySerializer
from ...infrastructure.storage.path_resolver import get_storage_root
from ...logger import logger, correlation_id_var
from ...config import settings
from ..dependencies import get_auth_token, get_or_404
from ..schemas import StandardResponse, UploadResponse, DrawingResponse, JobResponse

router = APIRouter()


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
    
    if file_ext not in ("dwg", "dxf", "pdf", "step", "stp", "iges", "igs", "icd", "sldprt", "sldasm"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported file format. Only proprietary .dwg, open .dxf drawings, .pdf files, 3D .step/.iges models, or iCAD .icd / SolidWorks sldprt/sldasm models are accepted."
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
        corr_id = correlation_id_var.get()
        logger.exception(f"[{corr_id}] Drawing upload failed while streaming to disk: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Drawing upload failed. Reference: {corr_id}"
        )

    file_hash = sha256.hexdigest()
    
    # Check for duplicate Drawing hash in database
    existing_drawing = await DrawingDocument.find_one(DrawingDocument.file_hash == file_hash)
    if existing_drawing:
        # If the drawing is already fully extracted and completed, don't nuke the caches or re-extract
        if existing_drawing.status == "completed":
            logger.info(f"Duplicate upload detected for completed drawing {existing_drawing.id}. Skipping re-extraction to preserve cache.")
            
            # Find the most recent job for this drawing to return in the response
            existing_job = await ExtractionJob.find_one(ExtractionJob.drawing_id == str(existing_drawing.id), sort=[("created_at", -1)])
            
            # If temp file exists, clean it up since we don't need it
            if temp_upload_path.exists():
                try:
                    temp_upload_path.unlink()
                except Exception:
                    pass
                    
            # Return early without deleting caches or re-queuing
            job_response = None
            if existing_job:
                job_response = JobResponse(
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
                )
            else:
                # Fallback if somehow there's no job
                job_response = JobResponse(
                    id=f"dummy-{existing_drawing.id}",
                    drawing_id=str(existing_drawing.id),
                    status="completed",
                    diagnostics={},
                    created_at=existing_drawing.created_at
                )
                
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
                    job=job_response,
                    is_duplicate=True
                )
            )

        # If it failed or got stuck, we DO want to overwrite it and clear caches
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
        
        # Clear stale comparison cache files from disk
        try:
            cache_dir = get_storage_root() / "cache"
            if cache_dir.exists():
                for f in cache_dir.glob("gemini_comparison_*.json"):
                    if str(existing_drawing.id) in f.name:
                        f.unlink()
        except Exception as cache_del_err:
            logger.warning(f"Could not clear comparison cache files on re-upload: {cache_del_err}")
            
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
        corr_id = correlation_id_var.get()
        logger.exception(f"[{corr_id}] Failed to move uploaded drawing to secure storage: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to securely store uploaded drawing. Reference: {corr_id}"
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
    response_model=StandardResponse[list[DrawingResponse]],
    summary="List all registered drawing documents",
    dependencies=[Depends(get_auth_token)]
)
async def list_drawings():
    """
    Fetches all registered drawings from the local MongoDB registry, sorted by newest first.
    Filters out and purges orphaned drawing records whose backing files no longer exist on disk.
    """
    docs = await DrawingDocument.find_all(sort=[("created_at", -1)]).to_list()
    storage_root = get_storage_root()
    valid_docs = []
    
    for d in docs:
        if d.file_path:
            full_path = storage_root / d.file_path
            if not full_path.exists():
                # Backing file on disk is gone - purge orphaned DB record
                logger.info(f"Pruning orphaned DrawingDocument {d.id} ({d.file_name}) - file not found at {full_path}")
                try:
                    await ExtractedEntity.find(ExtractedEntity.drawing_id == str(d.id)).delete()
                    await ExtractionJob.find(ExtractionJob.drawing_id == str(d.id)).delete()
                    await d.delete()
                except Exception as e:
                    logger.warning(f"Failed to auto-prune orphaned drawing {d.id}: {e}")
                continue
        valid_docs.append(d)

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
        for d in valid_docs
    ]
    return StandardResponse(success=True, data=res)


@router.delete(
    "/drawings/{id}",
    response_model=StandardResponse[dict],
    summary="Delete a DrawingDocument and its associated extracted entities and storage artifacts",
    dependencies=[Depends(get_auth_token)]
)
async def delete_drawing(id: str):
    """
    Purges a drawing document record, its parsed entities, jobs, and associated disk files.
    """
    drawing = await get_or_404(DrawingDocument, id, f"Drawing document not found for ID: {id}")
    
    # 1. Delete associated extracted entities & jobs
    await ExtractedEntity.find(ExtractedEntity.drawing_id == id).delete()
    await ExtractionJob.find(ExtractionJob.drawing_id == id).delete()

    # 2. Clean up disk artifacts if they exist
    storage_root = get_storage_root()
    if drawing.file_path:
        file_path = storage_root / drawing.file_path
        if file_path.exists():
            try:
                file_path.unlink()
            except Exception as e:
                logger.warning(f"Failed to delete drawing file {file_path}: {e}")

    rendering_path = storage_root / "renderings" / f"{id}.png"
    if rendering_path.exists():
        try:
            rendering_path.unlink()
        except Exception as e:
            logger.warning(f"Failed to delete rendering artifact {rendering_path}: {e}")

    gltf_path = storage_root / "temp" / f"model_{id}.gltf"
    if gltf_path.exists():
        try:
            gltf_path.unlink()
        except Exception as e:
            logger.warning(f"Failed to delete gltf artifact {gltf_path}: {e}")

    # 3. Delete the DrawingDocument record from MongoDB
    await drawing.delete()

    logger.info(f"Successfully deleted DrawingDocument {id} and associated artifacts.")
    return StandardResponse(success=True, data={"deleted_id": id})



@router.get(
    "/drawings/{id}",
    response_model=StandardResponse[DrawingResponse],
    summary="Retrieve details of a DrawingDocument",
    dependencies=[Depends(get_auth_token)]
)
async def get_drawing(id: str):
    drawing = await get_or_404(DrawingDocument, id, f"Drawing document not found for ID: {id}")
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
    drawing = await get_or_404(DrawingDocument, id, f"Drawing document not found for ID: {id}")
    entities = await ExtractedEntity.find(ExtractedEntity.drawing_id == id).to_list()
    
    if not entities:
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
    drawing = await get_or_404(DrawingDocument, id, f"Drawing document not found for ID: {id}")
    rendering_path = get_storage_root() / "renderings" / f"{id}.png"
    if not rendering_path.exists():
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    return FileResponse(str(rendering_path), media_type="image/png")


@router.get(
    "/drawings/{id}/gltf",
    summary="Get 3D converted GLTF file of STEP/IGES model",
    dependencies=[Depends(get_auth_token)]
)
async def get_drawing_gltf(id: str):
    drawing = await get_or_404(DrawingDocument, id, f"Drawing document not found for ID: {id}")
    gltf_path = get_storage_root() / "temp" / f"model_{id}.gltf"
    if not gltf_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="GLTF asset not found for this 3D model."
        )
    return FileResponse(
        str(gltf_path),
        media_type="model/gltf+json",
        filename=f"{drawing.file_name}.gltf"
    )


class SimilarityResult(BaseModel):
    drawing_id: str
    file_name: str
    similarity_score: float


@router.get(
    "/drawings/{id}/similarity",
    response_model=StandardResponse[list[SimilarityResult]],
    summary="Find drawings that have geometrically similar structures",
    dependencies=[Depends(get_auth_token)]
)
async def get_drawing_similarity(id: str, limit: int = 5):
    """
    Computes a cosine similarity score over CAD entity count vectors to identify
    geometrically or typologically similar technical drawing layouts.
    """
    target = await get_or_404(DrawingDocument, id, "Drawing not found.")

    all_drawings = await DrawingDocument.find(DrawingDocument.id != target.id).to_list()
    
    def cosine_similarity(v1: dict, v2: dict) -> float:
        keys = set(v1.keys()) | set(v2.keys())
        if not keys:
            return 1.0
        vec1 = [float(v1.get(k, 0)) for k in keys]
        vec2 = [float(v2.get(k, 0)) for k in keys]
        
        dot = sum(a*b for a, b in zip(vec1, vec2))
        norm1 = sum(a*a for a in vec1)**0.5
        norm2 = sum(a*a for a in vec2)**0.5
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return dot / (norm1 * norm2)

    results = []
    t_counts = target.entity_counts or {}
    for d in all_drawings:
        d_counts = d.entity_counts or {}
        score = cosine_similarity(t_counts, d_counts)
        results.append(
            SimilarityResult(
                drawing_id=str(d.id),
                file_name=d.file_name,
                similarity_score=round(score, 4)
            )
        )

    results = sorted(results, key=lambda r: r.similarity_score, reverse=True)
    return StandardResponse(success=True, data=results[:limit])


class SignatureVerificationResult(BaseModel):
    has_signature_field: bool
    message: str


@router.get(
    "/drawings/{id}/signature",
    response_model=StandardResponse[SignatureVerificationResult],
    summary="Checks whether a PDF drawing contains a digital signature field",
    dependencies=[Depends(get_auth_token)]
)
async def verify_drawing_signature(id: str):
    """
    Cheap presence check only: scans the raw PDF bytes for `/Sig` and `/ByteRange`
    markers indicating a signature field exists in the document structure.

    This does NOT perform certificate/trust-chain verification, does NOT confirm
    the signature is cryptographically valid, and does NOT identify a signer.
    `has_signature_field=True` means "this PDF has a signature field", nothing more.
    """
    drawing = await get_or_404(DrawingDocument, id, "Drawing not found.")

    if drawing.format.lower() != "pdf":
        return StandardResponse(
            success=True,
            data=SignatureVerificationResult(
                has_signature_field=False,
                message="Digital signature field detection is only supported for PDF blueprint drawing packages."
            )
        )

    try:
        file_path = get_storage_root() / drawing.file_path
        if file_path.exists():
            content = file_path.read_bytes()
            if b"/Sig" in content and b"/ByteRange" in content:
                return StandardResponse(
                    success=True,
                    data=SignatureVerificationResult(
                        has_signature_field=True,
                        message="This PDF contains a digital signature field. This is a structural presence check only — it does not verify the certificate, trust chain, or signer identity."
                    )
                )
    except Exception as e:
        logger.warning(f"Signature field check failed: {e}")

    return StandardResponse(
        success=True,
        data=SignatureVerificationResult(
            has_signature_field=False,
            message="No digital signature field found in this PDF document."
        )
    )


@router.get(
    "/jobs/{id}",
    response_model=StandardResponse[JobResponse],
    summary="Retrieve status of an ExtractionJob",
    dependencies=[Depends(get_auth_token)]
)
async def get_job(id: str):
    job = await get_or_404(ExtractionJob, id, f"Extraction job not found for ID: {id}")
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
