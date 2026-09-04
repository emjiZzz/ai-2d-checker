import hashlib
import uuid
from datetime import UTC, datetime
from pathlib import Path
import aiofiles
from fastapi import HTTPException, UploadFile, status

from ...config import settings
from ...domain.models.drawing_document import DrawingDocument
from ...domain.models.extracted_entity import EXTRACTION_SCHEMA_VERSION, ExtractedEntity
from ...domain.models.extraction_job import ExtractionJob
from ..cad.processing_queue import processing_queue
from ..storage.path_resolver import get_storage_root
from ...logger import correlation_id_var, logger
from ..storage.entity_cache import clear_for_drawing as clear_entity_cache


class DrawingIngestionService:
    """
    Orchestrates CAD drawing uploads, file hashing, sandbox storage management, database
    record creation/resetting, and CAD queue dispatching.
    Decouples storage and CAD pipeline interactions from the HTTP API router layer.

    Called `a domain service` here until 2026-08-14, which is what kept it in `domain/` while
    importing `infrastructure/` and `fastapi`. It is an application service over infrastructure —
    see this package's `__init__.py` for why the fix was to move it rather than invert its
    imports.
    """

    ALLOWED_EXTENSIONS = ("dwg", "dxf", "pdf", "step", "stp", "iges", "igs", "icd", "sldprt", "sldasm")

    @classmethod
    def validate_extension(cls, filename: str) -> str:
        """
        Validates the file extension against allowed drawing formats.
        """
        file_ext = filename.split(".")[-1].lower() if "." in filename else ""
        if file_ext not in cls.ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Unsupported file format. Only proprietary .dwg, open .dxf drawings, .pdf files, 3D .step/.iges models, or iCAD .icd / SolidWorks sldprt/sldasm models are accepted."
            )
        return file_ext

    @classmethod
    async def save_temp_file(cls, file: UploadFile) -> tuple[Path, str, int]:
        """
        Streams uploaded file to a temporary file in the sandbox and computes its SHA-256 hash.
        """
        sha256 = hashlib.sha256()
        total_size = 0
        temp_filename = f"upload_{uuid.uuid4().hex}.tmp"
        temp_upload_path = get_storage_root() / "temp" / temp_filename

        try:
            async with aiofiles.open(temp_upload_path, "wb") as out_file:
                while chunk := await file.read(1024 * 1024):  # 1MB chunk buffer
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

        return temp_upload_path, sha256.hexdigest(), total_size

    @classmethod
    async def process_ingestion(
        cls, file: UploadFile, uploaded_by: str | None = None
    ) -> tuple[DrawingDocument, ExtractionJob, bool]:
        """
        Orchestrates full ingestion flow: temp file save, storage move, database
        model persistence, and processing queue dispatch.

        No hash-based deduplication: every upload becomes its own fresh
        DrawingDocument and is re-parsed. In the room-owned model each drawing
        belongs to exactly one room slot, so re-uploading a corrected file always
        re-ingests instead of silently serving a stale cached parse.

        Returns:
            (drawing_doc, job_doc, is_duplicate) — is_duplicate is always False now
            that dedupe is gone; kept in the tuple/response for wire compatibility.
        """
        file_ext = cls.validate_extension(file.filename or "")
        temp_path, file_hash, total_size = await cls.save_temp_file(file)

        # Unique on-disk name per upload. Two uploads of the same bytes must NOT
        # share a file — otherwise purging one drawing's file would orphan the
        # other. file_hash is still stored on the record (metadata + OCR cache key
        # via ComparisonCacheManager.set_cached_ocr) but never names the file.
        secure_filename = f"{uuid.uuid4().hex}.{file_ext}"
        uploads_dir = get_storage_root() / "uploads"
        uploads_dir.mkdir(parents=True, exist_ok=True)
        final_path = uploads_dir / secure_filename

        try:
            if final_path.exists():
                final_path.unlink()
            temp_path.rename(final_path)
        except Exception as err:
            logger.error(f"Failed to move temp upload file to final destination: {err}")
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except Exception:
                    pass
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to finalize drawing storage."
            )

        drawing = DrawingDocument(
            file_name=file.filename or "drawing.dwg",
            file_path=f"uploads/{secure_filename}",
            file_hash=file_hash,
            file_size_bytes=total_size,
            format=file_ext,
            status="queued",
            # None when the caller sent no identity, which means SHARED rather than orphaned --
            # see DrawingDocument.uploaded_by. Defaulted in the signature so every existing
            # caller (tests, tooling) keeps working and keeps producing shared drawings.
            uploaded_by=uploaded_by,
        )
        await drawing.save()

        job = ExtractionJob(drawing_id=str(drawing.id), status="queued")
        await job.save()

        await processing_queue.enqueue(str(drawing.id), str(job.id))
        logger.info(f"Successfully ingested and queued drawing {drawing.id} ('{drawing.file_name}')")
        return drawing, job, False

    @classmethod
    async def reextract_drawing(cls, drawing_id: str) -> tuple[DrawingDocument, ExtractionJob]:
        """Re-run extraction on a drawing already in storage, from its original file.

        Extraction-time fields do not reach drawings ingested before they existed —
        `render_paths`, `render_text_point`, MTEXT rotation, the elliptical-arc fix — and until
        this route the only cure was deleting the drawing and uploading it again, which loses
        the record, its room slot, its audit history and its id. `EXTRACTION_SCHEMA_VERSION`
        names which drawings are stale; this is how they get fixed.

        Reuses the upload pipeline verbatim rather than reimplementing it. That is the point:
        a second extraction path would drift from the first, and the failure mode of drift here
        is a drawing that renders subtly differently depending on how it was ingested.

        The caller gets the queued job back and polls it exactly like an upload.

        Raises:
            HTTPException 404 — no such drawing.
            HTTPException 409 — an extraction is already queued or running for it; two
                concurrent runs would race on the same entity set.
            HTTPException 422 — the source file is gone, so there is nothing to re-read.
        """
        from ..audit.comparison.cache_manager import ComparisonCacheManager

        drawing = await DrawingDocument.get(drawing_id)
        if not drawing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Drawing {drawing_id} not found.",
            )

        if drawing.status in ("queued", "processing"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Drawing {drawing_id} already has an extraction {drawing.status}. "
                    "Wait for it to finish before re-extracting."
                ),
            )

        # The uploaded file is the input. It is never deleted except by `purge_drawing`, but a
        # drawing whose file went missing must fail here with a reason rather than enqueue a job
        # that dies in the worker with a path error nobody reads.
        source = get_storage_root() / drawing.file_path if drawing.file_path else None
        if not source or not source.exists():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=(
                    f"Source file for drawing {drawing_id} is missing from storage; "
                    "it cannot be re-extracted. Re-upload the drawing instead."
                ),
            )

        # Cached comparisons were computed against the entities this run is about to replace.
        # Leaving them would serve findings whose entities no longer exist — a hit returns in
        # ~0.14s and silently bypasses the whole re-extraction. Cleared BEFORE the job runs so
        # there is no window where a stale hit can be served against new entities.
        ComparisonCacheManager.clear_cache_for_drawing(drawing_id)

        # Entities are NOT deleted here. `ExtractionPipeline.run` replaces them immediately
        # before its own insert, so a parse that fails leaves the previous extraction intact and
        # the drawing keeps rendering. Deleting up front would blank the canvas for as long as
        # the job sits in the queue, and permanently if the job then failed.
        job = ExtractionJob(drawing_id=str(drawing.id), status="queued")
        await job.save()

        drawing.status = "queued"
        drawing.updated_at = datetime.now(UTC)
        await drawing.save()

        await processing_queue.enqueue(str(drawing.id), str(job.id))
        logger.info(
            f"Queued re-extraction for drawing {drawing_id} ('{drawing.file_name}'), "
            f"schema version {drawing.extraction_schema_version} -> {EXTRACTION_SCHEMA_VERSION}"
        )
        return drawing, job

    @classmethod
    async def purge_drawing(cls, drawing_id: str) -> None:
        """
        Hard-deletes a drawing and every artifact it owns: extracted entities,
        extraction jobs, the upload file, the PNG rendering, the GLTF model, all
        comparison/OCR cache files, and finally the DrawingDocument record itself.

        Best-effort per artifact — a missing or unremovable file is logged and
        skipped rather than aborting the purge, so a partial cleanup never leaves
        the DB record dangling. Single source of truth for drawing deletion,
        shared by the drawings DELETE route and room deletion.
        """
        from ..audit.comparison.cache_manager import ComparisonCacheManager

        drawing = await DrawingDocument.get(drawing_id)

        # 1. Parsed entities + jobs
        clear_entity_cache(drawing_id)
        await ExtractedEntity.find(ExtractedEntity.drawing_id == drawing_id).delete()
        await ExtractionJob.find(ExtractionJob.drawing_id == drawing_id).delete()

        # 2. Disk artifacts
        storage_root = get_storage_root()
        candidate_paths = [
            storage_root / drawing.file_path if drawing and drawing.file_path else None,
            storage_root / "renderings" / f"{drawing_id}.png",
            storage_root / "temp" / f"model_{drawing_id}.gltf",
        ]
        for path in candidate_paths:
            if path and path.exists():
                try:
                    path.unlink()
                except Exception as e:
                    logger.warning(f"Failed to delete artifact {path} for drawing {drawing_id}: {e}")

        # 3. Comparison + OCR cache files (canonical purge — matches on drawing_id)
        ComparisonCacheManager.clear_cache_for_drawing(drawing_id)

        # 4. The record
        if drawing:
            await drawing.delete()

        logger.info(f"Purged drawing {drawing_id} and associated artifacts.")
