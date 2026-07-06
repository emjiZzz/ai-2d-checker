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
                self._render_pdf_background(input_abs_path, drawing_id, metadata)
            elif drawing.format.lower() in ("step", "stp", "iges", "igs", "icd"):
                # No 2D background raster needed for 3D GLTF models
                pass
            elif dxf_file_path and dxf_file_path.exists():
                self._render_dxf_background(dxf_file_path, drawing_id, metadata)

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

            drawing.status = "completed"
            drawing.entity_counts = counts
            drawing.metadata = sanitize_utf8(metadata)
            drawing.updated_at = datetime.now(UTC)
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

    def _render_pdf_background(self, pdf_path: Path, drawing_id: str, metadata: dict[str, Any]) -> None:
        try:
            import fitz
            logger.info(f"Generating high-fidelity PDF raster background for drawing {drawing_id}...")
            
            doc = fitz.open(str(pdf_path))
            if len(doc) == 0:
                logger.warning("PDF has no pages. Skipping background rendering.")
                return
                
            page = doc[0]
            
            # Save rendering to safe destination path inside storage directory
            from .path_resolver import get_storage_root
            render_dir = get_storage_root() / "renderings"
            render_dir.mkdir(parents=True, exist_ok=True)
            output_png_path = render_dir / f"{drawing_id}.png"
            
            # Generate high-res image (300 DPI roughly) with transparent background
            matrix = fitz.Matrix(4.0, 4.0)
            pix = page.get_pixmap(matrix=matrix, alpha=True)
            pix.save(str(output_png_path))
            
            # Extract exactly the page bounds (in points)
            # PyMuPDF puts origin (0,0) at top-left. xmin, ymin, xmax, ymax
            # Note: The PDF parser extracts geometry directly using these coordinates.
            rect = page.rect
            metadata["render_bounds"] = [rect.x0, rect.y0, rect.x1, rect.y1]
            
            logger.info(f"PDF Raster Background generated successfully: {output_png_path}")
            
        except Exception as e:
            logger.error(f"Failed to render PDF background: {e}", exc_info=True)

    def _render_dxf_background(self, dxf_path: Path, drawing_id: str, metadata: dict[str, Any]) -> None:
        try:
            import matplotlib
            matplotlib.use('Agg') # Headless background thread safe execution
            import ezdxf
            import matplotlib.pyplot as plt
            from ezdxf.addons.drawing import Frontend, RenderContext
            from ezdxf.addons.drawing.matplotlib import MatplotlibBackend
            
            logger.info(f"Generating high-fidelity CAD layout background for drawing {drawing_id}...")

            # --- Step 1: Configure ezdxf font manager (MUST happen before readfile) ---
            import matplotlib.font_manager as mpl_fm
            from ezdxf.fonts import fonts as ezdxf_fonts

            JAPANESE_FONT_CANDIDATES = [
                r"C:\Windows\Fonts\msgothic.ttc",   # MS Gothic - best AutoCAD compatibility
                r"C:\Windows\Fonts\YuGothR.ttc",    # Yu Gothic Regular
                r"C:\Windows\Fonts\meiryo.ttc",     # Meiryo
                r"C:\Windows\Fonts\MSMINCHO.TTF",   # MS Mincho
            ]

            jp_font_path = None
            for candidate in JAPANESE_FONT_CANDIDATES:
                if Path(candidate).exists():
                    jp_font_path = candidate
                    logger.info(f"Japanese font found: {candidate}")
                    break

            if jp_font_path:
                # Scan Windows Fonts so ezdxf's font manager can locate TTF/TTC files
                ezdxf_fm = ezdxf_fonts.font_manager
                ezdxf_fm.scan_folder(Path(r"C:\Windows\Fonts"))
                jp_font_filename = Path(jp_font_path).name
                ezdxf_fm._fallback_font_name = jp_font_filename

                # Override SHX font mappings: Japanese CAD files use txt.shx + bigfont (extfont2/gothicj)
                # ezdxf cannot render BigFont SHX glyphs — substitute with MS Gothic TTF instead
                for shx_name in ["TXT", "TXT.SHX", "EXTFONT2", "EXTFONT2.SHX",
                                  "GOTHICJ", "GOTHICJ.SHX", "ROMANS", "ROMANS.SHX",
                                  "SIMPLEX", "SIMPLEX.SHX", "CHINESET", "CHINESET.SHX"]:
                    ezdxf_fonts.SHX_FONTS[shx_name] = jp_font_filename

                # Also configure matplotlib to use the same Japanese font
                mpl_fm.fontManager.addfont(jp_font_path)
                prop = mpl_fm.FontProperties(fname=jp_font_path)
                jp_font_name = prop.get_name()
                matplotlib.rcParams['font.sans-serif'] = [jp_font_name, 'DejaVu Sans', 'sans-serif']
                matplotlib.rcParams['font.family'] = 'sans-serif'
                logger.info(f"Japanese font '{jp_font_name}' registered for ezdxf + matplotlib rendering.")
            else:
                logger.warning("No Japanese font found. CJK characters may render as boxes.")

            matplotlib.rcParams['axes.unicode_minus'] = False

            # --- Step 2: Load DXF with smart encoding detection ---
            # Japanese BigFont SHX DXFs (txt.shx + extfont2) MUST use CP932 to decode correctly.
            doc = None
            
            # First try auto-detect (ezdxf uses $DWGCODEPAGE from header)
            try:
                doc = ezdxf.readfile(str(dxf_path))
                logger.info(f"DXF auto-detected encoding: {doc.encoding}")
            except (ezdxf.DXFError, UnicodeDecodeError):
                # Fallback chain if auto-detect fails
                for enc in ["cp932", "utf-8", "latin-1"]:
                    try:
                        doc = ezdxf.readfile(str(dxf_path), encoding=enc)
                        logger.info(f"DXF loaded with fallback encoding: {enc}")
                        break
                    except (ezdxf.DXFError, UnicodeDecodeError):
                        continue
                        
            if doc is None:
                raise ValueError(f"Unable to read DXF file with any supported encoding: {dxf_path}")

            # --- Step 3: Override text styles in the document to use MS Gothic TTF ---
            # This forces ezdxf to render text using the TTF font instead of the missing SHX bigfont files
            if jp_font_path:
                for style in doc.styles:
                    font = style.dxf.get('font', '')
                    bigfont = style.dxf.get('bigfont', '')
                    if font.upper().endswith('.SHX') or bigfont:
                        style.dxf.font = jp_font_filename
                        style.dxf.bigfont = ''
                        logger.info(f"Overriding DXF style '{style.dxf.get('name', '?')}': {font!r}+{bigfont!r} -> {jp_font_filename}")

            
            # --- Step 4: Select best layout to render (Paper Space preferred over Model Space) ---
            paperspace_layouts = [l for l in doc.layouts if l.name.lower() != 'model' and len(l) > 0]
            if paperspace_layouts:
                layout_to_render = paperspace_layouts[0]
                logger.info(f"Rendering Paper Space layout: {layout_to_render.name}")
            else:
                layout_to_render = doc.modelspace()
                logger.info("No Paper Space layouts found. Defaulting to Model Space.")

            fig = plt.figure(figsize=(24, 18), dpi=350)
            ax = fig.add_axes([0, 0, 1, 1])
            ax.set_axis_off()
            ax.set_aspect('equal', 'box')
            
            from ezdxf.addons.drawing.config import BackgroundPolicy, ColorPolicy, Configuration
            ctx = RenderContext(doc)
            ctx.set_current_layout(layout_to_render)
            
            # Configure ezdxf to NOT draw a background rectangle so it remains completely transparent
            # Also swap Black lines to White so they are visible on the dark React canvas grid
            config = Configuration(
                background_policy=BackgroundPolicy.OFF,
                color_policy=ColorPolicy.COLOR_SWAP_BW
            )
            
            # Keep figure transparent to let the frontend React grid show through perfectly
            fig.patch.set_alpha(0.0)
            ax.patch.set_alpha(0.0)
            
            backend = MatplotlibBackend(ax)
            # Render the selected layout (with automatic viewport projection!)
            Frontend(ctx, backend, config=config).draw_layout(layout_to_render, finalize=True)
            
            # Extract the exact tight bounds generated by Matplotlib's autoscale
            xmin, xmax = ax.get_xlim()
            ymin, ymax = ax.get_ylim()
            
            metadata["render_bounds"] = [float(xmin), float(ymin), float(xmax), float(ymax)]
            
            # Save rendering to safe destination path inside storage directory
            render_dir = get_storage_root() / "renderings"
            render_dir.mkdir(parents=True, exist_ok=True)
            output_png_path = render_dir / f"{drawing_id}.png"
            
            fig.savefig(
                str(output_png_path),
                dpi=350,
                transparent=True,
                facecolor='none',
                edgecolor='none'
            )
            plt.close(fig)
            logger.info(f"High-fidelity CAD background rendering successfully saved to: {output_png_path}")
        except Exception as render_e:
            logger.error(f"High-fidelity rendering generation failed: {str(render_e)}\n{traceback.format_exc()}")
            # Ensure figure resources are cleaned up
            try:
                import matplotlib.pyplot as plt
                plt.close('all')
            except Exception:
                pass
