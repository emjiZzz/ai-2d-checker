import os
import io
from pathlib import Path
from PIL import Image
from typing import Optional, List, Tuple, Any
from ...logger import logger
from ..storage.path_resolver import get_storage_root
from ..audit.bom.spatial_utils import compute_title_block_bbox

def crop_title_block_image(drawing_id: str, metadata: dict, entities: list) -> Optional[bytes]:
    """
    Crops the Title Block region from the rendered drawing PNG file and returns raw bytes.
    Maps CAD coordinate system (Y-up) to image pixel coordinate system (Y-down).
    """
    try:
        storage_root = get_storage_root()
        render_path = storage_root / "renderings" / f"{drawing_id}.png"
        if not render_path.exists():
            logger.warning(f"Drawing rendering PNG not found at: {render_path}")
            return None

        # Compute title block bounding box in CAD space
        tb_bbox = compute_title_block_bbox(entities)
        
        # Get render bounds from metadata
        bounds = metadata.get("render_bounds")
        
        # Load image
        img = Image.open(render_path)
        width, height = img.size

        use_fallback = True

        if tb_bbox and bounds and len(bounds) == 4:
            xmin, ymin, xmax, ymax = bounds
            
            # Enforce bounds validation by raising explicit ValueError instead of assert
            if not (xmin < xmax and ymin < ymax):
                raise ValueError(f"Invalid render bounds for title block crop: {bounds}")
                
            tb_xmin, tb_ymin, tb_xmax, tb_ymax = tb_bbox
            
            # Clip bounds to sheet limits to prevent coordinates out of range
            tb_xmin = max(tb_xmin, xmin)
            tb_ymin = max(tb_ymin, ymin)
            tb_xmax = min(tb_xmax, xmax)
            tb_ymax = min(tb_ymax, ymax)

            dx = xmax - xmin
            dy = ymax - ymin

            if dx > 0 and dy > 0:
                # Map CAD coords (Y-up) to image pixels (Y-down)
                p_min_x = int((tb_xmin - xmin) / dx * width)
                p_max_x = int((tb_xmax - xmin) / dx * width)
                
                # ymin (bottom) maps to max_y (bottom pixel), ymax (top) maps to min_y (top pixel)
                p_min_y = int((1.0 - (tb_ymax - ymin) / dy) * height)
                p_max_y = int((1.0 - (tb_ymin - ymin) / dy) * height)

                # Ensure valid pixel crop boundaries
                p_min_x = max(0, min(p_min_x, width))
                p_max_x = max(0, min(p_max_x, width))
                p_min_y = max(0, min(p_min_y, height))
                p_max_y = max(0, min(p_max_y, height))
                
                if p_min_x < p_max_x and p_min_y < p_max_y:
                    use_fallback = False
                else:
                    logger.warning(
                        f"Computed pixel boundaries are degenerate: X:[{p_min_x}, {p_max_x}] Y:[{p_min_y}, {p_max_y}]. "
                        f"Falling back to default quadrant."
                    )

        if use_fallback:
            # Default fallback: bottom-right quadrant of the drawing rendering (usually bottom-right corner)
            p_min_x = int(width * 0.70)
            p_max_x = width
            p_min_y = int(height * 0.70)
            p_max_y = height
            logger.info(
                f"Using default bottom-right quadrant fallback for title block crop: "
                f"X:[{p_min_x}, {p_max_x}], Y:[{p_min_y}, {p_max_y}]"
            )

        # Perform crop
        cropped_img = img.crop((p_min_x, p_min_y, p_max_x, p_max_y))
        
        # Save cropped image to bytes
        img_byte_arr = io.BytesIO()
        cropped_img.save(img_byte_arr, format='PNG')
        return img_byte_arr.getvalue()
    except ValueError as val_err:
        raise val_err
    except Exception as e:
        logger.error(f"Failed to crop title block image: {e}")
        return None
