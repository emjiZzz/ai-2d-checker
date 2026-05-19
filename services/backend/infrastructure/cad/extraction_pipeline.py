import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List
from ...logger import logger
from ...core.security import validate_sandboxed_path
from ...infrastructure.storage.path_resolver import get_storage_root
from ...domain.models.drawing_document import DrawingDocument
from ...domain.models.extraction_job import ExtractionJob
from ...domain.models.extracted_entity import ExtractedEntity
from .oda_converter import ODAConverter
from .dxf_parser import DXFParser

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
        job.started_at = datetime.utcnow()
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
            # 2. DWG format conversion if required
            if drawing.format.lower() == "dwg":
                logger.info(f"Drawing format is DWG. Initializing safe ODA conversion for: {input_abs_path}")
                conv_start = time.time()
                
                # Output to secure temporary directory
                temp_dxf_dir = storage_root / "temp"
                dxf_file_path = await self.converter.convert_dwg_to_dxf(input_abs_path, temp_dxf_dir)
                is_temp_dxf = True
                
                conversion_duration = time.time() - conv_start
                logger.info(f"Drawing conversion to DXF complete. Duration: {conversion_duration:.4f}s")
            else:
                # Direct DXF path
                dxf_file_path = input_abs_path

            # 3. Parse DXF using ezdxf
            parser_start = time.time()
            entities, layers, counts, metadata = self.parser.parse_file(dxf_file_path)
            parsing_duration = time.time() - parser_start

            # 4. Persist Extracted Geometry Records into MongoDB
            # Save layers as well (as an entity type)
            bulk_entities: List[ExtractedEntity] = []
            for item in layers + entities:
                bulk_entities.append(
                    ExtractedEntity(
                        drawing_id=drawing_id,
                        job_id=job_id,
                        entity_type=item["entity_type"],
                        layer=item["layer"],
                        properties=item["properties"],
                        geometry=item["geometry"]
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
            job.completed_at = datetime.utcnow()
            job.conversion_duration_seconds = conversion_duration
            job.parsing_duration_seconds = parsing_duration
            job.total_duration_seconds = total_duration
            job.diagnostics = {
                "extracted_entities_count": len(entities),
                "layers_count": len(layers),
                "metadata": metadata
            }
            await job.save()

            drawing.status = "completed"
            drawing.entity_counts = counts
            drawing.metadata = metadata
            drawing.updated_at = datetime.utcnow()
            await drawing.save()

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
        job.completed_at = datetime.utcnow()
        job.error_message = error_msg
        job.diagnostics = {
            "traceback": traceback_str,
            "failed_at": datetime.utcnow().isoformat()
        }
        await job.save()

        drawing.status = "failed"
        drawing.updated_at = datetime.utcnow()
        await drawing.save()
