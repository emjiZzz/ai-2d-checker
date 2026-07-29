import re
import math
from typing import List, Dict, Any, Optional
from ..bom_analyzer import BOMAnalyzer
from ..bom.title_block_extractor import TITLE_BLOCK_LABEL_KEYWORDS

# BOM column header vocabulary (marking_builder.py's bom_cols display labels, English +
# common Japanese variants) — used only by the Phase 7 value-only-coordinate safety net
# below (docs/checklist-taxonomy-grouping-implementation-plan.md), not for BOM extraction.
BOM_LABEL_KEYWORDS = [
    "no.", "code", "dimension", "q'ty", "material wt", "finished wt", "remark",
    "dwg no.", "dwg. no.", "title", "item",
    "番号", "コード", "寸法", "数量", "重量", "備考", "品名", "図番",
]

LABEL_PROXIMITY_TOLERANCE_MM = 3.0

def _clean_text_for_anchor(raw_text: str) -> str:
    if not raw_text:
        return ""
    t = raw_text.replace('\\P', ' ')
    t = re.sub(r'\{[^}]*\}', '', t)
    t = re.sub(r'\\[A-Za-z0-9\-~|.]+;', '', t)
    return t.strip()

def calc_anchor(e) -> list:
    ins = getattr(e, "geometry", {}).get("location") or getattr(e, "geometry", {}).get("insert") or getattr(e, "geometry", {}).get("text_point") or [0, 0, 0]
    height = e.properties.get("height", 3.0) if getattr(e, "properties", None) else 3.0
    bbox = e.properties.get("bbox", None) if getattr(e, "properties", None) else None
    if bbox and len(bbox) == 2:
        try:
            return [bbox[1][0] + 1.5, bbox[0][1] + (bbox[1][1] - bbox[0][1]) / 2.0]
        except Exception:
            pass
    raw_text = e.properties.get("text", "") if getattr(e, "properties", None) else ""
    clean_text = _clean_text_for_anchor(raw_text)
    clean_len = min(len(clean_text), 12)
    return [ins[0] + (clean_len * height * 0.35) + 1.5, ins[1] + (height / 2.0)]

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
    rev_title_ul_bbox: Optional[tuple],
    ref_title_ul_bbox: Optional[tuple],
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

            # Sibling zone boxes are excluded from a `drawing_views` search alongside the
            # per-cell boxes above. `views` is defined by exclusion, but a *pinned* views
            # zone from a sheet template is a plain rectangle over the whole drawing area
            # with that exclusion no longer baked in -- so without this, a fuzzy text search
            # for a drawing_views finding can match the notes block or the title block and
            # anchor the finding to the wrong part of the sheet.
            def zone_exclusions(*bboxes):
                return [b for b in bboxes if b]

            rev_ex = (
                get_individual_bboxes(rev_bom_rows, rev_title_fields)
                + zone_exclusions(rev_notes_bbox, rev_iso_bbox, rev_title_bbox,
                                  rev_title_ul_bbox, rev_bom_bbox)
            ) if cat == "drawing_views" else None
            ref_ex = (
                get_individual_bboxes(ref_bom_rows, ref_title_fields)
                + zone_exclusions(ref_notes_bbox, ref_iso_bbox, ref_title_bbox,
                                  ref_title_ul_bbox, ref_bom_bbox)
            ) if cat == "drawing_views" else None
            
            def set_region_bbox(kwargs: dict, category: str, is_rev: bool):
                bbox = None
                zone = m.get("zone")  # 'title_upper_left' tag set by extract_title_ul_kv markings
                if category == "bill_of_materials":
                    bbox = rev_bom_bbox if is_rev else ref_bom_bbox
                elif category == "title_block":
                    # Title Upper-Left has its own bbox; fall back to bottom-right title only for normal title_block
                    if zone == "title_upper_left":
                        bbox = rev_title_ul_bbox if is_rev else ref_title_ul_bbox
                    else:
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
                        
                        # HALLUCINATION GUARDRAIL: Check if it actually exists in the reference drawing
                        ref_kwargs = {"category": cat, "used_entities": used_ref_entities, "exclude_bboxes": ref_ex, "match_level": 1}
                        set_region_bbox(ref_kwargs, cat, is_rev=False)
                        ref_res = BOMAnalyzer.find_drawing_text_coordinates(ref_entities, txt, **ref_kwargs)
                        if ref_res:
                            # It exists in both! Override the AI's hallucinated ADDED status.
                            m["status"] = "MATCHED"
                            m["details"] = "Verified match with reference (Auto-corrected AI vision hallucination)"
                            m["ref_coordinates"] = ref_res.get("coords")
                            m["ref_bbox"] = ref_res.get("bbox")
            
            elif status_val == "REMOVED":
                search_txt = m.get("original_value") or txt
                if m.get("ref_coordinates") is None and search_txt and search_txt != "NONE":
                    kwargs = {"category": cat, "used_entities": used_ref_entities, "exclude_bboxes": ref_ex}
                    set_region_bbox(kwargs, cat, is_rev=False)
                    res = BOMAnalyzer.find_drawing_text_coordinates(ref_entities, search_txt, **kwargs)
                    if res:
                        m["ref_coordinates"] = res.get("coords")
                        m["ref_bbox"] = res.get("bbox")
                        
                        # HALLUCINATION GUARDRAIL: Check if it actually exists in the revision drawing
                        rev_kwargs = {"category": cat, "used_entities": used_rev_entities, "exclude_bboxes": rev_ex, "match_level": 1}
                        set_region_bbox(rev_kwargs, cat, is_rev=True)
                        rev_res = BOMAnalyzer.find_drawing_text_coordinates(rev_entities, search_txt, **rev_kwargs)
                        if rev_res:
                            # It exists in both! Override the AI's hallucinated REMOVED status.
                            m["status"] = "MATCHED"
                            m["details"] = "Verified match with reference (Auto-corrected AI vision hallucination)"
                            m["text_content"] = search_txt
                            m["original_value"] = None
                            m["coordinates"] = rev_res.get("coords")
                            m["bbox"] = rev_res.get("bbox")
                    
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


def _is_label_text(raw_text: str) -> bool:
    if not raw_text:
        return False
    norm = raw_text.strip().replace(" ", "").lower()
    for kw in TITLE_BLOCK_LABEL_KEYWORDS + BOM_LABEL_KEYWORDS:
        norm_kw = kw.replace(" ", "").lower()
        if norm_kw == norm or norm_kw in norm or norm in norm_kw:
            return True
    return False


def _label_anchor(e) -> Optional[list]:
    """Same anchor formula as calc_anchor() above — duplicated rather than shared so this
    safety-net check stays self-contained and doesn't couple to calc_anchor()'s own
    evolution (see Phase 7 completion log for the tradeoff)."""
    ins = getattr(e, "geometry", {}).get("location") or getattr(e, "geometry", {}).get("insert") or getattr(e, "geometry", {}).get("text_point") or [0, 0, 0]
    height = e.properties.get("height", 3.0) if getattr(e, "properties", None) else 3.0
    bbox = e.properties.get("bbox", None) if getattr(e, "properties", None) else None
    if bbox and len(bbox) == 2:
        try:
            return [bbox[1][0] + (height * 0.8), bbox[0][1] + (bbox[1][1] - bbox[0][1]) / 2.0]
        except Exception:
            pass
    return [ins[0], ins[1]]


def _collect_label_anchors(entities: List[Any]) -> list:
    anchors = []
    for e in entities:
        if getattr(e, "entity_type", "") not in ("text", "mtext", "attrib"):
            continue
        raw = e.properties.get("text", "") if getattr(e, "properties", None) else ""
        if _is_label_text(raw):
            anchors.append(_label_anchor(e))
    return anchors


def _coincides_with_label(coord: Optional[list], label_anchors: list) -> bool:
    if not coord or len(coord) < 2:
        return False
    for la in label_anchors:
        if la and math.hypot(coord[0] - la[0], coord[1] - la[1]) <= LABEL_PROXIMITY_TOLERANCE_MM:
            return True
    return False


def harden_value_only_coordinates(
    clean_markings: List[Dict[str, Any]],
    ref_entities: List[Any],
    rev_entities: List[Any],
) -> None:
    """
    Phase 7 safety net (docs/checklist-taxonomy-grouping-implementation-plan.md,
    decision 7). The deterministic coordinate-resolution paths in this module and in
    marking_builder.py/title_block_extractor.py are already value-only by construction —
    is_garbage_value() keeps label text from ever being chosen as a field's VALUE in the
    first place, extract_title_ul_kv() only ever emits a marking at its value-band
    entity's own coordinates, and find_drawing_text_coordinates() searches by the
    marking's own value text, never a label's — see the Phase 7 completion log for the
    full read-through audit. This function exists for the one path with no
    deterministic guarantee: Generator B's Gemini-vision visual_bbox coordinates,
    steered by a prompt instruction ("mark VALUES, not labels") rather than enforced,
    plus defense-in-depth against any fuzzy-match edge case the audit didn't anticipate.

    For every title_block/bill_of_materials marking, null out any coordinates/
    ref_coordinates that land within LABEL_PROXIMITY_TOLERANCE_MM of a known label-text
    entity's own anchor point. A nulled coordinate is strictly safer than a wrong one —
    the marking keeps its text/status/details, it just won't get a canvas pin, and can
    still fall through to whatever fallback resolution runs after this (or end up with
    no pin at all, which is a visible gap rather than a silently wrong one).
    """
    rev_label_anchors: Optional[list] = None
    ref_label_anchors: Optional[list] = None

    for m in clean_markings:
        if m.get("category") not in ("title_block", "bill_of_materials"):
            continue

        if m.get("coordinates"):
            if rev_label_anchors is None:
                rev_label_anchors = _collect_label_anchors(rev_entities)
            if _coincides_with_label(m["coordinates"], rev_label_anchors):
                m["coordinates"] = None

        if m.get("ref_coordinates"):
            if ref_label_anchors is None:
                ref_label_anchors = _collect_label_anchors(ref_entities)
            if _coincides_with_label(m["ref_coordinates"], ref_label_anchors):
                m["ref_coordinates"] = None
