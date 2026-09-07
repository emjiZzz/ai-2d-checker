import os
import io
from pathlib import Path
from PIL import Image
from typing import Optional, List, Tuple, Any
from ...logger import logger
from ..storage.path_resolver import get_storage_root
from ..audit.bom.spatial_utils import compute_title_block_bbox

def crop_region_image(
    drawing_id: str,
    metadata: dict,
    cad_bbox: Optional[Tuple[float, float, float, float]],
    margin_pct: float = 0.15,
) -> Optional[bytes]:
    """
    Crops an arbitrary CAD-space bbox region from the rendered drawing PNG and returns
    raw bytes. Maps CAD coordinate system (Y-up) to image pixel coordinate system
    (Y-down). Generalized from crop_title_block_image (below, now a thin wrapper over
    this) so the hybrid pipeline's crop verifier (docs/hybrid-comparison-engine-
    implementation-plan.md, Phase 3) can crop any disputed finding's location, not just
    the title block.

    margin_pct pads the crop by that fraction of the bbox's own width/height on each
    side (minimum 1 CAD unit of padding even for a zero-area bbox, e.g. a marking's
    single coordinate point rather than a real region) — a disputed finding's exact
    location can carry a little jitter between the two generators' coordinate estimates,
    and a tight, unpadded crop risks cutting the actual disputed content out of frame.
    """
    try:
        storage_root = get_storage_root()
        render_path = storage_root / "renderings" / f"{drawing_id}.png"
        if not render_path.exists():
            logger.warning(f"Drawing rendering PNG not found at: {render_path}")
            return None

        bounds = metadata.get("render_bounds")

        img = Image.open(render_path)
        width, height = img.size

        use_fallback = True

        if cad_bbox and bounds and len(bounds) == 4:
            xmin, ymin, xmax, ymax = bounds

            # Enforce bounds validation by raising explicit ValueError instead of assert
            if not (xmin < xmax and ymin < ymax):
                raise ValueError(f"Invalid render bounds for region crop: {bounds}")

            r_xmin, r_ymin, r_xmax, r_ymax = cad_bbox

            # Pad by margin_pct of the region's own size (floor of 1.0 CAD unit so a
            # point-only bbox still gets a usable crop window instead of a 0px slice).
            rw = max(r_xmax - r_xmin, 1.0)
            rh = max(r_ymax - r_ymin, 1.0)
            pad_x = rw * margin_pct
            pad_y = rh * margin_pct
            r_xmin -= pad_x
            r_xmax += pad_x
            r_ymin -= pad_y
            r_ymax += pad_y

            # Clip bounds to sheet limits to prevent coordinates out of range
            r_xmin = max(r_xmin, xmin)
            r_ymin = max(r_ymin, ymin)
            r_xmax = min(r_xmax, xmax)
            r_ymax = min(r_ymax, ymax)

            dx = xmax - xmin
            dy = ymax - ymin

            if dx > 0 and dy > 0:
                # Map CAD coords (Y-up) to image pixels (Y-down)
                p_min_x = int((r_xmin - xmin) / dx * width)
                p_max_x = int((r_xmax - xmin) / dx * width)

                # ymin (bottom) maps to max_y (bottom pixel), ymax (top) maps to min_y (top pixel)
                p_min_y = int((1.0 - (r_ymax - ymin) / dy) * height)
                p_max_y = int((1.0 - (r_ymin - ymin) / dy) * height)

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
                f"Using default bottom-right quadrant fallback for region crop: "
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
        logger.error(f"Failed to crop region image: {e}")
        return None


def crop_title_block_image(drawing_id: str, metadata: dict, entities: list) -> Optional[bytes]:
    """
    Crops the Title Block region from the rendered drawing PNG file and returns raw bytes.
    Thin wrapper over crop_region_image: computes the title-block bbox the way it always
    has, then reuses the generic cropping/fallback logic with margin_pct=0 to preserve
    this function's original tight-crop behavior exactly — existing OCR call sites expect
    the crop to match the title block bbox precisely, not a padded region.
    """
    tb_bbox = compute_title_block_bbox(entities)
    return crop_region_image(drawing_id, metadata, tb_bbox, margin_pct=0.0)
