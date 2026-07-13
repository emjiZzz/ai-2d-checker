import re
from typing import Optional, Tuple
from ...utils.text import compare_values
from .constants import map_signature_value

def extract_dynamic_regions(entities: list) -> dict:
    """
    Determines sheet boundary and title block/BOM regions dynamically.
    """
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

    default_regions = {
        "views":         { "xMin": 0.04, "xMax": 0.68, "yMin": 0.12, "yMax": 0.88 },
        "notes":         { "xMin": 0.04, "xMax": 0.38, "yMin": 0.18, "yMax": 0.62 },
        "bom":           { "xMin": 0.62, "xMax": 0.98, "yMin": 0.04, "yMax": 0.44 },
        "title":         { "xMin": 0.38, "xMax": 0.98, "yMin": 0.72, "yMax": 0.98 },
        "tolerance":     { "xMin": 0.02, "xMax": 0.40, "yMin": 0.65, "yMax": 0.98 },
        "titleUpperLeft":{ "xMin": 0.02, "xMax": 0.35, "yMin": 0.02, "yMax": 0.35 },
        "iso":           { "xMin": 0.62, "xMax": 0.98, "yMin": 0.42, "yMax": 0.74 }
    }

    if not lines:
        return default_regions

    min_x = min(min(p1[0], p2[0]) for p1, p2 in lines)
    max_x = max(max(p1[0], p2[0]) for p1, p2 in lines)
    min_y = min(min(p1[1], p2[1]) for p1, p2 in lines)
    max_y = max(max(p1[1], p2[1]) for p1, p2 in lines)

    width = max_x - min_x
    height = max_y - min_y
    if width <= 0 or height <= 0:
        return default_regions

    tr_lines = [l for l in lines if (l[0][0]-min_x)/width > 0.6 and (l[0][1]-min_y)/height < 0.5]
    br_lines = [l for l in lines if (l[0][0]-min_x)/width > 0.4 and (l[0][1]-min_y)/height > 0.6]
    bl_lines = [l for l in lines if (l[0][0]-min_x)/width < 0.4 and (l[0][1]-min_y)/height > 0.6]

    def get_bounds(quad_lines, default_box):
        if not quad_lines:
            return default_box
        qx_min = min(min(p1[0], p2[0]) for p1, p2 in quad_lines)
        qx_max = max(max(p1[0], p2[0]) for p1, p2 in quad_lines)
        qy_min = min(min(p1[1], p2[1]) for p1, p2 in quad_lines)
        qy_max = max(max(p1[1], p2[1]) for p1, p2 in quad_lines)
        return {
            "xMin": max(0.0, (qx_min - min_x) / width - 0.01),
            "xMax": min(1.0, (qx_max - min_x) / width + 0.01),
            "yMin": max(0.0, (qy_min - min_y) / height - 0.01),
            "yMax": min(1.0, (qy_max - min_y) / height + 0.01)
        }

    bom_bounds = get_bounds(tr_lines, default_regions["bom"])
    title_bounds = get_bounds(br_lines, default_regions["title"])
    tolerance_bounds = get_bounds(bl_lines, default_regions["tolerance"])

    return {
        "views":         default_regions["views"],
        "notes":         default_regions["notes"],
        "bom":           bom_bounds,
        "title":         title_bounds,
        "tolerance":     tolerance_bounds,
        "titleUpperLeft":default_regions["titleUpperLeft"],
        "iso":           default_regions["iso"]
    }

def extract_bom_table(entities: list, render_bounds: Optional[list] = None) -> Tuple[list, bool]:
    """Auto-detect drawing type (Parts vs Assembly) and extract all BOM rows.
    Returns (extracted_rows, is_assembly) where extracted_rows is a list of dicts.
    """
    bom_coord_scale = 1.0
    if render_bounds and len(render_bounds) >= 4:
        if render_bounds[2] - render_bounds[0] > 1200:
            bom_coord_scale = 2.0
    else:
        for e in entities:
            if getattr(e, "entity_type", "") == "text" and getattr(e, "geometry", None):
                ins = e.geometry.get("insert") or [0, 0, 0]
                if 1000 < ins[0] < 5000:
                    bom_coord_scale = 2.0
                    break

    def bom_norm(text: str) -> str:
        return text.strip().replace(" ", "").lower()

    all_ys = [(e.geometry or {}).get("insert", [0, 0, 0])[1]
              for e in entities if getattr(e, "entity_type", "") == "text" and getattr(e, "geometry", None)]
    
    # Auto-detect dynamic coordinates bounds inside the BOM quadrant
    regions = extract_dynamic_regions(entities)
    
    # Assembly drawings don't have finished weight/material weight cells.
    # Check text tokens to see if "Material Wt" or "仕上重量" is present.
    is_assembly = True
    for e in entities:
        if getattr(e, "entity_type", "") == "text":
            val = (e.properties.get("text") or e.properties.get("value") or "").strip()
            if any(k in val.lower() for k in ["material wt", "仕上重量", "finished wt", "材質", "寸法"]):
                is_assembly = False
                break

    # Native BOM block attributes parser
    native_rows = []
    seen_items = set()
    for e in entities:
        if getattr(e, "entity_type", "") == "block" and getattr(e, "properties", None):
            attrs = e.properties.get("attributes", {})
            if attrs:
                # Locate the item number attribute tag
                item_no = None
                for tag in ("NO", "ITEM", "番号", "項目"):
                    if tag in attrs and str(attrs[tag]).strip():
                        item_no = str(attrs[tag]).strip()
                        break
                
                # Check standard regex pattern
                if item_no and re.match(r'^\d{1,3}$', item_no):
                    num = int(item_no)
                    if num in seen_items:
                        continue
                    seen_items.add(num)
                    
                    row = {
                        "NO": map_signature_value(item_no),
                        "QTY": map_signature_value("1")
                    }
                    if is_assembly:
                        row.update({
                            "DWG_NO": map_signature_value(attrs.get("DWG", attrs.get("DWG_NO", attrs.get("図面番号")))),
                            "TITLE": map_signature_value(attrs.get("NAME", attrs.get("TITLE", attrs.get("名称", attrs.get("品名"))))),
                            "QTY": map_signature_value(attrs.get("QTY", attrs.get("個数", attrs.get("数量", "1")))),
                            "REMARK": map_signature_value(attrs.get("REMARK", attrs.get("備考", ""))),
                        })
                    else:
                        row.update({
                            "CODE": map_signature_value(attrs.get("MATERIAL", attrs.get("CODE", attrs.get("材質")))),
                            "DIMENSION": map_signature_value(attrs.get("SIZE", attrs.get("DIMENSION", attrs.get("寸法", attrs.get("型式"))))),
                            "QTY": map_signature_value(attrs.get("QTY", attrs.get("個数", attrs.get("数量", "1")))),
                            "MATERIAL_WEIGHT": map_signature_value(attrs.get("MAT_WT", attrs.get("MATERIAL_WEIGHT", attrs.get("素材重量")))),
                            "FINISHED_WEIGHT": map_signature_value(attrs.get("FIN_WT", attrs.get("FINISHED_WEIGHT", attrs.get("仕上重量")))),
                            "REMARK": map_signature_value(attrs.get("REMARK", attrs.get("備考", ""))),
                        })
                    native_rows.append(row)

    if native_rows:
        return sorted(native_rows, key=lambda r: int(r["NO"]) if r["NO"] != "NONE" else 999), is_assembly

    # Proximity spatial layout heuristics fallback for unexploded/text-based BOMs
    bom_texts = []
    
    # Filter text objects in the BOM quadrant: x in [0.60, 0.98] and y in [0.04, 0.48]
    for e in entities:
        if getattr(e, "entity_type", "") == "text" and getattr(e, "geometry", None):
            ins = e.geometry.get("insert") or [0, 0, 0]
            val = (e.properties.get("text") or e.properties.get("value") or "").strip()
            if val:
                bom_texts.append((ins[0], ins[1], val, e))

    if not bom_texts:
        return [], is_assembly

    min_x_sheet = min(t[0] for t in bom_texts)
    max_x_sheet = max(t[0] for t in bom_texts)
    min_y_sheet = min(t[1] for t in bom_texts)
    max_y_sheet = max(t[1] for t in bom_texts)
    
    w_sheet = max_x_sheet - min_x_sheet
    h_sheet = max_y_sheet - min_y_sheet

    bom_box = regions["bom"]
    bom_x_min = min_x_sheet + bom_box["xMin"] * w_sheet
    bom_x_max = min_x_sheet + bom_box["xMax"] * w_sheet
    bom_y_min = min_y_sheet + bom_box["yMin"] * h_sheet
    bom_y_max = min_y_sheet + bom_box["yMax"] * h_sheet
    
    # Adjust absolute threshold for scale changes
    if bom_coord_scale == 2.0:
        bom_x_min = min_x_sheet + 0.58 * w_sheet

    bom_filtered = [t for t in bom_texts if bom_x_min <= t[0] <= bom_x_max and bom_y_min <= t[1] <= bom_y_max]
    
    # Group rows dynamically by their y coordinates (with ±4mm threshold)
    y_threshold = 4.0 * bom_coord_scale
    rows_grouped = []
    
    for x, y, val, ent in bom_filtered:
        found_row = False
        for group in rows_grouped:
            avg_y = sum(item[1] for item in group) / len(group)
            if abs(y - avg_y) <= y_threshold:
                group.append((x, y, val, ent))
                found_row = True
                break
        if not found_row:
            rows_grouped.append([(x, y, val, ent)])

    # Sort each row horizontally (by x coordinate) and discard rows with no valid numbers
    extracted_rows = []
    
    # Assembly drawings structure: No., DWG No., TITLE, Q'ty, Remark
    # Parts drawings structure: No., Code, Dimension, Q'ty, Material Wt, Finished Wt, Remark
    for group in rows_grouped:
        group.sort(key=lambda item: item[0])
        
        # A valid BOM row should have multiple columns (at least No, Name, Qty)
        if len(group) < 3:
            continue
            
        # The Item Number must be at the far left of the row (first or second element)
        has_number_key = False
        number_val = None
        for item in group[:2]:
            if re.match(r'^\d{1,3}$', item[2]):
                has_number_key = True
                number_val = item[2]
                break
                
        if not has_number_key:
            continue
            
        # Parse fields based on coordinate splits inside the BOM region
        row_min_x = min(item[0] for item in group)
        row_max_x = max(item[0] for item in group)
        row_w = row_max_x - row_min_x if row_max_x > row_min_x else 100.0
        
        row_data = {
            "NO": number_val,
            "QTY": "1"
        }
        
        # Proximity splits:
        if is_assembly:
            # Splits: [No: 0.0-0.1] [DWG: 0.1-0.55] [TITLE: 0.55-0.8] [QTY: 0.8-0.9] [REMARK: 0.9-1.0]
            dwg_vals = []
            title_vals = []
            qty_vals = []
            remark_vals = []
            for item in group:
                rel_x = (item[0] - row_min_x) / row_w if row_w > 0 else 0.0
                val = item[2]
                if val == number_val:
                    continue
                if rel_x < 0.50:
                    dwg_vals.append(val)
                elif rel_x < 0.82:
                    title_vals.append(val)
                elif rel_x < 0.92:
                    qty_vals.append(val)
                else:
                    remark_vals.append(val)
            
            row_data.update({
                "DWG_NO": map_signature_value(" ".join(dwg_vals)),
                "TITLE": map_signature_value(" ".join(title_vals)),
                "QTY": map_signature_value(" ".join(qty_vals)) if qty_vals else "1",
                "REMARK": map_signature_value(" ".join(remark_vals)),
            })
        else:
            # Splits: [No: 0.0-0.1] [Code: 0.1-0.35] [Dim: 0.35-0.65] [QTY: 0.65-0.75] [MatWt: 0.75-0.84] [FinWt: 0.84-0.93] [Remark: 0.93-1.0]
            code_vals = []
            dim_vals = []
            qty_vals = []
            mat_vals = []
            fin_vals = []
            rem_vals = []
            for item in group:
                rel_x = (item[0] - row_min_x) / row_w if row_w > 0 else 0.0
                val = item[2]
                if val == number_val:
                    continue
                if rel_x < 0.32:
                    code_vals.append(val)
                elif rel_x < 0.64:
                    dim_vals.append(val)
                elif rel_x < 0.74:
                    qty_vals.append(val)
                elif rel_x < 0.84:
                    mat_vals.append(val)
                elif rel_x < 0.93:
                    fin_vals.append(val)
                else:
                    rem_vals.append(val)
                    
            row_data.update({
                "CODE": map_signature_value(" ".join(code_vals)),
                "DIMENSION": map_signature_value(" ".join(dim_vals)),
                "QTY": map_signature_value(" ".join(qty_vals)) if qty_vals else "1",
                "MATERIAL_WEIGHT": map_signature_value(" ".join(mat_vals)),
                "FINISHED_WEIGHT": map_signature_value(" ".join(fin_vals)),
                "REMARK": map_signature_value(" ".join(rem_vals)),
            })
            
        extracted_rows.append(row_data)

    return extracted_rows, is_assembly

def build_bom_table(ref_rows: list, rev_rows: list, is_assembly: bool) -> str:
    """Build dynamic ASCII BOM comparison table for all rows."""
    def get_val(row_dict, key):
        obj = row_dict.get(key, {})
        if isinstance(obj, dict):
            return obj.get("value", "NONE") or "NONE"
        return obj or "NONE"

    def is_blank_spacer(row):
        if not row:
            return True
        if is_assembly:
            dwg = get_val(row, "DWG_NO")
            title = get_val(row, "TITLE")
            return dwg == "NONE" and title == "NONE"
        else:
            code = get_val(row, "CODE")
            dim = get_val(row, "DIMENSION")
            return code == "NONE" and dim == "NONE"

    filtered_ref = [r for r in ref_rows if not is_blank_spacer(r)]
    filtered_rev = [r for r in rev_rows if not is_blank_spacer(r)]

    def get_row_key(row):
        no_val = get_val(row, "NO")
        if no_val == "NONE":
            return ""
        return no_val.strip()

    ref_map = {}
    for idx, r in enumerate(filtered_ref):
        k = get_row_key(r)
        if not k:
            k = f"_ref_idx_{idx}"
        ref_map[k] = r

    rev_map = {}
    for idx, r in enumerate(filtered_rev):
        k = get_row_key(r)
        if not k:
            k = f"_rev_idx_{idx}"
        rev_map[k] = r

    all_keys = list(set(ref_map.keys()).union(set(rev_map.keys())))
    
    def key_sort_fn(key_str):
        if key_str.startswith("_ref_idx_"):
            try:
                return (2, int(key_str.split("_")[-1]), key_str)
            except Exception:
                pass
        if key_str.startswith("_rev_idx_"):
            try:
                return (3, int(key_str.split("_")[-1]), key_str)
            except Exception:
                pass
        try:
            nums = re.findall(r'\d+', key_str)
            if nums:
                return (0, int(nums[0]), key_str)
        except Exception:
            pass
        return (1, 0, key_str)
    all_keys.sort(key=key_sort_fn)

    def cmp_status(orig, kmti, key_col):
        s = compare_values(orig, kmti)
        if s == "CHANGED" and key_col in ("MATERIAL_WEIGHT", "FINISHED_WEIGHT"):
            try:
                o_float = float(orig)
                k_float = float(kmti)
                if o_float == k_float and re.search(r'\.\d{2}$', kmti.strip()):
                    return "MATCHED"
            except ValueError:
                pass
        return "MATCHED" if s == "MATCHED" else "MISMATCHED"

    header = f"{'COLUMN':<32}| {'ORIGINAL':<20}| {'KMTI':<20}| MARKED"
    sep = '-' * len(header)
    lines = [header, sep]

    for key in all_keys:
        ref_row = ref_map.get(key, {})
        rev_row = rev_map.get(key, {})

        row_label = f"Unnumbered Row" if (key.startswith("_ref_idx_") or key.startswith("_rev_idx_")) else f"Item {key}"

        if is_assembly:
            cols = [
                ("No.",                  "NO"),
                ("図面番号 / DWG No.",   "DWG_NO"),
                ("名称 / TITLE",         "TITLE"),
                ("Q'ty",                "QTY"),
                ("備考 / Remark",        "REMARK"),
            ]
        else:
            cols = [
                ("No.",                          "NO"),
                ("材質 / Code",                  "CODE"),
                ("材料寸法/型式 / Dimension",     "DIMENSION"),
                ("材料個数 / Q'ty",              "QTY"),
                ("素材重量Kg / Material Wt(kg)", "MATERIAL_WEIGHT"),
                ("仕上重量Kg / Finished Wt(kg)", "FINISHED_WEIGHT"),
                ("備考 / Remark",                "REMARK"),
            ]

        for label, key_col in cols:
            orig = get_val(ref_row, key_col)
            kmti = get_val(rev_row, key_col)
            s = cmp_status(orig, kmti, key_col)
            full_label = f"[{row_label}] {label}"
            lines.append(f"{full_label:<32}| {orig:<20}| {kmti:<20}| {s}")

    return '\n'.join(lines)
