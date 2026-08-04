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


def _collect_vertical_rules(entities: list) -> List[tuple]:
    """The title block's ruled vertical lines, as (x, ymin, ymax).

    These are the cell boundaries the proximity search must not read across. They come free with
    the DXF -- LINE/POLYLINE entities reach this extractor because `keep_for_title_extraction`
    filters on `geometry["insert"]`, which line geometry does not have, so the bbox test is a
    no-op for them and they survive (measured: 188 lines on the reference, 189 on the revision of
    the M7452A1N01 pair).

    Only near-exactly-vertical segments count. A tolerance of 0.05 drawing units rejects the
    slightly-off-vertical strokes of drawn glyphs and leader lines while keeping real rules, which
    are axis-aligned to floating-point precision in every sheet measured.
    """
    rules: List[tuple] = []
    for e in entities:
        if getattr(e, "entity_type", "") not in ("line", "polyline", "lwpolyline"):
            continue
        geom = getattr(e, "geometry", {}) or {}
        pts = geom.get("points")
        if not pts:
            start, end = geom.get("start"), geom.get("end")
            pts = [start, end] if start and end else None
        if not pts:
            continue
        pts = [p for p in pts if p and len(p) >= 2]
        for i in range(len(pts) - 1):
            x1, y1 = float(pts[i][0]), float(pts[i][1])
            x2, y2 = float(pts[i + 1][0]), float(pts[i + 1][1])
            if abs(x1 - x2) < 0.05 and abs(y1 - y2) > 0.5:
                rules.append((x1, min(y1, y2), max(y1, y2)))
    return rules

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

    # Coordinate scale for the proximity tolerances below. Those tolerances are absolute
    # distances in drawing units, so they only transfer between drawings drawn at the same
    # scale. This corpus mixes coordinate spaces that differ ~3x (the reference/revision
    # "2.500x" split -- see the coordinate-spaces gotcha in the vault): on the larger drawing
    # the title-block label->value gap is ~30 units, past the ~14 the tolerances assume, so
    # every field read NONE and the whole block came back as ADDED.
    #
    # The previous detector was a binary `any text x>1000 -> 2.0`. It under-shot (the measured
    # reference needs ~3.0, not 2.0, so fields still missed by a hair) and it keys off raw
    # coordinate magnitude, which conflates drawing scale with sheet size. Text height is the
    # scale-invariant signal instead: a title block is lettered at a fixed physical height
    # (~2.5 units at 1:1), so the median text height relative to that baseline recovers the
    # drawing's scale directly. Floored at 1.0 so a small-coordinate drawing never has its
    # tolerances shrunk below the calibrated values (protects the drawings that already work),
    # and capped at 3.0 so an outlier height cannot inflate the multi-line grouping window
    # (which also scales by coord_scale) far enough to swallow a neighbouring column.
    #
    # Measured (2026-07-30, M745227 pair): reference median height 9.6 -> 3.0; revision 2.2
    # -> 1.0 (unchanged). Recalibrate the baseline before trusting this on another standard.
    _BASELINE_TITLE_TEXT_HEIGHT = 2.5
    _heights = [
        float(e.properties["height"])
        for e in entities
        if getattr(e, "entity_type", "") == "text"
        and getattr(e, "properties", None)
        and e.properties.get("height")
    ]
    if _heights:
        _heights.sort()
        _n = len(_heights)
        _median_h = _heights[_n // 2] if _n % 2 else (_heights[_n // 2 - 1] + _heights[_n // 2]) / 2.0
        coord_scale = min(max(_median_h / _BASELINE_TITLE_TEXT_HEIGHT, 1.0), 3.0)
    else:
        coord_scale = 1.0

    # Ruled cell boundaries, used by the 'below' search only -- see _separated_by_rule.
    vertical_rules = _collect_vertical_rules(entities)

    def _separated_by_rule(lx: float, ly: float, vx: float, vy: float) -> bool:
        """True if a ruled vertical line stands between the label and a candidate value.

        The proximity search is a bare rectangle around the label's insert point, so it happily
        reads a value out of a NEIGHBOURING COLUMN when the tolerances are wide enough. That is
        how "Previous Dwg. No." came back as `1`: the label 旧図面番号 sits at (382.1, 89.3) on the
        reference and the search picked the tolerance table's Fabrication cell `1` at
        (364.9, 74.5) -- dx=17.2, admitted because coord_scale inflates dx_tol=8.0 past it. The
        vertical rule at x=380.1 (spanning y 25.0-128.2) is the tolerance-table/title-block
        divider, and it sits squarely between them. Same shape on the revision: label (153.0,
        35.5), bogus candidate (145.9, 29.8), rule at x=152.0 spanning y 10.0-51.0.

        A rule only counts as a separator when its y-span COVERS both points. A stub that merely
        overlaps the band may be a cell divider one row up or down, not one that actually stands
        between these two pieces of text.

        BELOW-SEARCHES ONLY -- do not generalise this to direction='right'. Stepping across a
        vertical rule while searching downward always means landing in the wrong column. Stepping
        across one while searching rightward is the NORMAL label-cell -> value-cell move, and
        JOB NO depends on it: 'Job No.' at (180.9, 11.6) reads its value 9324 at (196.0, 11.5)
        across the rule at x=181.5. Applying this guard there would re-break that field.
        """
        xlo, xhi = min(lx, vx), max(lx, vx)
        ylo, yhi = min(ly, vy), max(ly, vy)
        return any(
            xlo < rx < xhi and ry0 <= ylo and yhi <= ry1
            for rx, ry0, ry1 in vertical_rules
        )

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

    def extract_proximity_value(label_patterns, direction='below', dx_tol=8.0, dy_tol=25.0, dy_min=1.0, exclude_patterns=None, prefer_lowest_y=False, prefer_highest_y=False, multiline=False):
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
                    if _separated_by_rule(lx, ly, vx, vy):
                        continue
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

        # Single-value fields (SCALE, DESIGNED, DRAWN, QTY, DWG_NO, ...) take the closest
        # candidate outright. Only genuinely multi-line fields (e.g. TITLE) run the grouping
        # below. Grouping is what stitched adjacent cells into one value on this corpus --
        # 橋本 (DESIGNED) + 中川 (DRAWN) + an unrelated FSRS2 -- and tuning its window could
        # not separate a single value from its neighbours reliably across coordinate scales.
        if not multiline:
            return closest_candidate[1], closest_candidate[2]

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
            
            # Grouping stitches the stacked lines of ONE multi-line value together. Bound
            # the window to a few text-heights (which scale with the drawing) rather than
            # 10x/80x coord_scale: the old 80x vertical window spanned ~240 units on a
            # coord_scale=3 drawing -- a third of the sheet -- and merged the label, both
            # name cells and an unrelated standard number into a single value
            # ('作 成\n橋本\n中川\nFSRS2'). ~2 char-widths horizontally keeps adjacent columns
            # apart; ~4 line-heights vertically still catches a value that wraps 2-3 lines.
            h = e.properties.get("height", 3.0) or 3.0
            if vx >= lx - 30.0 * coord_scale and (vx - lx) <= scaled_dx_tol:
                # Grouping reuses the same rectangle, so it can stitch a neighbouring column's
                # text onto the value even when the value itself was picked correctly.
                if _separated_by_rule(lx, ly, vx, vy):
                    continue
                if abs(vx - cx) <= max(2.0 * h, 6.0) and abs(vy - cy) <= 4.0 * h:
                    if decoded not in seen_texts:
                        seen_texts.add(decoded)
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

    def resolve_field(field_key: str, label_patterns: list, direction='below', dx_tol=8.0, dy_tol=25.0, dy_min=1.0, exclude_patterns=None, prefer_lowest_y=False, prefer_highest_y=False, multiline=False) -> tuple:
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
                # Grounding miss: the OCR value matches no single text run on the drawing.
                # Two very different reasons this happens, and they need opposite handling:
                #   1. Correct value split across runs -- OCR read 'MI511' + '0A01' as the one
                #      real value 'MI51100A01'. The OCR value is the right, fuller form.
                #   2. Misread -- Gemini read a mislocated reference title-block crop as
                #      'ME17227N24' for the real 'M745227N01' (see the OCR crop gotcha). The
                #      OCR value is wrong and disagrees with the actual drawing text.
                # The spatial reading tells them apart: in case 1 it is a *fragment* of the OCR
                # string (substring either way after normalisation), so keep the OCR value; in
                # case 2 it is unrelated real drawing text, so prefer it over the misread.
                spatial_val, spatial_coords = extract_proximity_value(
                    label_patterns, direction, dx_tol, dy_tol, dy_min,
                    exclude_patterns, prefer_lowest_y, prefer_highest_y, multiline
                )
                sv = str(spatial_val).strip()
                if not sv or sv.upper() == "NONE":
                    return ocr_val_str, spatial_coords
                n_ocr, n_sv = _normalize_for_match(ocr_val_str), _normalize_for_match(sv)
                if n_sv and (n_sv in n_ocr or n_ocr in n_sv):
                    return ocr_val_str, spatial_coords
                return spatial_val, spatial_coords

        # Fallback to spatial heuristics
        return extract_proximity_value(
            label_patterns, direction, dx_tol, dy_tol, dy_min,
            exclude_patterns, prefer_lowest_y, prefer_highest_y, multiline
        )

    f_qty, qty_c = resolve_field("QTY", ["T. Q'ty", "T. Q’ty", "総製作個数"], "below", 20.0, 30.0, 1.0, prefer_highest_y=True)
    f_cross_ref, cross_ref_c = extract_proximity_value(["Cross ref No.", "共通番号"], "below", prefer_highest_y=True)
    f_prev_dwg, prev_dwg_c = extract_proximity_value(["Previous Dwg. No.", "旧図面番号"], "below", prefer_highest_y=True)
    
    f_drawn, drawn_c = resolve_field("DRAWN", ["製図", "drawn"], "below", dx_tol=18.0, dy_tol=18.0, dy_min=0.5, exclude_patterns=["設計", "検図", "承認"])
    f_designed, designed_c = resolve_field("DESIGNED", ["設計", "designed"], "below", dx_tol=18.0, dy_tol=18.0, dy_min=0.5, exclude_patterns=["製図", "検図", "承認"])
    # SCALE sits DIRECTLY BELOW its label in this title block (the value row is under the
    # label row: DESIGNED|DRAWN|SCALE|Y/M/D headers at y~46, values at y~36), exactly like
    # DRAWN/DESIGNED/DWG_NO/TITLE. The old 'right' search skipped the value directly under
    # the label (excluded because dx≈0 < dy_min) and grabbed the adjacent Y/M/D date column
    # instead -- the reference read SCALE as '04/12/22\n20' and the revision as '2026/07/03',
    # producing a false CHANGED against the real scales '1:1' vs '1/1'.
    #
    # dx_tol is deliberately tight (5). On the measured pair the SCALE value sits at dx≈0
    # under its label while the neighbouring Y/M/D date fragment is only ~8 to the right; a
    # dx_tol of 8 separated them by just 0.1 units (and the multi-line grouping step, which
    # reuses dx_tol, would then merge the date fragment onto the value). 5 keeps a 3-unit
    # margin against that date column while still clearing DRAWN on the left (dx≈-15).
    # dy_tol=14 reaches the value ~10 below without touching the row beneath.
    f_scale, scale_c = resolve_field("SCALE", ["SCALE", "尺度"], "below", dx_tol=5.0, dy_tol=14.0, dy_min=1.0)
    
    # JOB NO's value sits to the RIGHT of its label, not below it, and the old 'below' search
    # therefore read NONE on every sheet in this corpus -- hiding a real 2589 -> 9324 edit.
    #
    # The cell is laid out label-cell | value-cell: 工事番号 is set as four SEPARATE single-char
    # vertical TEXT entities (so it never matches as a label -- the English 'Job No.' is the only
    # usable anchor), and 'Job No.' sits at the BOTTOM of that label cell with the value up and to
    # the right. Searching below the bottom-most label ran off the end of the sheet.
    #
    # dx_tol=22 measured across all six DXFs in the corpus; the true value is the CLOSEST
    # candidate on every one:
    #   reference  (coord_scale 1.80): label (451.3, 27.6) -> '2589' dx=38.6 dy=+4.1
    #   revision   (coord_scale 1.00): label (180.9, 11.6) -> '9324' dx=15.1 dy=-0.1
    # Nearest competitor is the 標準図番号 label at dx=31.3 (rev) / 79.3 (ref), outside 22*scale on
    # both. The only other text inside the window is the sheet-margin label ４ (ref dx=25.2, rev
    # dx=9.7); it loses on the right-branch's 4x-dy-weighted distance, which is what makes the
    # ordering safe rather than lucky.
    #
    # direction='right' is what broke SCALE (see the "SCALE Field Read the Date Column" gotcha) --
    # the difference is that SCALE's value genuinely sits below its label whereas JOB NO's
    # genuinely sits to the right. _separated_by_rule is deliberately not applied to 'right'
    # searches for exactly this case: the value is one ruled cell over, by design.
    f_job, job_c = extract_proximity_value(
        ["Job No.", "工事番号"], "right", dx_tol=22.0, dy_tol=25.0, dy_min=1.0, prefer_lowest_y=True
    )
    f_std, std_c = extract_proximity_value(["Std. No.", "標準図番号"], "below")
    f_standard, standard_c = extract_proximity_value(["Standard"], "below")
    
    f_mach, mach_c = extract_proximity_value(["Mach. code", "Unit Code", "機器記号", "ユニット記号"], "below", prefer_lowest_y=True)
    f_dwg, dwg_c = resolve_field("DWG NO", ["DWG. No.", "図面番号", "図番"], "below", dx_tol=20.0, dy_tol=35.0, dy_min=1.0, prefer_lowest_y=True)
    # TITLE is the one field that legitimately wraps to multiple lines (e.g. a product name
    # over a sub-name), so it opts into line grouping. Every other field is single-value.
    f_title, title_c = resolve_field("TITLE", ["TITLE", "名称", "品名"], "below", dx_tol=50.0, dy_tol=35.0, dy_min=1.0, prefer_lowest_y=True, multiline=True)
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
