import re
from pathlib import Path
from ...domain.models.drawing_document import DrawingDocument
from ...infrastructure.storage.path_resolver import get_storage_root
from ...logger import logger

# Matches a leading diameter/radius/plus-minus symbol on dimension text. Entity extraction
# (entity_mapper.py, via the shared strip_mtext canonical decode) now converts the raw
# AutoCAD control-code form to its Unicode symbol before this text is ever stored (e.g.
# "%%c50" -> "Ø50"), so the Unicode form is what normally reaches this point -- the raw
# "%%c"-style match is kept only as a defensive fallback. Regardless of form: some drawings
# carry this symbol as a manually-typed text override, others rely on the DIMENSION entity
# auto-filling from the raw measurement with no symbol at all — a purely cosmetic difference
# between otherwise-identical values that would otherwise read as a false CHANGED diff to
# the comparison model, so it's stripped entirely (not just decoded) for comparison purposes.
_DIM_SYMBOL_PREFIX_RE = re.compile(r'^(?:%%[cCdDpP]|[Ø⌀ΦR±°])\s*(?=\d)')


def _normalize_dim_text(text: str) -> str:
    return _DIM_SYMBOL_PREFIX_RE.sub('', text).strip()

def load_drawing_png(drawing_id: str) -> bytes | None:
    """
    Resolves the pre-rendered PNG from the storage/renderings directory and
    returns its raw bytes for injection into the Gemini Vision multipart request.
    Returns None if the rendering does not exist (non-fatal — falls back to text-only).
    """
    try:
        render_path: Path = get_storage_root() / "renderings" / f"{drawing_id}.png"
        if render_path.exists() and render_path.stat().st_size > 0:
            png_bytes = render_path.read_bytes()
            logger.info(f"Drawing PNG loaded for Gemini Vision: {render_path} ({len(png_bytes):,} bytes)")
            return png_bytes
        logger.warning(f"Drawing PNG not found at {render_path}. Proceeding with text-only audit.")
    except Exception as e:
        logger.warning(f"Failed to load drawing PNG for Vision (non-fatal): {e}")
    return None

def build_structured_context(entities: list, drawing: DrawingDocument) -> dict:
    """
    Pre-processes raw entity logs into structured engineering segments
    to optimize LLM prompt readability and token sizes.
    """
    texts = [e for e in entities if e.entity_type == "text"]
    dimensions = [e for e in entities if e.entity_type == "dimension"]
    blocks = [e for e in entities if e.entity_type == "block"]
    tolerances = [e for e in entities if e.entity_type == "tolerance"]

    def clean_txt(ent) -> str:
        props = ent.properties or {}
        return (props.get("text") or props.get("value") or "").strip()

    # Group and classify title block items
    title_block_items = []
    for txt in texts:
        if txt.layer.lower() in ("am_bor", "border", "title", "title_block"):
            txt_val = clean_txt(txt)
            if txt_val:
                title_block_items.append(txt_val)

    # Extract structured BOM cell entries
    bom_cells = []
    for blk in blocks:
        attrs = blk.properties.get("attributes", {}) if blk.properties else {}
        if attrs:
            bom_cells.append(attrs)

    return {
        "metadata": {
            "file_name": drawing.file_name,
            "format": drawing.format,
            "units": "Metric" if drawing.metadata.get("measurement", 1) == 1 else "Imperial",
            "acad_version": drawing.metadata.get("acad_version", "unknown")
        },
        "layers": list(set(e.layer for e in entities)),
        "geometry_counts": {
            "lines": len([e for e in entities if e.entity_type == "line"]),
            "circles": len([e for e in entities if e.entity_type == "circle"]),
            "arcs": len([e for e in entities if e.entity_type == "arc"]),
            "polylines": len([e for e in entities if e.entity_type == "polyline"])
        },
        "dimensions": [_normalize_dim_text(clean_txt(d)) for d in dimensions if clean_txt(d)],
        "title_block_annotations": title_block_items,
        "bom_table_cells": bom_cells[:20],
        "gd_and_t_frames": [clean_txt(t) for t in tolerances if clean_txt(t)]
    }
