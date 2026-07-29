import re
import math
import unicodedata
import difflib
from typing import Optional, Tuple, List, Any
from ...utils.text import safe_decode, strip_mtext
from .table_extractor import extract_bom_table
from .title_block_extractor import extract_title_block

def find_drawing_text_coordinates(
    entities: list,
    target_text: str,
    category: Optional[str] = None,
    region_bbox: Optional[tuple] = None,
    used_entities: Optional[set] = None,
    exclude_bboxes: Optional[list] = None,
    match_level: int = 5
) -> Optional[dict]:
    """Locate screen anchor coordinates for a given text value in drawings."""
    if not target_text or target_text == "NONE":
        return None
        
    target_norm = unicodedata.normalize('NFKC', target_text).strip().replace(" ", "").replace("\n", "").lower()

    def get_anchor(e) -> dict:
        ins = getattr(e, "geometry", {}).get("location") or getattr(e, "geometry", {}).get("insert") or getattr(e, "geometry", {}).get("text_point") or [0, 0, 0]
        height = e.properties.get("height", 3.0) if getattr(e, "properties", None) else 3.0
        bbox = e.properties.get("bbox", None) if getattr(e, "properties", None) else None
        res = {"coords": None, "bbox": None}
        if bbox:
            try:
                xmin, ymin = bbox[0]
                xmax, ymax = bbox[1]
                box_height = ymax - ymin
                res["coords"] = [xmax + (height * 0.4), ymin + (box_height / 2.0)]
                res["bbox"] = bbox
                return res
            except Exception:
                pass
        text_len = len(e.properties.get("text", "")) if getattr(e, "properties", None) else 0
        estimated_width = text_len * height * 0.6
        is_dim = getattr(e, "entity_type", "") == "dimension"
        
        halign = e.properties.get("halign", 0) if getattr(e, "properties", None) else 0
        attachment_point = e.properties.get("attachment_point", 0) if getattr(e, "properties", None) else 0
        is_center_aligned = (halign in [1, 4]) or (attachment_point in [2, 5, 8])
        
        is_centered = is_dim or is_center_aligned
        offset_x = (estimated_width / 2.0) if is_centered else estimated_width
        padding = height * 0.4
        
        res["coords"] = [ins[0] + offset_x + padding, ins[1] + (height / 2.0)]
        res["bbox"] = [[ins[0] - (offset_x if is_centered else 0), ins[1] - (height / 2.0)], [ins[0] + offset_x, ins[1] + (height * 1.5)]]
        return res

    def in_region(e) -> bool:
        if not region_bbox:
            return False
        ins = getattr(e, "geometry", {}).get("location") or getattr(e, "geometry", {}).get("insert") or getattr(e, "geometry", {}).get("text_point") or [0, 0, 0]
        rx0, ry0, rx1, ry1 = region_bbox
        return rx0 <= ins[0] <= rx1 and ry0 <= ins[1] <= ry1

    def in_excluded_region(e) -> bool:
        if not exclude_bboxes:
            return False
        ins = getattr(e, "geometry", {}).get("location") or getattr(e, "geometry", {}).get("insert") or getattr(e, "geometry", {}).get("text_point") or [0, 0, 0]
        ex, ey = ins[0], ins[1]
        for bbox in exclude_bboxes:
            if bbox and len(bbox) == 4:
                if bbox[0] <= ex <= bbox[2] and bbox[1] <= ey <= bbox[3]:
                    return True
        return False

    def layer_matches_category(layer_str: str, cat: Optional[str]) -> bool:
        if not cat:
            return False
        l = (layer_str or "").lower()
        if cat == "title_block":
            return any(x in l for x in ("title", "border", "stamp", "attr", "admin", "block", "header", "logo", "dwg", "rev", "approved", "checked", "designed", "drawn", "scale"))
        if cat == "bill_of_materials":
            return any(x in l for x in ("bom", "parts", "material", "partslist", "materials"))
        if cat == "notes_section":
            return any(x in l for x in ("note", "anno", "comment", "annotation", "text"))
        if cat == "drawing_views":
            return any(x in l for x in ("dim", "dimension", "callout", "geometry", "anno", "0"))
        return False

    inside_region = []
    layer_priority = []
    elsewhere = []
    for e in entities:
        if getattr(e, "entity_type", "") not in ["text", "mtext", "dimension", "multileader", "tolerance", "block"] or not getattr(e, "geometry", None):
            continue
            
        if in_excluded_region(e):
            continue
            
        # Strictly enforce bounding box for ALL categories so entities outside their designated zone box are never miscategorized
        if region_bbox and not in_region(e):
            continue
            
        layer = getattr(e, "layer", "") or ""
        if region_bbox and in_region(e):
            inside_region.append(e)
        elif layer_matches_category(layer, category):
            layer_priority.append(e)
        else:
            is_cross_contaminated = False
            for other_cat in ["title_block", "bill_of_materials"]:
                if category != other_cat and layer_matches_category(layer, other_cat):
                    is_cross_contaminated = True
                    break
            if not is_cross_contaminated:
                elsewhere.append(e)

    search_order = inside_region + layer_priority + elsewhere

    for e in search_order:
        if used_entities is not None and id(e) in used_entities:
            continue
            
        # Safeguard: Do not match short strings or pure numbers (like quantities) outside their designated region
        # otherwise it will hallucinate and match geometric dimensions on the CAD drawing.
        is_short_or_numeric = len(target_norm) < 4 or target_norm.isnumeric()
        if region_bbox and e in elsewhere and is_short_or_numeric:
            continue
            
        raw_txt = e.properties.get("text", "") if getattr(e, "properties", None) else ""
        if raw_txt:
            decoded = strip_mtext(safe_decode(raw_txt))
            dec_norm = unicodedata.normalize('NFKC', decoded).strip().replace(" ", "").replace("\n", "").lower()
            if dec_norm == target_norm:
                if used_entities is not None:
                    used_entities.add(id(e))
                return get_anchor(e)

    if match_level <= 1:
        return None

    for e in search_order:
        if used_entities is not None and id(e) in used_entities:
            continue
            
        is_short_or_numeric = len(target_norm) < 4 or target_norm.isnumeric()
        if region_bbox and e in elsewhere and is_short_or_numeric:
            continue
            
        raw_txt = e.properties.get("text", "") if getattr(e, "properties", None) else ""
        if raw_txt:
            decoded = strip_mtext(safe_decode(raw_txt))
            dec_norm = unicodedata.normalize('NFKC', decoded).strip().replace(" ", "").replace("\n", "").lower()
            if target_norm in dec_norm:
                if len(target_norm) > 2:
                    if used_entities is not None:
                        used_entities.add(id(e))
                    return get_anchor(e)
                else:
                    if re.search(r'(^|\D)' + re.escape(target_norm) + r'(\D|$)', dec_norm):
                        if used_entities is not None:
                            used_entities.add(id(e))
                        return get_anchor(e)

    if match_level <= 2:
        return None

    if len(target_norm) >= 3:
        prefix = target_norm[:2]
        for e in search_order:
            if used_entities is not None and id(e) in used_entities:
                continue
            raw_txt = e.properties.get("text", "") if getattr(e, "properties", None) else ""
            if raw_txt:
                decoded = strip_mtext(safe_decode(raw_txt))
                dec_norm = unicodedata.normalize('NFKC', decoded).strip().replace(" ", "").replace("\n", "").lower()
                if len(dec_norm) >= 2 and (prefix in dec_norm or dec_norm.startswith(prefix)):
                    if used_entities is not None:
                        used_entities.add(id(e))
                    return get_anchor(e)

    if len(target_norm) > 4:
        for e in search_order:
            if used_entities is not None and id(e) in used_entities:
                continue
            raw_txt = e.properties.get("text", "") if getattr(e, "properties", None) else ""
            if raw_txt:
                decoded = strip_mtext(safe_decode(raw_txt))
                dec_norm = unicodedata.normalize('NFKC', decoded).strip().replace(" ", "").replace("\n", "").lower()
                if len(dec_norm) >= 3 and dec_norm in target_norm:
                    if used_entities is not None:
                        used_entities.add(id(e))
                    return get_anchor(e)

    if len(target_norm) >= 4:
        for e in search_order:
            if used_entities is not None and id(e) in used_entities:
                continue
            raw_txt = e.properties.get("text", "") if getattr(e, "properties", None) else ""
            if raw_txt:
                decoded = strip_mtext(safe_decode(raw_txt))
                dec_norm = unicodedata.normalize('NFKC', decoded).strip().replace(" ", "").replace("\n", "").lower()
                if len(dec_norm) >= 3:
                    if difflib.SequenceMatcher(None, target_norm, dec_norm).ratio() > 0.8:
                        if used_entities is not None:
                            used_entities.add(id(e))
                        return get_anchor(e)

    return None

def _bom_region(rows: list, entities: list) -> Optional[tuple]:
    """Covering coordinates for all BOM row entries in a drawing."""
    xs, ys = [], []
    for row in rows:
        for cell in row.values():
            if isinstance(cell, dict):
                c = cell.get("coordinates")
                if c and len(c) >= 2:
                    xs.append(c[0])
                    ys.append(c[1])
    if not xs:
        return None
    pad = 40.0
    return (min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad)

def _title_region(fields: dict, entities: list) -> Optional[tuple]:
    """Covering coordinates for all title block fields in a drawing."""
    xs, ys = [], []
    for cell in fields.values():
        if isinstance(cell, dict):
            c = cell.get("coordinates")
            if c and len(c) >= 2:
                xs.append(c[0])
                ys.append(c[1])
    if not xs:
        return None
    pad = 40.0
    return (min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad)

def compute_bom_bbox(entities: List[Any]) -> Optional[Tuple[float, float, float, float]]:
    """Compute the absolute geometric bounding box for the BOM region."""
    from .table_extractor import extract_dynamic_regions
    return extract_dynamic_regions(entities).get("bom")

def compute_notes_bbox(entities: List[Any]) -> Optional[Tuple[float, float, float, float]]:
    """Compute the absolute geometric bounding box for the Notes region."""
    from .table_extractor import extract_dynamic_regions
    return extract_dynamic_regions(entities).get("notes")

def compute_iso_bbox(entities: List[Any]) -> Optional[Tuple[float, float, float, float]]:
    """Compute the absolute geometric bounding box for the ISO region."""
    from .table_extractor import extract_dynamic_regions
    return extract_dynamic_regions(entities).get("iso")

def compute_views_bbox(entities: List[Any]) -> Optional[Tuple[float, float, float, float]]:
    """Compute the absolute geometric bounding box for the Drawing Views region."""
    from .table_extractor import extract_dynamic_regions
    return extract_dynamic_regions(entities).get("views")

def compute_title_block_bbox(entities: List[Any]) -> Optional[Tuple[float, float, float, float]]:
    """Compute the absolute geometric bounding box for the Title Block region."""
    from .table_extractor import extract_dynamic_regions
    return extract_dynamic_regions(entities).get("title")

def compute_tolerance_table_bbox(entities: List[Any]) -> Optional[Tuple[float, float, float, float]]:
    """Compute the absolute geometric bounding box for the Tolerance Table (bottom-left) region."""
    from .table_extractor import extract_dynamic_regions
    return extract_dynamic_regions(entities).get("tolerance")

def compute_drawing_bounds(entities: List[Any]) -> Optional[Tuple[float, float, float, float]]:
    """Compute the absolute max and min bounding box of all lines in the drawing, to represent the layout boundaries."""
    lines = []
    for e in entities:
        if getattr(e, "entity_type", "") == "line":
            geo = getattr(e, "geometry", {})
            if "start" in geo and "end" in geo:
                lines.append((geo["start"], geo["end"]))
        elif getattr(e, "entity_type", "") == "polyline":
            geo = getattr(e, "geometry", {})
            if "vertices" in geo:
                pts = geo["vertices"]
                for i in range(len(pts) - 1):
                    lines.append((pts[i], pts[i+1]))
            elif "points" in geo:
                pts = geo["points"]
                for i in range(len(pts) - 1):
                    lines.append((pts[i], pts[i+1]))

    if not lines:
        return None

    min_x = min(min(p1[0], p2[0]) for p1, p2 in lines)
    max_x = max(max(p1[0], p2[0]) for p1, p2 in lines)
    min_y = min(min(p1[1], p2[1]) for p1, p2 in lines)
    max_y = max(max(p1[1], p2[1]) for p1, p2 in lines)
    
    return (min_x, min_y, max_x, max_y)
