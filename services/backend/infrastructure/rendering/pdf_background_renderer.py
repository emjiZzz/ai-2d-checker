from pathlib import Path
from typing import Any
from ...logger import logger

def render_pdf_background(pdf_path: Path, drawing_id: str, metadata: dict[str, Any]) -> None:
    try:
        import fitz
        logger.info(f"Generating high-fidelity PDF raster background for drawing {drawing_id}...")
        
        doc = fitz.open(str(pdf_path))
        if len(doc) == 0:
            logger.warning("PDF has no pages. Skipping background rendering.")
            return
            
        page = doc[0]
        
        # Save rendering to safe destination path inside storage directory
        from services.backend.infrastructure.storage.path_resolver import get_storage_root
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
