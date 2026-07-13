import re
from typing import List, Dict, Any, Optional
from ..bom_analyzer import BOMAnalyzer

def calc_anchor(e) -> list:
    ins = getattr(e, "geometry", {}).get("location") or getattr(e, "geometry", {}).get("insert") or getattr(e, "geometry", {}).get("text_point") or [0, 0, 0]
    height = e.properties.get("height", 3.0) if getattr(e, "properties", None) else 3.0
    bbox = e.properties.get("bbox", None) if getattr(e, "properties", None) else None
    if bbox and len(bbox) == 2:
        try:
            return [bbox[1][0] + (height * 0.8), bbox[0][1] + (bbox[1][1] - bbox[0][1]) / 2.0]
        except Exception:
            pass
    text_len = len(e.properties.get("text", "")) if getattr(e, "properties", None) else 0
    return [ins[0] + text_len * height * 0.6 + (height * 0.8), ins[1] + (height / 2.0)]

def resolve_marking_coordinates(
    clean_markings: List[Dict[str, Any]],
    id_to_rev_entity: Dict[str, Any],
    id_to_ref_entity: Dict[str, Any],
    rev_entities: List[Any],
    ref_entities: List[Any],
    rev_bom_rows: List[Any],
    ref_bom_rows: List[Any],
    rev_title_fields: Dict[str, Any],
    ref_title_fields: Dict[str, Any],
    rev_bom_bbox: Optional[tuple],
    ref_bom_bbox: Optional[tuple],
    rev_title_bbox: Optional[tuple],
    ref_title_bbox: Optional[tuple],
    rev_notes_bbox: Optional[tuple],
    ref_notes_bbox: Optional[tuple],
    rev_iso_bbox: Optional[tuple],
    ref_iso_bbox: Optional[tuple],
    rev_views_bbox: Optional[tuple],
    ref_views_bbox: Optional[tuple],
    used_rev_entities: set,
    used_ref_entities: set
) -> None:
    """Resolves coordinates for all comparison markings using exact ID mappings or fuzzy search fallbacks."""
    for m in clean_markings:
        eid = m.get("entity_id")
        if eid:
            eid_rev = eid if eid.startswith("REV-") else f"REV-{eid}"
            eid_ref = eid if eid.startswith("REF-") else f"REF-{eid}"
            
            status_val = m.get("status")
            if status_val == "REMOVED":
                if eid_ref in id_to_ref_entity:
                    ref_ent = id_to_ref_entity[eid_ref]
                    m["ref_coordinates"] = calc_anchor(ref_ent)
                    used_ref_entities.add(id(ref_ent))
            else:
                if eid_rev in id_to_rev_entity:
                    rev_ent = id_to_rev_entity[eid_rev]
                    m["coordinates"] = calc_anchor(rev_ent)
                    used_rev_entities.add(id(rev_ent))
                if status_val in ["CHANGED", "MATCHED"] and eid_ref in id_to_ref_entity:
                    ref_ent = id_to_ref_entity[eid_ref]
                    m["ref_coordinates"] = calc_anchor(ref_ent)
                    used_ref_entities.add(id(ref_ent))
                    
        # Fallback to fuzzy text search if coordinates are missing
        if m.get("coordinates") is None or m.get("ref_coordinates") is None:
            txt = m.get("text_content", "")
            orig_txt = m.get("original_value") or txt
            cat = m.get("category")
            status_val = m.get("status")
            
            def get_individual_bboxes(rows, fields):
                bboxes = []
                for row in rows:
                    for cell in row.values():
                        if isinstance(cell, dict):
                            c = cell.get("coordinates")
                            if c and len(c) >= 2:
                                bboxes.append((c[0] - 30.0, c[1] - 15.0, c[0] + 30.0, c[1] + 15.0))
                for cell in fields.values():
                    if isinstance(cell, dict):
                        c = cell.get("coordinates")
                        if c and len(c) >= 2:
                            bboxes.append((c[0] - 30.0, c[1] - 15.0, c[0] + 30.0, c[1] + 15.0))
                return bboxes

            rev_ex = get_individual_bboxes(rev_bom_rows, rev_title_fields) if cat == "drawing_views" else None
            ref_ex = get_individual_bboxes(ref_bom_rows, ref_title_fields) if cat == "drawing_views" else None
            
            def set_region_bbox(kwargs: dict, category: str, is_rev: bool):
                bbox = None
                if category == "bill_of_materials":
                    bbox = rev_bom_bbox if is_rev else ref_bom_bbox
                elif category == "title_block":
                    bbox = rev_title_bbox if is_rev else ref_title_bbox
                elif category == "notes_section":
                    bbox = rev_notes_bbox if is_rev else ref_notes_bbox
                elif category == "isometric_view":
                    bbox = rev_iso_bbox if is_rev else ref_iso_bbox
                elif category == "drawing_views":
                    bbox = rev_views_bbox if is_rev else ref_views_bbox
                if bbox:
                    kwargs["region_bbox"] = bbox
            
            if status_val == "ADDED":
                if m.get("coordinates") is None and txt and txt != "NONE":
                    kwargs = {"category": cat, "used_entities": used_rev_entities, "exclude_bboxes": rev_ex}
                    set_region_bbox(kwargs, cat, is_rev=True)
                    res = BOMAnalyzer.find_drawing_text_coordinates(rev_entities, txt, **kwargs)
                    if res:
                        m["coordinates"] = res.get("coords")
                        m["bbox"] = res.get("bbox")
            
            elif status_val == "REMOVED":
                search_txt = m.get("original_value") or txt
                if m.get("ref_coordinates") is None and search_txt and search_txt != "NONE":
                    kwargs = {"category": cat, "used_entities": used_ref_entities, "exclude_bboxes": ref_ex}
                    set_region_bbox(kwargs, cat, is_rev=False)
                    res = BOMAnalyzer.find_drawing_text_coordinates(ref_entities, search_txt, **kwargs)
                    if res:
                        m["ref_coordinates"] = res.get("coords")
                        m["ref_bbox"] = res.get("bbox")
                    
            elif status_val == "CHANGED":
                if m.get("coordinates") is None and txt and txt != "NONE":
                    kwargs = {"category": cat, "used_entities": used_rev_entities, "exclude_bboxes": rev_ex}
                    set_region_bbox(kwargs, cat, is_rev=True)
                    res = BOMAnalyzer.find_drawing_text_coordinates(rev_entities, txt, **kwargs)
                    if res:
                        m["coordinates"] = res.get("coords")
                        m["bbox"] = res.get("bbox")
                search_txt = m.get("original_value") or txt
                if m.get("ref_coordinates") is None and search_txt and search_txt != "NONE":
                    kwargs = {"category": cat, "used_entities": used_ref_entities, "exclude_bboxes": ref_ex}
                    set_region_bbox(kwargs, cat, is_rev=False)
                    res = BOMAnalyzer.find_drawing_text_coordinates(ref_entities, search_txt, **kwargs)
                    if res:
                        m["ref_coordinates"] = res.get("coords")
                        m["ref_bbox"] = res.get("bbox")
                    
            else: # MATCHED
                if m.get("coordinates") is None and txt and txt != "NONE":
                    kwargs = {"category": cat, "used_entities": used_rev_entities, "exclude_bboxes": rev_ex}
                    set_region_bbox(kwargs, cat, is_rev=True)
                    res = BOMAnalyzer.find_drawing_text_coordinates(rev_entities, txt, **kwargs)
                    if res:
                        m["coordinates"] = res.get("coords")
                        m["bbox"] = res.get("bbox")
                if m.get("ref_coordinates") is None and txt and txt != "NONE":
                    kwargs = {"category": cat, "used_entities": used_ref_entities, "exclude_bboxes": ref_ex}
                    set_region_bbox(kwargs, cat, is_rev=False)
                    res = BOMAnalyzer.find_drawing_text_coordinates(ref_entities, txt, **kwargs)
                    if res:
                        m["ref_coordinates"] = res.get("coords")
                        m["ref_bbox"] = res.get("bbox")
