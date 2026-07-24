import hashlib
import uuid
from pathlib import Path
import aiofiles
from fastapi import HTTPException, UploadFile, status

from ...config import settings
from ...domain.models.drawing_document import DrawingDocument
from ...domain.models.extracted_entity import ExtractedEntity
from ...domain.models.extraction_job import ExtractionJob
from ...infrastructure.cad.processing_queue import processing_queue
from ...infrastructure.storage.path_resolver import get_storage_root
from ...logger import correlation_id_var, logger


class DrawingIngestionService:
    """
    Domain service responsible for managing CAD drawing uploads, file hashing,
    sandbox storage management, database record creation/resetting, and CAD queue dispatching.
    Decouples storage and CAD pipeline interactions from the HTTP API router layer.
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
    async def process_ingestion(cls, file: UploadFile) -> tuple[DrawingDocument, ExtractionJob, bool]:
        """
        Orchestrates full ingestion flow: temp file save, duplicate handling,
        storage move, database model persistence, and processing queue dispatch.
        
        Returns:
            (drawing_doc, job_doc, is_duplicate)
        """
        file_ext = cls.validate_extension(file.filename or "")
        temp_path, file_hash, total_size = await cls.save_temp_file(file)

        # 1. Check for duplicate drawing hash in MongoDB database
        existing_drawing = await DrawingDocument.find_one(DrawingDocument.file_hash == file_hash)
        if existing_drawing:
            # If drawing is already fully extracted and completed, return existing completed record
            if existing_drawing.status == "completed":
                logger.info(f"Duplicate upload detected for completed drawing {existing_drawing.id}. Preserving cache.")
                existing_job = await ExtractionJob.find_one(
                    ExtractionJob.drawing_id == str(existing_drawing.id),
                    sort=[("created_at", -1)]
                )
                if temp_path.exists():
                    try:
                        temp_path.unlink()
                    except Exception:
                        pass
                
                if not existing_job:
                    # Synthetic placeholder only — no ExtractionJob record exists for this
                    # drawing (e.g. pruned/migrated). Let Beanie assign a real ObjectId;
                    # `id` must be a PydanticObjectId, not an arbitrary string.
                    existing_job = ExtractionJob(
                        drawing_id=str(existing_drawing.id),
                        status="completed",
                        diagnostics={},
                        created_at=existing_drawing.created_at
                    )
                return existing_drawing, existing_job, True

            # If incomplete or failed, reset record and overwrite file
            secure_filename = f"{file_hash}.{file_ext}"
            final_upload_path = get_storage_root() / "uploads" / secure_filename
            try:
                if final_upload_path.exists():
                    final_upload_path.unlink()
                temp_path.rename(final_upload_path)
            except Exception:
                if temp_path.exists():
                    try:
                        temp_path.unlink()
                    except Exception:
                        pass

            await ExtractedEntity.find(ExtractedEntity.drawing_id == str(existing_drawing.id)).delete()
            cls._clear_comparison_cache(str(existing_drawing.id))

            existing_drawing.status = "queued"
            existing_drawing.entity_counts = {}
            existing_drawing.metadata = {}
            existing_drawing.file_path = f"uploads/{secure_filename}"
            existing_drawing.format = file_ext
            await existing_drawing.save()

            existing_job = ExtractionJob(drawing_id=str(existing_drawing.id), status="queued")
            await existing_job.save()

            await processing_queue.enqueue(str(existing_drawing.id), str(existing_job.id))
            return existing_drawing, existing_job, True

        # 2. Ingest brand new drawing
        secure_filename = f"{file_hash}.{file_ext}"
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
            status="queued"
        )
        await drawing.save()

        job = ExtractionJob(drawing_id=str(drawing.id), status="queued")
        await job.save()

        await processing_queue.enqueue(str(drawing.id), str(job.id))
        logger.info(f"Successfully ingested and queued drawing {drawing.id} ('{drawing.file_name}')")
        return drawing, job, False

    @staticmethod
    def _clear_comparison_cache(drawing_id: str) -> None:
        """
        Clears stale comparison cache files on re-upload.
        """
        try:
            cache_dir = get_storage_root() / "cache"
            if cache_dir.exists():
                for f in cache_dir.glob("gemini_comparison_*.json"):
                    if drawing_id in f.name:
                        f.unlink()
        except Exception as cache_del_err:
            logger.warning(f"Could not clear comparison cache files on re-upload: {cache_del_err}")
