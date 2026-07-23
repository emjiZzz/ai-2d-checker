import re
import math
from typing import List, Optional
from ...utils.text import safe_decode
from .constants import map_signature_value

# Label/boilerplate keyword list used to keep title-block field-name text from ever
# being mistaken for a field's VALUE (see is_garbage_value below). Exported at module
# level (docs/checklist-taxonomy-grouping-implementation-plan.md, Phase 7) so
# coordinate_resolver.py's value-only-coordinate safety net can reuse the exact same
# label vocabulary instead of maintaining a second, drifting copy.
TITLE_BLOCK_LABEL_KEYWORDS = [
    "designed", "設計", "drawn", "製図", "approved", "承認", "checked", "照査",
    "scale", "尺度", "title", "図面名", "図名", "名称", "jobname",
    "jobno.", "工事番号", "unitcode", "mach.code", "ユニット記号", "機番記号", "機器記号",
    "dwg.no.", "図面番号", "dwgno", "previousdwg.no,", "旧図面番号", "crossrefno.", "共通番号",
    "符号", "年月日", "y/m/d", "amd.", "designchgno.", "dir.", "branch", "std.no.", "標準図番号",
    "machine type", "machinetype", "unit no.", "unitno.", "part no.", "partno.", "dir.", "branch", "amd.", "standard",
    "kusakabe", "electric", "machinery", "co.,ltd", "日下部電機", "t.q'ty", "t.q’ty", "総製作個数", "個数", "q'ty", "stockq'ty",
    "機種", "ユニット", "部品", "特性", "訂正符号"
]

def extract_title_block(entities: list, all_text_list: List[str] = None, ocr_results: dict = None) -> dict:
    """Dynamically search the drawing text tokens for each of the 11 title block fields."""
    if all_text_list is None:
        all_text_list = [e.properties.get("text", "") for e in entities if getattr(e, "entity_type", "") == "text"]

    native_fields = {
        "QTY": "NONE", "CROSS REF NO": "NONE", "PREVIOUS DWG NO": "NONE",
        "DESIGNED": "NONE", "DRAWN": "NONE", "SCALE": "NONE", "NAME": "NONE",
        "TITLE": "NONE", "JOB NO": "NONE", "MACHINE CODE": "NONE",
        "DWG NO": "NONE", "UNIT NO": "NONE", "PART NO": "NONE",
        "STOCK QTY": "NONE", "STD NO": "NONE", "STANDARD": "NONE",
        "REVISION CODE": "NONE"
    }
    native_coords: dict = {k: None for k in native_fields}
    found_native = False

    for e in entities:
        if getattr(e, "entity_type", "") == "block":
            attrs = getattr(e, "properties", {}).get("attributes", {})
            if attrs:
                for tag, val in attrs.items():
                    t_upper = tag.upper().strip()
                    matched_key = None
                    if "TITLE" in t_upper or "NAME" in t_upper:
                        matched_key = "TITLE"
                    elif "DWG" in t_upper and "NO" in t_upper and "PREV" not in t_upper:
                        matched_key = "DWG NO"
                    elif "PART" in t_upper and "NO" in t_upper:
                        matched_key = "PART NO"
                    elif "QTY" in t_upper and "TOTAL" in t_upper:
                        matched_key = "QTY"
                    elif "SCALE" in t_upper:
                        matched_key = "SCALE"
                    elif "DRAWN" in t_upper:
                        matched_key = "DRAWN"
                    elif "DESIGN" in t_upper:
                        matched_key = "DESIGNED"
                    
                    if matched_key:
                        native_fields[matched_key] = val
                        found_native = True
                        ins = getattr(e, "geometry", {}).get("insert")
                        if ins:
                            native_coords[matched_key] = [ins[0], ins[1]]

    if found_native:
        res = {}
        for k in native_fields:
            res[k] = {"value": native_fields[k], "coordinates": native_coords[k]}
        return res

    coord_scale = 1.0
    for e in entities:
        if getattr(e, "entity_type", "") == "text" and getattr(e, "geometry", None):
            ins = e.geometry.get("insert") or [0, 0, 0]
            if ins[0] > 1000:
                coord_scale = 2.0
                break

    def is_garbage_value(text: str) -> bool:
        if not text:
            return True
        t = text.strip()
        if len(t) == 0:
            return True
        norm = t.replace(" ", "").lower()

        for kw in TITLE_BLOCK_LABEL_KEYWORDS:
            norm_kw = kw.replace(" ", "").lower()
            if norm_kw == norm or norm_kw in norm or norm in norm_kw:
                return True
                
        if len(t) <= 2:
            if not re.search(r'[a-zA-Z0-9\u4e00-\u9faf\u3040-\u309f\u30a0-\u30ff]', t):
                return True
            ignored_chars = [
                "工", "事", "番", "号", "発", "尺", "度", "設", "計",
                "製", "図", "名", "称", "面", "個", "数", "単", "位", "前"
            ]
            for ic in ignored_chars:
                if ic in t:
                    return True
                    
        if len(t) == 1:
            if re.search(r'[\u4e00-\u9faf\u3040-\u309f\u30a0-\u30ff]', t):
                return True
                
        return False

    def extract_proximity_value(label_patterns, direction='below', dx_tol=8.0, dy_tol=25.0, dy_min=1.0, exclude_patterns=None, prefer_lowest_y=False, prefer_highest_y=False):
        scaled_dx_tol = dx_tol * coord_scale
        scaled_dy_tol = dy_tol * coord_scale
        scaled_dy_min = dy_min * coord_scale
        
        label_entities = []
        
        for e in entities:
            txt = e.properties.get("text", "").strip() if getattr(e, "properties", None) else ""
            decoded = safe_decode(txt).strip()
            norm_txt = txt.replace(" ", "").lower()
            norm_dec = decoded.replace(" ", "").lower()
            
            for pat in label_patterns:
                norm_pat = pat.replace(" ", "").lower()
                if norm_pat == norm_txt or norm_pat == norm_dec:
                    if exclude_patterns:
                        exclude_found = False
                        for excl in exclude_patterns:
                            norm_excl = excl.replace(" ", "").lower()
                            if norm_excl in norm_txt or norm_excl in norm_dec:
                                exclude_found = True
                                break
                        if exclude_found:
                            continue
                    label_entities.append(e)
                    break
                    
        if not label_entities:
            for e in entities:
                txt = e.properties.get("text", "").strip() if getattr(e, "properties", None) else ""
                decoded = safe_decode(txt).strip()
                norm_txt = txt.replace(" ", "").lower()
                norm_dec = decoded.replace(" ", "").lower()
                
                for pat in label_patterns:
                    norm_pat = pat.replace(" ", "").lower()
                    if len(norm_pat) > 2 and (norm_pat in norm_txt or norm_pat in norm_dec):
                        if exclude_patterns:
                            exclude_found = False
                            for excl in exclude_patterns:
                                norm_excl = excl.replace(" ", "").lower()
                                if norm_excl in norm_txt or norm_excl in norm_dec:
                                    exclude_found = True
                                    break
                            if exclude_found:
                                continue
                        label_entities.append(e)
                        break
                        
        if not label_entities:
            return "NONE", None
            
        if prefer_lowest_y:
            def get_y(ent):
                geom = getattr(ent, "geometry", {}) or {}
                ins = geom.get("insert") or [0, 0, 0]
                return ins[1]
            label_entities.sort(key=get_y)
        elif prefer_highest_y:
            def get_y(ent):
                geom = getattr(ent, "geometry", {}) or {}
                ins = geom.get("insert") or [0, 0, 0]
                return ins[1]
            label_entities.sort(key=get_y, reverse=True)
            
        label_entity = label_entities[0]
        geom = getattr(label_entity, "geometry", {}) or {}
        ins = geom.get("insert") or [0, 0, 0]
        lx, ly = ins[0], ins[1]
        
        candidates = []
        for e in entities:
            if e == label_entity:
                continue
            txt = e.properties.get("text", "").strip() if getattr(e, "properties", None) else ""
            if not txt:
                continue
                
            decoded = safe_decode(txt).strip()
            if is_garbage_value(decoded):
                continue
                
            if exclude_patterns:
                exclude_found = False
                norm_txt_c = txt.replace(" ", "").lower()
                norm_dec_c = decoded.replace(" ", "").lower()
                for excl in exclude_patterns:
                    norm_excl = excl.replace(" ", "").lower()
                    if norm_excl in norm_txt_c or norm_excl in norm_dec_c:
                        exclude_found = True
                        break
                if exclude_found:
                    continue
                    
            e_geom = getattr(e, "geometry", {}) or {}
            e_ins = e_geom.get("insert") or [0, 0, 0]
            vx, vy = e_ins[0], e_ins[1]
            
            if direction == 'below':
                if abs(vx - lx) <= scaled_dx_tol and scaled_dy_min <= (ly - vy) <= scaled_dy_tol:
                    dist = math.sqrt((4.0 * (vx - lx))**2 + (vy - ly)**2)
                    h = e.properties.get("height", 3.0)
                    bbox = e.properties.get("bbox")
                    if bbox and len(bbox) >= 2:
                        xmax, ymin, ymax = bbox[1][0], bbox[0][1], bbox[1][1]
                        candidates.append((dist, decoded, [xmax + (h * 0.8), ymin + ((ymax - ymin) / 2.0)]))
                    else:
                        candidates.append((dist, decoded, [vx + (h * 0.8), vy + (h * 0.5)]))
            elif direction == 'right':
                effective_dy_tol = max(scaled_dy_tol, 25.0 * coord_scale)
                if abs(vy - ly) <= effective_dy_tol and scaled_dy_min <= (vx - lx) <= scaled_dx_tol:
                    dist = math.sqrt((vx - lx)**2 + (4.0 * (vy - ly))**2)
                    h = e.properties.get("height", 3.0)
                    bbox = e.properties.get("bbox")
                    if bbox and len(bbox) >= 2:
                        xmax, ymin, ymax = bbox[1][0], bbox[0][1], bbox[1][1]
                        candidates.append((dist, decoded, [xmax + (h * 0.8), ymin + ((ymax - ymin) / 2.0)]))
                    else:
                        candidates.append((dist, decoded, [vx + (h * 0.8), vy + (h * 0.5)]))
                    
        if not candidates:
            return "NONE", [lx, ly]
            
        candidates.sort(key=lambda item: item[0])
        closest_candidate = candidates[0]
        cx, cy = closest_candidate[2][0], closest_candidate[2][1]
        
        grouped_ents = []
        seen_texts = set()
        for e in entities:
            if getattr(e, "entity_type", "") != "text":
                continue
            txt = e.properties.get("text", "").strip() if getattr(e, "properties", None) else ""
            if not txt:
                continue
            decoded = safe_decode(txt).strip()
            if is_garbage_value(decoded):
                continue
            
            e_geom = getattr(e, "geometry", {}) or {}
            e_ins = e_geom.get("insert") or [0, 0, 0]
            vx, vy = e_ins[0], e_ins[1]
            
            if exclude_patterns:
                exclude_found = False
                norm_txt_c = txt.replace(" ", "").lower()
                norm_dec_c = decoded.replace(" ", "").lower()
                for excl in exclude_patterns:
                    norm_excl = excl.replace(" ", "").lower()
                    if norm_excl in norm_txt_c or norm_excl in norm_dec_c:
                        exclude_found = True
                        break
                if exclude_found:
                    continue
            
            if vx >= lx - 30.0 * coord_scale and (vx - lx) <= scaled_dx_tol:
                if abs(vx - cx) <= 10.0 * coord_scale and abs(vy - cy) <= 80.0 * coord_scale:
                    if decoded not in seen_texts:
                        seen_texts.add(decoded)
                        h = e.properties.get("height", 3.0)
                        bbox = e.properties.get("bbox")
                        if bbox and len(bbox) >= 2:
                            xmax, ymin, ymax = bbox[1][0], bbox[0][1], bbox[1][1]
                            grouped_ents.append((vy, decoded, [xmax + (h * 0.8), ymin + ((ymax - ymin) / 2.0)]))
                        else:
                            grouped_ents.append((vy, decoded, [vx + (h * 0.8), vy + (h * 0.5)]))
        
        if not any(item[1] == closest_candidate[1] for item in grouped_ents):
            grouped_ents.append((cy, closest_candidate[1], closest_candidate[2]))

        if len(grouped_ents) > 0:
            grouped_ents.sort(key=lambda item: item[0], reverse=True)
            merged_text = "\n".join([item[1] for item in grouped_ents])
            return merged_text, grouped_ents[0][2]
        else:
            return closest_candidate[1], closest_candidate[2]

    import unicodedata
    def _normalize_for_match(text: str) -> str:
        if not text:
            return ""
        t = unicodedata.normalize('NFKC', str(text)).lower()
        t = t.replace("%%c", "⌀").replace("%%d", "°").replace("%%p", "±")
        return re.sub(r'\s+', '', t)

    ocr_mapping = {}
    if ocr_results:
        ocr_mapping = {
            "QTY": ocr_results.get("QTY"),
            "DESIGNED": ocr_results.get("DESIGNED"),
            "DRAWN": ocr_results.get("DRAWN"),
            "SCALE": ocr_results.get("SCALE"),
            "DWG NO": ocr_results.get("DWG_NO"),
            "TITLE": ocr_results.get("TITLE")
        }

    def resolve_field(field_key: str, label_patterns: list, direction='below', dx_tol=8.0, dy_tol=25.0, dy_min=1.0, exclude_patterns=None, prefer_lowest_y=False, prefer_highest_y=False) -> tuple:
        ocr_val = ocr_mapping.get(field_key)
        if ocr_val is not None and str(ocr_val).strip() != "" and str(ocr_val).upper().strip() != "NONE":
            ocr_val_str = str(ocr_val).strip()
            norm_ocr = _normalize_for_match(ocr_val_str)
            
            # Ground coordinates using normalized matching
            matched_coords = None
            for e in entities:
                if getattr(e, "entity_type", "") == "text":
                    txt = e.properties.get("text", "") if getattr(e, "properties", None) else ""
                    if txt:
                        decoded = safe_decode(txt)
                        if _normalize_for_match(decoded) == norm_ocr:
                            geom = getattr(e, "geometry", {}) or {}
                            ins = geom.get("insert") or [0, 0, 0]
                            matched_coords = [ins[0], ins[1]]
                            break
                            
            if matched_coords is not None:
                return ocr_val_str, matched_coords
            else:
                # Grounding miss: keep OCR text value and query heuristic coords only
                _, heuristic_coords = extract_proximity_value(
                    label_patterns, direction, dx_tol, dy_tol, dy_min,
                    exclude_patterns, prefer_lowest_y, prefer_highest_y
                )
                return ocr_val_str, heuristic_coords

        # Fallback to spatial heuristics
        return extract_proximity_value(
            label_patterns, direction, dx_tol, dy_tol, dy_min,
            exclude_patterns, prefer_lowest_y, prefer_highest_y
        )

    f_qty, qty_c = resolve_field("QTY", ["T. Q'ty", "T. Q’ty", "総製作個数"], "below", 20.0, 30.0, 1.0, prefer_highest_y=True)
    f_cross_ref, cross_ref_c = extract_proximity_value(["Cross ref No.", "共通番号"], "below", prefer_highest_y=True)
    f_prev_dwg, prev_dwg_c = extract_proximity_value(["Previous Dwg. No.", "旧図面番号"], "below", prefer_highest_y=True)
    
    f_drawn, drawn_c = resolve_field("DRAWN", ["製図", "drawn"], "below", dx_tol=18.0, dy_tol=18.0, dy_min=0.5, exclude_patterns=["設計", "検図", "承認"])
    f_designed, designed_c = resolve_field("DESIGNED", ["設計", "designed"], "below", dx_tol=18.0, dy_tol=18.0, dy_min=0.5, exclude_patterns=["製図", "検図", "承認"])
    f_scale, scale_c = resolve_field("SCALE", ["SCALE", "尺度"], "right", dx_tol=45.0, dy_tol=8.0, dy_min=1.0)
    
    f_job, job_c = extract_proximity_value(["Job No.", "工事番号"], "below", prefer_lowest_y=True)
    f_std, std_c = extract_proximity_value(["Std. No.", "標準図番号"], "below")
    f_standard, standard_c = extract_proximity_value(["Standard"], "below")
    
    f_mach, mach_c = extract_proximity_value(["Mach. code", "Unit Code", "機器記号", "ユニット記号"], "below", prefer_lowest_y=True)
    f_dwg, dwg_c = resolve_field("DWG NO", ["DWG. No.", "図面番号", "図番"], "below", dx_tol=20.0, dy_tol=35.0, dy_min=1.0, prefer_lowest_y=True)
    f_title, title_c = resolve_field("TITLE", ["TITLE", "名称", "品名"], "below", dx_tol=50.0, dy_tol=35.0, dy_min=1.0, prefer_lowest_y=True)
    f_revision, revision_c = extract_proximity_value(["AMD.", "Design Chg No.", "訂正符号"], "below", prefer_highest_y=True)

    res = {
        "QTY": {"value": f_qty, "coordinates": qty_c},
        "CROSS REF NO": {"value": f_cross_ref, "coordinates": cross_ref_c},
        "PREVIOUS DWG NO": {"value": f_prev_dwg, "coordinates": prev_dwg_c},
        "DESIGNED": {"value": f_designed, "coordinates": designed_c},
        "DRAWN": {"value": f_drawn, "coordinates": drawn_c},
        "SCALE": {"value": f_scale, "coordinates": scale_c},
        "JOB NO": {"value": f_job, "coordinates": job_c},
        "STD NO": {"value": f_std, "coordinates": std_c},
        "STANDARD": {"value": f_standard, "coordinates": standard_c},
        "MACHINE CODE": {"value": f_mach, "coordinates": mach_c},
        "DWG NO": {"value": f_dwg, "coordinates": dwg_c},
        "TITLE": {"value": f_title, "coordinates": title_c},
        "STOCK QTY": {"value": "NONE", "coordinates": None},
        "REVISION CODE": {"value": f_revision, "coordinates": revision_c}
    }
    return res
