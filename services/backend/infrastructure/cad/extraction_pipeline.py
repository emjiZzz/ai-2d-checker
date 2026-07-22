import time
import traceback
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ...core.security import validate_sandboxed_path
from ...domain.models.drawing_document import DrawingDocument
from ...domain.models.extracted_entity import ExtractedEntity
from ...domain.models.extraction_job import ExtractionJob
from ...infrastructure.storage.path_resolver import get_storage_root
from ...logger import logger
from .dxf_parser import DXFParser
from .oda_converter import ODAConverter
from .pdf_parser import PDFParser
from .three_d_pipeline import ThreeDPipeline



class ExtractionPipeline:
    """
    Coordinates drawing ingestion, format conversion, geometric parsing, and metadata persistence.
    """
    def __init__(self):
        self.converter = ODAConverter()
        self.parser = DXFParser()

    async def run(self, drawing_id: str, job_id: str) -> None:
        """
        Executes the CAD drawing extraction pipeline.
        Must run asynchronously. Safely captures durations and catches all errors.
        """
        start_time = time.time()
        logger.info(f"Kicking off CAD Extraction Pipeline for Drawing ID: {drawing_id} [Job ID: {job_id}]")

        # 1. Load active job and drawing records
        job = await ExtractionJob.get(job_id)
        drawing = await DrawingDocument.get(drawing_id)

        if not job or not drawing:
            logger.error(f"Failed to resolve pipeline documents for drawing {drawing_id} or job {job_id}")
            return

        # Update statuses to processing
        job.status = "processing"
        job.started_at = datetime.now(UTC)
        await job.save()

        drawing.status = "processing"
        await drawing.save()

        # Resolve files inside secure sandbox storage
        storage_root = get_storage_root()
        input_relative = Path(drawing.file_path)
        input_abs_path = storage_root / input_relative
        
        # Enforce canonical check
        try:
            validate_sandboxed_path(input_abs_path)
        except Exception as traversal_e:
            await self._handle_failure(job, drawing, f"Path traversal violation: {str(traversal_e)}")
            return

        if not input_abs_path.exists():
            await self._handle_failure(job, drawing, f"Physical uploaded drawing file not found: {input_abs_path}")
            return

        dxf_file_path = None
        is_temp_dxf = False
        conversion_duration = 0.0

        try:
            # 2. Format conversion/handling
            if drawing.format.lower() in ("step", "stp", "iges", "igs", "icd", "sldprt", "sldasm"):
                logger.info(f"Drawing format is 3D model ({drawing.format}). Initializing 3D pipeline for: {input_abs_path}")
                parser_start = time.time()
                import asyncio
                metadata, mesh_content = await asyncio.to_thread(ThreeDPipeline.parse_and_convert, input_abs_path)
                parsing_duration = time.time() - parser_start
                
                # Write glTF 2.0 JSON to temp folder for the /gltf endpoint to serve
                mesh_path = storage_root / "temp" / f"model_{drawing_id}.gltf"
                if isinstance(mesh_content, bytes):
                    mesh_path.write_bytes(mesh_content)
                else:
                    mesh_path.write_text(mesh_content, encoding="utf-8")
                
                entities = []
                layers = []
                counts = {
                    "vertices": metadata.get("vertex_count", 0),
                    "faces": metadata["face_count"],
                    "triangles": metadata.get("triangle_count", 0),
                    "mesh": 1
                }
            elif drawing.format.lower() == "dwg":
                logger.info(f"Drawing format is DWG. Initializing safe ODA conversion for: {input_abs_path}")
                conv_start = time.time()
                
                # Output to secure temporary directory
                temp_dxf_dir = storage_root / "temp"
                dxf_file_path = await self.converter.convert_dwg_to_dxf(input_abs_path, temp_dxf_dir)
                is_temp_dxf = True
                
                conversion_duration = time.time() - conv_start
                logger.info(f"Drawing conversion to DXF complete. Duration: {conversion_duration:.4f}s")
                
                # Parse DXF using ezdxf
                parser_start = time.time()
                entities, layers, counts, metadata = self.parser.parse_file(dxf_file_path)
                parsing_duration = time.time() - parser_start
            elif drawing.format.lower() == "pdf":
                logger.info(f"Drawing format is PDF. Initializing safe layout extraction for: {input_abs_path}")
                pdf_parser = PDFParser()
                parser_start = time.time()
                entities, layers, counts, metadata = pdf_parser.parse_file(input_abs_path)
                parsing_duration = time.time() - parser_start
            else:
                # Direct DXF path
                dxf_file_path = input_abs_path
                
                # Parse DXF using ezdxf
                parser_start = time.time()
                entities, layers, counts, metadata = self.parser.parse_file(dxf_file_path)
                parsing_duration = time.time() - parser_start

            # 3. Generate High-Fidelity premium background rendering
            if drawing.format.lower() == "pdf":
                from services.backend.infrastructure.rendering.pdf_background_renderer import render_pdf_background
                render_pdf_background(input_abs_path, drawing_id, metadata)
            elif drawing.format.lower() in ("step", "stp", "iges", "igs", "icd"):
                # No 2D background raster needed for 3D GLTF models
                pass
            elif dxf_file_path and dxf_file_path.exists():
                from services.backend.infrastructure.rendering.dxf_background_renderer import render_dxf_background
                render_dxf_background(dxf_file_path, drawing_id, metadata, entities)

            # 4. Persist Extracted Geometry Records into MongoDB
            # Save layers as well (as an entity type)
            bulk_entities: list[ExtractedEntity] = []
            
            def sanitize_utf8(data):
                """Strip only surrogate escape characters that would corrupt MongoDB,
                while fully preserving valid Unicode including Japanese (CJK) characters."""
                if isinstance(data, str):
                    # Direct filtration of characters in the UTF-16 surrogate range: [0xD800, 0xDFFF]
                    # This is extremely robust and does not rely on encoding/decoding cycles
                    return "".join(c for c in data if not (0xD800 <= ord(c) <= 0xDFFF))
                elif isinstance(data, dict):
                    return {sanitize_utf8(k): sanitize_utf8(v) for k, v in data.items()}
                elif isinstance(data, list):
                    return [sanitize_utf8(v) for v in data]
                elif isinstance(data, tuple):
                    return tuple(sanitize_utf8(v) for v in data)
                return data

            for item in layers + entities:
                bulk_entities.append(
                    ExtractedEntity(
                        drawing_id=drawing_id,
                        job_id=job_id,
                        entity_type=item["entity_type"],
                        layer=sanitize_utf8(item.get("layer", "Unknown")),
                        properties=sanitize_utf8(item.get("properties", {})),
                        geometry=sanitize_utf8(item.get("geometry", {}))
                    )
                )

            if bulk_entities:
                await ExtractedEntity.insert_many(bulk_entities)

            # 5. Clean up temporary converted DXF files to optimize disk storage
            if is_temp_dxf and dxf_file_path and dxf_file_path.exists():
                try:
                    dxf_file_path.unlink()
                    logger.info("Successfully deleted temporary sandboxed DXF file.")
                except Exception as clean_e:
                    logger.warning(f"Could not purge temporary DXF file at {dxf_file_path}: {str(clean_e)}")

            # 6. Complete Job & Document records
            total_duration = time.time() - start_time
            
            job.status = "completed"
            job.completed_at = datetime.now(UTC)
            job.conversion_duration_seconds = conversion_duration
            job.parsing_duration_seconds = parsing_duration
            job.total_duration_seconds = total_duration
            job.diagnostics = {
                "extracted_entities_count": len(entities),
                "layers_count": len(layers),
                "metadata": sanitize_utf8(metadata)
            }
            await job.save()

            # --- PHASE 7.2: Auto-revision detection ---
            from services.backend.infrastructure.cad.revision_detector import detect_revision
            part_number, revision_letter = await detect_revision(entities)

            if part_number:
                logger.info(f"Phase 7: Extracted Part Number '{part_number}', Revision '{revision_letter or '0'}'")
                drawing.part_number = part_number
                drawing.revision_letter = revision_letter or "0"

                # Find a previous revision of the same part number
                previous = await DrawingDocument.find_one(
                    DrawingDocument.part_number == part_number,
                    DrawingDocument.is_latest_revision == True,
                    DrawingDocument.id != drawing.id
                )
                if previous:
                    drawing.previous_revision_id = str(previous.id)
                    previous.is_latest_revision = False
                    await previous.save()
                    logger.info(f"Phase 7: Established revision chain. Supersedes previous Rev {previous.revision_letter} (ID: {previous.id}).")

            drawing.is_latest_revision = True
            drawing.status = "completed"
            drawing.entity_counts = counts
            drawing.metadata = sanitize_utf8(metadata)
            drawing.updated_at = datetime.now(UTC)
            await drawing.save()

            # --- PHASE 8: Async 6-View AI Summarization Enrichment ---
            try:
                from .summarization_queue import summarization_queue
                await summarization_queue.enqueue(str(drawing.id))
            except Exception as queue_err:
                logger.error(f"Failed to enqueue summarization task for drawing {drawing.id}: {queue_err}")

            logger.info(
                f"Successfully completed CAD drawing ingestion pipeline for {drawing.file_name} "
                f"in {total_duration:.4f}s. Extracted entities count: {counts}"
            )

        except Exception as pipeline_err:
            error_trace = traceback.format_exc()
            logger.error(f"CAD extraction pipeline aborted with error: {str(pipeline_err)}\n{error_trace}")
            
            # Clean up temp file in case of failure
            if is_temp_dxf and dxf_file_path and dxf_file_path.exists():
                try:
                    dxf_file_path.unlink()
                except Exception:
                    pass

            await self._handle_failure(job, drawing, f"Pipeline Error: {str(pipeline_err)}", error_trace)

    async def _handle_failure(self, job: ExtractionJob, drawing: DrawingDocument, error_msg: str, traceback_str: str = "") -> None:
        """
        Roll back/update records to failed status cleanly.
        """
        job.status = "failed"
        job.completed_at = datetime.now(UTC)
        job.error_message = error_msg
        job.diagnostics = {
            "traceback": traceback_str,
            "failed_at": datetime.now(UTC).isoformat()
        }
        await job.save()

        drawing.status = "failed"
        drawing.updated_at = datetime.now(UTC)
        await drawing.save()


