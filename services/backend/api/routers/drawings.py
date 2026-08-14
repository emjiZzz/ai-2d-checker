import os
import hashlib
import uuid
import aiofiles
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from fastapi.responses import FileResponse
from pydantic import BaseModel
from ...domain.models.drawing_document import DrawingDocument
from ...domain.models.extracted_entity import ExtractedEntity
from ...domain.models.extraction_job import ExtractionJob
from ...infrastructure.cad.processing_queue import processing_queue
from ...infrastructure.cad.diagnostics import CADDiagnostics
from ...infrastructure.rendering.geometry_serializer import GeometrySerializer
from ...core.security import sandboxed_path
from ...logger import logger, correlation_id_var
from ...config import settings
from ..dependencies import get_auth_token, get_or_404
from ..schemas import (
    StandardResponse,
    UploadResponse,
    DrawingResponse,
    JobResponse,
    DrawingZonesResponse,
    ZoneBBox,
)

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
    computes SHA-256 hash, and queues it for background ODA/DXF extraction via DrawingIngestionService.
    """
    from ...domain.services.drawing_ingestion_service import DrawingIngestionService

    try:
        drawing, job, is_duplicate = await DrawingIngestionService.process_ingestion(file)
    except HTTPException:
        raise
    except Exception as e:
        corr_id = correlation_id_var.get()
        logger.error(f"[{corr_id}] Drawing ingestion failed unexpectedly: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Drawing upload failed. Reference: {corr_id}"
        )

    job_response = JobResponse(
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
                drawing_numbers=drawing.drawing_numbers,
                created_at=drawing.created_at,
                updated_at=drawing.updated_at
            ),
            job=job_response,
            is_duplicate=is_duplicate
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
    valid_docs = []
    
    for d in docs:
        if d.file_path:
            # Guarded like the serving paths, but it must not raise: this loop decides whether to
            # *delete* records, and one malformed row should not fail the whole listing. A path
            # that cannot be validated is kept rather than pruned — declining to delete on a
            # check we could not complete is the conservative direction.
            try:
                full_path = sandboxed_path(d.file_path)
            except HTTPException:
                logger.warning(
                    f"DrawingDocument {d.id} ({d.file_name}) has a file_path outside the "
                    f"storage root: {d.file_path!r}. Keeping the record; not pruning on an "
                    f"unverifiable path."
                )
                valid_docs.append(d)
                continue
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
            drawing_numbers=d.drawing_numbers,
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
    # 404 first so a bad id is a clean not-found rather than a silent no-op purge.
    await get_or_404(DrawingDocument, id, f"Drawing document not found for ID: {id}")

    # Single source of truth for drawing deletion: entities, jobs, upload file,
    # rendering, gltf, comparison/OCR caches, and the record itself.
    from ...domain.services.drawing_ingestion_service import DrawingIngestionService
    await DrawingIngestionService.purge_drawing(id)

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
            drawing_numbers=drawing.drawing_numbers,
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
    "/drawings/{id}/scene",
    response_model=StandardResponse[dict],
    summary="Retrieve render-ready vector scene and entity index for interactive canvas",
    dependencies=[Depends(get_auth_token)]
)
async def get_drawing_scene(id: str):
    drawing = await get_or_404(DrawingDocument, id, f"Drawing document not found for ID: {id}")
    entities = await ExtractedEntity.find(ExtractedEntity.drawing_id == id).to_list()
    
    if not entities:
        return StandardResponse(
            success=False,
            error={
                "code": "ENTITIES_NOT_READY",
                "message": "Drawing entities have not been extracted yet."
            },
            data={"layers": {}, "transform": None, "handles": {}}
        )

    layers_data = GeometrySerializer.serialize_entities(entities)
    transform_data = (drawing.metadata or {}).get("viewport_transform")
    
    handles_map = {}
    for ent in entities:
        handle = getattr(ent, "handle", None) or ent.properties.get("handle")
        if handle:
            handles_map[handle] = {
                "id": str(ent.id),
                "type": ent.entity_type.lower(),
                "layer": ent.layer,
                "text": ent.properties.get("text"),
                "geometry": ent.geometry,
            }

    return StandardResponse(
        success=True,
        data={
            "drawing_id": id,
            "layers": layers_data.get("layers", {}),
            "transform": transform_data,
            "handles": handles_map,
            "render_bounds": (drawing.metadata or {}).get("render_bounds"),
        }
    )


# The seven template zones extract_dynamic_regions() resolves, mirrored from
# table_extractor.default_pct. Whitelisted explicitly rather than derived by iterating the
# returned dict: that dict also carries "safe_zones" (a list) and "_zone_confidence" (a
# dict) under reserved keys, and feeding either into a bbox model raises.
ZONE_KEYS = ("views", "notes", "bom", "title", "tolerance", "iso", "title_upper_left", "shim")


def _to_zone_bbox(raw, confidence: str) -> ZoneBBox | None:
    """Coerces one (xmin, ymin, xmax, ymax) tuple into a ZoneBBox, or None if malformed.

    Returning None rather than raising keeps one bad zone from taking down the whole
    overlay — the other six are still useful, and a missing box is visible as such.
    """
    if not isinstance(raw, (tuple, list)) or len(raw) != 4:
        return None
    try:
        xmin, ymin, xmax, ymax = (float(v) for v in raw)
    except (TypeError, ValueError):
        return None
    return ZoneBBox(xmin=xmin, ymin=ymin, xmax=xmax, ymax=ymax, confidence=confidence)


def build_zones_response(
    drawing_id: str,
    regions: dict,
    render_bounds: list[float] | None,
) -> DrawingZonesResponse:
    """Maps extract_dynamic_regions() output onto the wire model.

    Kept a module-level pure function rather than inlined into the handler so the
    reserved-key regression test can call it with a hand-built dict — no FastAPI client,
    no Mongo fixture, no real DXF.
    """
    confidence_by_zone = regions.get("_zone_confidence") or {}
    zones = {
        key: _to_zone_bbox(regions.get(key), confidence_by_zone.get(key, "unknown"))
        for key in ZONE_KEYS
    }
    return DrawingZonesResponse(
        drawing_id=drawing_id,
        render_bounds=render_bounds,
        **zones,
    )


@router.get(
    "/drawings/{id}/zones",
    response_model=StandardResponse[DrawingZonesResponse],
    summary="Detected template-zone bounding boxes for the canvas debug overlay",
    dependencies=[Depends(get_auth_token)]
)
async def get_drawing_zones(id: str):
    """Serves the zone boxes the audit pipeline computes internally, for visual inspection.

    Deliberately independent of any comparison run: zone detection needs one drawing's
    entities and no AI call, so gating it behind /physical-comparison would mean burning an
    LLM call to see why a zone box is wrong. See
    docs/zone-bbox-overlay-implementation-plan.md, architecture decision 1.
    """
    from ...infrastructure.audit.bom.table_extractor import extract_dynamic_regions

    drawing = await get_or_404(DrawingDocument, id, f"Drawing document not found for ID: {id}")
    entities = await ExtractedEntity.find(ExtractedEntity.drawing_id == id).to_list()

    if not entities:
        return StandardResponse(
            success=False,
            error={
                "code": "ENTITIES_NOT_READY",
                "message": "Drawing entities have not been extracted yet."
            },
            data=None
        )

    regions = extract_dynamic_regions(entities)
    return StandardResponse(
        success=True,
        data=build_zones_response(
            drawing_id=id,
            regions=regions,
            render_bounds=(drawing.metadata or {}).get("render_bounds"),
        )
    )


# NOTE: `GET /drawings/{id}/rendering` was removed with the raster display path (ADR-011).
# The canvas draws vectors and no longer fetches a background PNG, and it was this route's only
# client. `storage/renderings/{id}.png` is still generated on upload and still read — but from
# disk, in-process, by `image_cropper` (title-block OCR), `context_builder.load_drawing_png()`
# and `pdf_exporter`. Do not reinstate this route to "restore" the raster: the display path is
# gone on the client side too.


@router.get(
    "/drawings/{id}/gltf",
    summary="Get 3D converted GLTF file of STEP/IGES model",
    dependencies=[Depends(get_auth_token)]
)
async def get_drawing_gltf(id: str):
    drawing = await get_or_404(DrawingDocument, id, f"Drawing document not found for ID: {id}")
    # `id` reaches the filesystem as a filename fragment, so it goes through the guard rather
    # than straight into a join — a path separator or traversal component in a route parameter
    # is the classic way out of a directory that looks hardcoded.
    gltf_path = sandboxed_path("temp", f"model_{id}.gltf")
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
        # `drawing.file_path` is a DB value, and `/` discards its left operand when the right side
        # is absolute — so a plain join here would read whatever absolute path the record names.
        file_path = sandboxed_path(drawing.file_path)
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
    except HTTPException:
        # A rejected path is not "no signature found". Without this the guard's 400 would be
        # swallowed into a success response saying the PDF is unsigned, which is a wrong answer
        # to a question the caller asked, not a degraded one.
        raise
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
