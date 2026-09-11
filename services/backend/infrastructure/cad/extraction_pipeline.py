import asyncio
import time
import traceback
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ...core.security import validate_sandboxed_path
from ...domain.models.drawing_document import DrawingDocument
from ...domain.models.extracted_entity import EXTRACTION_SCHEMA_VERSION, ExtractedEntity
from ...domain.models.extraction_job import ExtractionJob
from ...infrastructure.storage.path_resolver import get_storage_root
from ...logger import logger
from .dxf_parser import DXFParser
from .icd_converter import ICDConverter, count_drawing_entities
from .oda_converter import ODAConverter
from .pdf_parser import PDFParser
from .three_d_pipeline import ThreeDConversionError, ThreeDPipeline
from ..storage.entity_cache import clear_for_drawing as clear_entity_cache



class ExtractionPipeline:
    """
    Coordinates drawing ingestion, format conversion, geometric parsing, and metadata persistence.
    """
    def __init__(self):
        self.converter = ODAConverter()
        self.icd_converter = ICDConverter()
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
            if drawing.format.lower() in ("step", "stp", "iges", "igs", "sldprt", "sldasm"):
                logger.info(f"Drawing format is 3D model ({drawing.format}). Initializing 3D pipeline for: {input_abs_path}")
                parser_start = time.time()
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
            elif drawing.format.lower() == "icd":
                # An .icd carries both a 3D model and 2D drawing content, and either half may
                # be absent. 2D is tried first because it is what the comparison engine reads;
                # a file with no 2D drawing falls through to the 3D pipeline rather than being
                # rejected. Measured on a production sample: 15 of 27 files have no 2D drawing,
                # and one of those carries a 31 MB solid model.
                logger.info(f"Drawing format is iCAD SX. Initializing TR2 conversion for: {input_abs_path}")
                conv_start = time.time()

                temp_dxf_dir = storage_root / "temp"
                dxf_file_path = await self.icd_converter.convert_icd_to_dxf(
                    input_abs_path, temp_dxf_dir
                )
                is_temp_dxf = True

                conversion_duration = time.time() - conv_start
                logger.info(f"iCAD conversion to DXF complete. Duration: {conversion_duration:.4f}s")

                # The translator reports success for an .icd whose 2D drawing was never
                # created, writing a valid DXF holding nothing. Its exit code proves nothing,
                # so the output is counted.
                entity_count = await asyncio.to_thread(count_drawing_entities, dxf_file_path)

                if entity_count:
                    parser_start = time.time()
                    entities, layers, counts, metadata = await asyncio.to_thread(
                        self.parser.parse_file, dxf_file_path
                    )
                    parsing_duration = time.time() - parser_start

                    # Both halves, so the workspace can switch between them without a second
                    # upload. Done here rather than on demand because gmsh is not safe to run
                    # from a request thread -- doing so wedged the backend, spinning without
                    # answering `/health`, which is the failure mode
                    # `06 - .../Gotcha - A Dead Atlas Socket Wedged Every Request.md` describes.
                    # This queue has a single serial consumer, which is where it belongs.
                    #
                    # Best-effort: an .icd holding only a drawing has no model, and that is a
                    # normal file, not a failed one. Cost is bounded -- 5.7s to export and 0.7s
                    # to tessellate on a 196 KB sheet -- and it is paid on the background job,
                    # not on the upload request.
                    mesh_faces = await self._try_extract_icd_mesh(
                        input_abs_path, drawing_id, storage_root, drawing.file_name
                    )
                    if mesh_faces is not None:
                        counts["mesh"] = 1
                        counts["faces"] = mesh_faces
                else:
                    logger.info(
                        f"No 2D content in {drawing.file_name}; extracting its 3D model instead."
                    )
                    # The empty DXF is discarded here rather than at the end: nulling the path
                    # is also what tells the background raster below to skip this drawing, and
                    # a raster of an empty sheet is what would otherwise be produced.
                    try:
                        dxf_file_path.unlink()
                    except Exception:
                        pass
                    dxf_file_path = None
                    is_temp_dxf = False

                    parser_start = time.time()
                    metadata, mesh_content = await asyncio.to_thread(
                        ThreeDPipeline.parse_and_convert, input_abs_path
                    )
                    parsing_duration = time.time() - parser_start

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
                        "mesh": 1,
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
                
                # Parse DXF using ezdxf -- offloaded, see the note above step 3.
                parser_start = time.time()
                entities, layers, counts, metadata = await asyncio.to_thread(
                    self.parser.parse_file, dxf_file_path
                )
                parsing_duration = time.time() - parser_start
            elif drawing.format.lower() == "pdf":
                logger.info(f"Drawing format is PDF. Initializing safe layout extraction for: {input_abs_path}")
                pdf_parser = PDFParser()
                parser_start = time.time()
                entities, layers, counts, metadata = await asyncio.to_thread(
                    pdf_parser.parse_file, input_abs_path
                )
                parsing_duration = time.time() - parser_start
            else:
                # Direct DXF path
                dxf_file_path = input_abs_path

                # Parse DXF using ezdxf -- offloaded, see the note above step 3.
                parser_start = time.time()
                entities, layers, counts, metadata = await asyncio.to_thread(
                    self.parser.parse_file, dxf_file_path
                )
                parsing_duration = time.time() - parser_start

            # 3. Generate High-Fidelity premium background rendering
            #
            # Offloaded via `asyncio.to_thread`, like every other blocking step in this method.
            # This runs inside the single background worker task, which lives on the *same*
            # event loop that serves HTTP -- so anything left inline here stalls every other
            # request for its full duration. `render_dxf_background` is the worst offender in
            # the pipeline: a 24x18in figure at 350 dpi is ~8400x6300 px and takes seconds.
            # See `06 - Gotchas .../Gotcha - The Background Queue Was Not a Background Thread.md`.
            #
            # These mutate `metadata` in place (`render_bounds`, `render_layout`); the awaits
            # below join before anything reads it, so the thread hop changes nothing there.
            #
            # NB both renderers drive matplotlib through the `pyplot` state machine, which is
            # not the thread-safe API -- `render_dxf_background`'s failure path calls
            # `plt.close('all')`. That is only safe because this queue has a single serial
            # consumer, so at most one render is ever in flight. Parallelising the worker
            # requires porting them to the OO `Figure`/`FigureCanvasAgg` API first.
            if drawing.format.lower() == "pdf":
                from services.backend.infrastructure.rendering.pdf_background_renderer import render_pdf_background
                await asyncio.to_thread(render_pdf_background, input_abs_path, drawing_id, metadata)
            elif drawing.format.lower() in ("step", "stp", "iges", "igs"):
                # No 2D background raster needed for 3D GLTF models. `.icd` is not in this
                # list: it converts to DXF above and needs the raster like any other drawing,
                # because `render_bounds` is what zone template fractions are stored against.
                pass
            elif dxf_file_path and dxf_file_path.exists():
                from services.backend.infrastructure.rendering.dxf_background_renderer import render_dxf_background
                await asyncio.to_thread(
                    render_dxf_background, dxf_file_path, drawing_id, metadata, entities
                )

            # Check if a companion 3D STEP file exists (from client-side CAD conversion)
            companion_stp = input_abs_path.with_suffix(".stp")
            if not companion_stp.exists():
                companion_stp = input_abs_path.with_suffix(".step")

            if companion_stp.exists() and "mesh" not in counts:
                try:
                    logger.info(f"Extracting 3D mesh from companion STEP: {companion_stp}")
                    mesh_metadata, mesh_content = await asyncio.to_thread(
                        ThreeDPipeline.parse_and_convert, companion_stp
                    )
                    mesh_path = storage_root / "temp" / f"model_{drawing_id}.gltf"
                    if isinstance(mesh_content, bytes):
                        mesh_path.write_bytes(mesh_content)
                    else:
                        mesh_path.write_text(mesh_content, encoding="utf-8")
                    counts["mesh"] = 1
                    counts["faces"] = mesh_metadata.get("face_count", 0)
                    if "parts" in mesh_metadata:
                        metadata["parts"] = mesh_metadata["parts"]
                    logger.info(f"Companion STEP mesh extraction successful for drawing {drawing_id}")
                except Exception as e:
                    logger.warning(f"Failed to extract companion STEP mesh for drawing {drawing_id}: {e}")

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
                item_props = item.get("properties", {}) or {}
                bulk_entities.append(
                    ExtractedEntity(
                        drawing_id=drawing_id,
                        job_id=job_id,
                        entity_type=item["entity_type"],
                        layer=sanitize_utf8(item.get("layer", "Unknown")),
                        # Promoted from properties so they are indexable; they remain
                        # in `properties` too so existing consumers are unaffected.
                        handle=sanitize_utf8(item_props.get("handle")) or None,
                        parent_handle=sanitize_utf8(item_props.get("parent_handle")) or None,
                        space=item_props.get("space", "model"),
                        viewport_index=int(item_props.get("viewport_index", -1)),
                        properties=sanitize_utf8(item_props),
                        geometry=sanitize_utf8(item.get("geometry", {}))
                    )
                )

            # Replace, never append. `run` had no delete because it was only ever reached once
            # per drawing, straight after upload — so a second run (the re-extract route, a
            # requeued job) would silently DOUBLE every entity, and a doubled payload renders
            # and compares as a plausible drawing rather than as an error.
            #
            # Deliberately here and not at the top: everything above can fail (conversion,
            # parse, render), and on failure the previous extraction must survive intact. By
            # this line the new entities are built and the only remaining step is the write.
            # The cache must die BEFORE the entities do: a reader between the delete and the
            # insert_many below would otherwise repopulate it from a drawing that is briefly
            # empty, and an empty payload caches as a blank sheet rather than as an error.
            clear_entity_cache(drawing_id)
            replaced = await ExtractedEntity.find(
                ExtractedEntity.drawing_id == drawing_id
            ).delete()
            if replaced and getattr(replaced, "deleted_count", 0):
                logger.info(
                    f"Re-extraction: cleared {replaced.deleted_count} existing entities for "
                    f"drawing {drawing_id} before writing {len(bulk_entities)} new ones."
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

            # Drawing-number tokens, for the reference/revision pair guard. Independent of
            # the Phase 7.2 block above, which is dead on real sheets -- see
            # infrastructure/cad/drawing_identity.py for the measurement and for why this
            # does not simply repair `part_number`.
            from services.backend.infrastructure.cad.drawing_identity import (
                extract_drawing_numbers,
            )
            drawing.drawing_numbers = extract_drawing_numbers(entities)
            logger.info(
                f"Drawing identity tokens for {drawing_id}: {drawing.drawing_numbers or 'none found'}"
            )

            # Zone templates store their fractions against `render_bounds`, so if a re-extraction
            # produces different bounds from the ones a template was authored against, every
            # fraction silently maps to the wrong place — a mirrored-overlay class of defect that
            # looks plausible. Re-rendering the same file is deterministic, so this should never
            # fire; it fires when the RENDERER changed between the two extractions, which is
            # exactly the case nobody would think to check.
            previous_bounds = (drawing.metadata or {}).get("render_bounds")
            new_bounds = metadata.get("render_bounds")
            if previous_bounds and new_bounds and list(previous_bounds) != list(new_bounds):
                logger.warning(
                    f"render_bounds CHANGED for drawing {drawing_id} across extractions: "
                    f"{previous_bounds} -> {new_bounds}. Zone templates stored against the old "
                    f"bounds now map to the wrong region and must be re-authored."
                )
                job.diagnostics["render_bounds_changed"] = {
                    "previous": list(previous_bounds),
                    "current": list(new_bounds),
                }
                await job.save()

            drawing.is_latest_revision = True
            drawing.status = "completed"
            drawing.entity_counts = counts
            drawing.metadata = sanitize_utf8(metadata)
            drawing.extraction_schema_version = EXTRACTION_SCHEMA_VERSION
            drawing.transform_version = int(metadata.get("transform_version", 0) or 0)
            drawing.updated_at = datetime.now(UTC)
            await drawing.save()

            # --- PHASE 8: Async 6-View AI Summarization Enrichment (Disabled) ---
            # Disabled to avoid consuming external API tokens during standard ingestion.
            # Local CAD geometry extraction, rendering, and indexing are completely self-sufficient.
            # try:
            #     from .summarization_queue import summarization_queue
            #     await summarization_queue.enqueue(str(drawing.id))
            # except Exception as queue_err:
            #     logger.error(f"Failed to enqueue summarization task for drawing {drawing.id}: {queue_err}")

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

    async def _try_extract_icd_mesh(
        self, source: Path, drawing_id: str, storage_root: Path, file_name: str
    ) -> int | None:
        """Write this .icd's 3D model as glTF, or return None if it has none.

        Never raises. The 2D drawing is already extracted by the time this runs, and an .icd
        holding no model is an ordinary file -- failing the job over it would reject a drawing
        that is entirely fine.
        """
        try:
            metadata, mesh_content = await asyncio.to_thread(
                ThreeDPipeline.parse_and_convert, source
            )
        except ThreeDConversionError as exc:
            logger.info(f"No 3D model in {file_name}: {exc}")
            return None
        except Exception:
            logger.exception(f"3D extraction failed for {file_name}; its 2D drawing is unaffected.")
            return None

        mesh_path = storage_root / "temp" / f"model_{drawing_id}.gltf"
        if isinstance(mesh_content, bytes):
            mesh_path.write_bytes(mesh_content)
        else:
            mesh_path.write_text(mesh_content, encoding="utf-8")
        logger.info(f"3D model extracted for {file_name}: {metadata['face_count']} faces.")
        return int(metadata["face_count"])

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


