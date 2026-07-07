import re
from typing import Any

def safe_decode(text: Any) -> str:
    if not text:
        return ""
    text_str = str(text)
    # If text already contains valid Japanese, return as-is to avoid Mojibake
    if re.search(r'[\u4e00-\u9faf\u3040-\u309f\u30a0-\u30ff]', text_str):
        return text_str
    try:
        b = text_str.encode('latin1')
        dec = b.decode('cp932')
        return dec
    except Exception:
        try:
            b = text_str.encode('utf-8')
            dec = b.decode('cp932')
            if re.search(r'[\u4e00-\u9faf\u3040-\u309f\u30a0-\u30ff]', dec):
                return dec
            return text_str
        except Exception:
            return text_str


def strip_mtext(t: str) -> str:
    # Replace AutoCAD newlines (\P) with standard newlines before stripping formatting
    t = t.replace('\\P', '\n')
    return re.sub(r'\\[A-Za-z0-9\-~|.]+;', '', t.replace('{', '').replace('}', '')).strip()


def compare_values(orig_val: str, kmti_val: str) -> str:
    """Compare two cell or block values and classify: MATCHED, ADDED, CHANGED, or REMOVED."""
    o = (orig_val or "NONE").strip()
    k = (kmti_val or "NONE").strip()
    
    if o == k:
        return "MATCHED"

    # Strict scale/format check: e.g. 1:2 vs 1/2 must be CHANGED
    if (":" in o and "/" in k) or ("/" in o and ":" in k):
        return "CHANGED"
        
    def normalize(val: str) -> str:
        if not val or val == "NONE":
            return ""
        v = val.lower().strip()
        # Treat lowercase x, uppercase X, × multiplication symbol, CP932 decoded 'ラ', and fullwidth 'ｘ', 'Ｘ' identically
        v = re.sub(r'[xX×ラｘＸ]', 'x', v)
        # Treat colons : and slashes / identically
        v = re.sub(r':', '/', v)
        # Treat all dashes, hyphens, and minus variants identically as a standard ASCII hyphen
        v = re.sub(r'[－−–—―〜～]', '-', v)
        # Strip all internal spaces to prevent mismatch due to spacing
        v = re.sub(r'\s+', '', v)
        return v
        
    norm_o = normalize(o)
    norm_k = normalize(k)
    
    if norm_o == norm_k:
        return "MATCHED"
        
    # ADDED Marker rule
    if (not norm_o or norm_o == "") and (norm_k and norm_k != ""):
        return "ADDED"
        
    # REMOVED Marker rule
    if (norm_o and norm_o != "") and (not norm_k or norm_k == ""):
        return "REMOVED"
        
    return "CHANGED"


def extract_semantic_text_groups(entities: list, prefix: str = "") -> dict:
    geometry_annotations = []
    notes_zone_text = []
    bom_zone_text = []
    title_block_data = []
    isometric_view_data = []
    
    # Pre-scan for structural label coordinates (Unit No, Part No, etc.) to securely bypass their values
    structural_coords = []
    tolerance_coords = []
    for e in entities:
        if e.entity_type == "text":
            raw_txt = e.properties.get("text")
            if raw_txt:
                txt_val = strip_mtext(safe_decode(str(raw_txt)))
                txt_lower = txt_val.lower()
                # Structural block scan
                if any(kw in txt_lower for kw in ["unit no", "ユニットno", "part no", "コードno", "stock q'ty", "総製作個数", "t. q'ty", "共通番号"]):
                    ins = e.geometry.get("insert")
                    if ins and len(ins) >= 2:
                        structural_coords.append((ins[0], ins[1]))
                # Tolerance table scan
                txt_no_space = txt_lower.replace(" ", "")
                if any(kw in txt_no_space for kw in ["表示外公差", "仕上げ記号", "機械加工", "板金加工", "寸法区分"]) or \
                   ("100s" in txt_lower and "50s" in txt_lower) or \
                   ("1005" in txt_lower and "505" in txt_lower) or \
                   ("25s" in txt_lower and "12.5s" in txt_lower) or \
                   ("255" in txt_lower and "12.55" in txt_lower) or \
                   re.search(r'^\d+\.?\d*\s*[~〜～\-`\?]\s*\d+\.?\d*$', txt_val) or \
                   re.search(r'^\d+\.?\d*[sS]\s*[~〜～\-`\?]\s*\d+\.?\d*[sS]$', txt_val) or \
                   re.search(r'^}\s*\d+\.?\d*$', txt_val):
                    ins = e.geometry.get("insert")
                    if ins and len(ins) >= 2:
                        tolerance_coords.append((ins[0], ins[1]))
                        
    min_x, min_y = float('inf'), float('inf')
    max_x, max_y = float('-inf'), float('-inf')
    for e in entities:
        if e.entity_type == "text" and e.geometry:
            ins = e.geometry.get("insert")
            if ins and len(ins) >= 2:
                min_x = min(min_x, ins[0])
                max_x = max(max_x, ins[0])
                min_y = min(min_y, ins[1])
                max_y = max(max_y, ins[1])
                
    width = max_x - min_x if max_x > min_x else 1000.0
    height = max_y - min_y if max_y > min_y else 1000.0
    dx_margin = width * 0.04
    dy_margin = height * 0.04
    
    for e in entities:
        if e.entity_type not in ("text", "dimension", "tolerance", "leader", "multileader", "attrib", "insert", "block") or not e.geometry:
            continue
            
        raw_txt = e.properties.get("text")
        if e.entity_type == "block" and not raw_txt:
            attrs = e.properties.get("attributes", {})
            if attrs:
                raw_txt = " ".join(str(v) for v in attrs.values() if v)
                
        if raw_txt is None:
            continue
            
        text_val = strip_mtext(safe_decode(str(raw_txt)))
        if not text_val:
            continue
            
        layer_lower = e.layer.lower() if e.layer else ""
        text_lower = text_val.lower().strip()

        # Hard Filter 1: Strip Outer Border grid markers mathematically
        is_outer_border = False
        ins = e.geometry.get("insert")
        if ins and len(ins) >= 2:
            is_outer_border = (
                ins[0] <= min_x + dx_margin or ins[0] >= max_x - dx_margin or
                ins[1] <= min_y + dy_margin or ins[1] >= max_y - dy_margin
            )
            
        if len(text_val) <= 2 and is_outer_border:
            continue
            
        # Hard Filter 2: Strip Column Headers and Category Labels robustly
        norm_txt = text_lower.replace(" ", "").replace("　", "").replace("’", "'").replace(":", "/")
        column_headers = {
            "no.", "no", "code", "dimension", "q'ty", "remark", "title", "dwgno.", "dwgno", 
            "材質", "寸法", "個数", "重量", "備考", "名称", "図面番号", "材料寸法", "材料個数", "素材重量", "仕上重量",
            "material", "weight", "qty", "unitcode", "unit/total", "t.q'ty", "stockq'ty",
            "drawn", "製図", "approved", "承認", "checked", "照査", "designed", "設計",
            "scale", "尺度", "jobno.", "工事番号", "mach.code", "unitno.", "partno.", "型式",
            "材質/code", "材料寸法/型式/dimension", "材料個数/q'ty", "素材重量kg/materialwt(kg)", 
            "仕上重量kg/finishedwt(kg)", "備考/remark", "図面番号/dwgno.", "名称/title"
        }
        if norm_txt in column_headers:
            continue

        # Check if coordinates overlap with known tolerance table bounds
        ins = e.geometry.get("insert")
        if ins and len(ins) >= 2:
            is_in_tolerance = False
            for tx, ty in tolerance_coords:
                if abs(ins[0] - tx) < width * 0.15 and abs(ins[1] - ty) < height * 0.15:
                    is_in_tolerance = True
                    break
            if is_in_tolerance:
                continue

        # Check if coordinates overlap with known structural label coordinates
        if ins and len(ins) >= 2:
            is_structural = False
            for sx, sy in structural_coords:
                if abs(ins[0] - sx) < width * 0.05 and abs(ins[1] - sy) < height * 0.03:
                    is_structural = True
                    break
            if is_structural:
                continue

        # Check if the text is one of the structural labels
        is_structural_label = any(kw in text_lower for kw in ["unit no", "ユニットno", "part no", "コードno", "stock q'ty", "在庫棚入庫", "t. q'ty", "総製作個数"])
        
        # Spatial check: if this text is physically near any of the structural labels, it's a metadata value.
        is_structural_value = False
        is_tolerance_value = False
        ins = e.geometry.get("insert")
        if ins and len(ins) >= 2:
            for cx, cy in structural_coords:
                if abs(ins[1] - cy) < max(100.0, height * 0.05):
                    if abs(ins[0] - cx) < max(1500.0, width * 0.6):
                        is_structural_value = True
                        break
                        
            # Tolerance table spatial filter
            for cx, cy in tolerance_coords:
                if abs(ins[0] - cx) < max(500.0, width * 0.15) and abs(ins[1] - cy) < max(450.0, height * 0.20):
                    if len(text_val) < 15 and (re.search(r'^\d+(\.\d+)?$', text_val) or "s" in text_lower or "~" in text_val or "〜" in text_val or "-" in text_val or "5" in text_val or "0" in text_val):
                        is_tolerance_value = True
                        break
        
        if is_structural_label or is_structural_value or is_tolerance_value:
            continue

        # 1. Title Block Data
        is_title = (
            "title" in layer_lower or "header" in layer_lower or "border" in layer_lower or 
            "stamp" in layer_lower or "admin" in layer_lower or "block" in layer_lower or 
            "logo" in layer_lower or "dwg" in layer_lower or "rev" in layer_lower or "qty" in layer_lower or
            "date" in layer_lower or "approved" in layer_lower or "checked" in layer_lower or
            "scale" in layer_lower or
            "approved" in text_lower or "checked" in text_lower or "designed" in text_lower or
            "drawn" in text_lower or "scale" in text_lower or "dwg no" in text_lower or
            "job no" in text_lower or "cross ref" in text_lower or "prev" in text_lower or
            any(kw in text_val for kw in ["日下部", "設計", "製図", "尺度", "図番", "図名", "品名", "年月日", "日付", "共通番号", "機番", "計画図", "総製作個数", "個数", "T. Q'ty", "T. Q’ty", "ユニットNo.", "Unit No.", "コードNo.", "Part No."]) or
            re.search(r'\b(?:REV|revision)\.?\s*([A-Z0-9]+)\b', text_val, re.IGNORECASE) or
            re.search(r'^\d{4}/\d{2}/\d{2}$', text_val) or
            re.search(r'^\d{4}-\d{1,2}-\d{1,2}$', text_val) or
            (("title" in layer_lower or "header" in layer_lower or "border" in layer_lower or "admin" in layer_lower or "stamp" in layer_lower or "block" in layer_lower) and 
             (re.search(r'^[A-Z0-9_-]+$', text_val) or re.search(r'^\d+(\.\d+)?$', text_val)))
        )
        if "在庫棚入庫" in text_val or "stock q'ty" in text_lower or "stock" in text_lower:
            is_title = True
        if is_title:
            title_block_data.append(text_val)
            continue
            
        # 2. BOM Zone Text
        is_bom = (
            "bom" in layer_lower or "bill" in layer_lower or "material" in layer_lower or 
            "table" in layer_lower or "parts" in layer_lower or "qty" in layer_lower or "legend" in layer_lower or
            "weight" in text_lower or "material" in text_lower or "qty" in text_lower or
            "fin.wt" in text_lower or "finished weight" in text_lower or "remark" in text_lower or
            "ss400" in text_lower or "sus304" in text_lower or "s235jr" in text_lower or
            "s355jr" in text_lower or "a6061" in text_lower or "alumin" in text_lower or
            "unit no." in text_lower or "part no." in text_lower or
            any(kw in text_val for kw in ["材質", "寸法", "型式", "素材重量", "仕上重量", "備考", "単／全", "コードNo.", "ユニットNo."]) or
            re.search(r'\b(?:qty|qt|quantity)\b', text_lower) or
            re.search(r'\b\d+\s*(?:[xX\*×]|\u00d7)\s*\d+\s*(?:[xX\*×]|\u00d7)\s*\d+\b', text_val) or
            (("bom" in layer_lower or "bill" in layer_lower or "table" in layer_lower or "parts" in layer_lower or "material" in layer_lower) and 
             (re.search(r'^\d+(\.\d+)?$', text_val) or text_val in ["-", "—", "トオシ", "通シ"]))
        )
        if is_bom:
            bom_zone_text.append(text_val)
            continue
  
        # 3. Geometry Annotations
        is_geom = (
            "dim" in layer_lower or "dimension" in layer_lower or "callout" in layer_lower or 
            "geometry" in layer_lower or "anno" in layer_lower or
            "キリ" in text_val or "トオシ" in text_val or "通シ" in text_val or 
            "深サ" in text_val or "ザグリ" in text_val or "面取" in text_val or "抜キ" in text_val or
            re.search(r'^\d+-\d+キリ', text_val) or
            re.search(r'^\d+X\d+-M\d+', text_val) or
            re.search(r'^M\d+', text_val) or
            re.search(r'^\d+-\d+-[A-Z]', text_val)
        )
        
        handle = e.properties.get("handle", "UNK") if e.properties else "UNK"
        id_str = f"{prefix}-{handle}" if prefix else handle
        ins = e.geometry.get("insert") or e.geometry.get("location") or e.geometry.get("text_point") or [0, 0]
        formatted_txt = f"[ID: {id_str}, X: {int(ins[0])}, Y: {int(ins[1])}] {text_val}"

        if is_geom:
            geometry_annotations.append(formatted_txt)
            continue
        # 4. Isometric View Data
        is_iso = (
            "iso" in layer_lower or "isometric" in layer_lower or "3d" in layer_lower or
            "アイソメ" in text_val or "等角" in text_val
        )
        if is_iso:
            isometric_view_data.append(formatted_txt)
            continue
  
        # 5. Notes Zone Text
        is_note = (
            "note" in layer_lower or "rule" in layer_lower or "instruction" in layer_lower or
            "text" in layer_lower or
            re.search(r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF]', text_val)
        )
        is_tolerance_row = re.search(r'^\d+\.?\d*\s*~\s*\d+\.?\d*$', text_val) or re.search(r'^±\s*\d+\.?\d*$', text_val)
        
        if is_note and not is_tolerance_row:
            notes_zone_text.append(formatted_txt)
            continue
  
        if re.search(r'^\d+(\.\d+)?$', text_val) or layer_lower in ["0", "defpoints"]:
            geometry_annotations.append(formatted_txt)
        else:
            notes_zone_text.append(formatted_txt)
            
    return {
        "geometry_annotations": "\n".join(geometry_annotations),
        "notes_zone_text": "\n".join(notes_zone_text),
        "bom_zone_text": "\n".join(bom_zone_text),
        "title_block_data": "\n".join(title_block_data),
        "isometric_view_data": "\n".join(isometric_view_data),
    }


def build_title_block_table(ref_fields: dict, rev_fields: dict) -> str:
    def status(orig: str, kmti: str) -> str:
        s = compare_values(orig, kmti)
        return 'MATCHED' if s == 'MATCHED' else 'MISMATCHED'

    def get_val(fields: dict, key: str) -> str:
        val_obj = fields.get(key, "NONE")
        if isinstance(val_obj, dict):
            val = val_obj.get("value", "NONE")
        else:
            val = val_obj
            
        val_str = str(val).strip()
        if val_str == "NONE":
            return val_str
            
        if key == 'DRAWN':
            val_str = re.sub(r'^(?:作\s*成|製\s*図|DRAWN)\s*:?\s*', '', val_str, flags=re.IGNORECASE).strip()
        elif key == 'DESIGNED':
            val_str = re.sub(r'^(?:設\s*計|DESIGNED)\s*:?\s*', '', val_str, flags=re.IGNORECASE).strip()
        elif key == 'JOB NO':
            val_str = re.sub(r'^(?:工\s*事\s*番\s*号|JOB\s*NO\.?)\s*:?\s*', '', val_str, flags=re.IGNORECASE).strip()
        elif key == 'MACHINE CODE':
            val_str = re.sub(r'^(?:機\s*器\s*/?\s*ユ\s*ニ\s*ッ\s*ト\s*記\s*号|機\s*器\s*記\s*号|ユ\s*ニ\s*ッ\s*ト\s*記\s*号|Mach\.?\s*code|Unit\s*Code)\s*:?\s*', '', val_str, flags=re.IGNORECASE).strip()
        elif key == 'DWG NO':
            val_str = re.sub(r'^(?:図\s*面\s*番\s*号|図\s*番|DWG\s*NO\.?)\s*:?\s*', '', val_str, flags=re.IGNORECASE).strip()
        elif key == 'UNIT NO':
            val_str = re.sub(r'^(?:ユ\s*ニ\s*ッ\s*ト\s*No\.?|Unit\s*No\.?)\s*:?\s*', '', val_str, flags=re.IGNORECASE).strip()
        elif key == 'PART NO':
            val_str = re.sub(r'^(?:パ\s*ー\s*ツ\s*No\.?|Part\s*No\.?)\s*:?\s*', '', val_str, flags=re.IGNORECASE).strip()
        elif key == 'SCALE':
            val_str = re.sub(r'^(?:尺\s*度|SCALE)\s*:?\s*', '', val_str, flags=re.IGNORECASE).strip()
        return val_str

    f_drawn_ref = get_val(ref_fields, 'DRAWN')
    f_drawn_rev = get_val(rev_fields, 'DRAWN')
    f_designed_ref = get_val(ref_fields, 'DESIGNED')
    f_designed_rev = get_val(rev_fields, 'DESIGNED')
    f_scale_ref = get_val(ref_fields, 'SCALE')
    f_scale_rev = get_val(rev_fields, 'SCALE')
    f_title_ref = get_val(ref_fields, 'TITLE')
    f_title_rev = get_val(rev_fields, 'TITLE')
    f_job_ref = get_val(ref_fields, 'JOB NO')
    f_job_rev = get_val(rev_fields, 'JOB NO')
    f_mach_ref = get_val(ref_fields, 'MACHINE CODE')
    f_mach_rev = get_val(rev_fields, 'MACHINE CODE')
    f_dwg_ref = get_val(ref_fields, 'DWG NO')
    f_dwg_rev = get_val(rev_fields, 'DWG NO')
    f_unit_ref = get_val(ref_fields, 'UNIT NO')
    f_unit_rev = get_val(rev_fields, 'UNIT NO')
    f_part_ref = get_val(ref_fields, 'PART NO')
    f_part_rev = get_val(rev_fields, 'PART NO')
    f_qty_ref = get_val(ref_fields, 'QTY')
    f_qty_rev = get_val(rev_fields, 'QTY')
    f_stock_ref = get_val(ref_fields, 'STOCK QTY')
    f_stock_rev = get_val(rev_fields, 'STOCK QTY')

    tbl = (
        "| FIELD NAME                      | ORIGINAL (Reference) | KMTI (Revision) | STATUS |\n"
        "|---------------------------------|----------------------|-----------------|--------|\n"
        f"| QTY (Quantity)                  | {f_qty_ref} | {f_qty_rev} | {status(f_qty_ref, f_qty_rev)} |\n"
        f"| STOCK QTY (Stock Qty)           | {f_stock_ref} | {f_stock_rev} | {status(f_stock_ref, f_stock_rev)} |\n"
        f"| DRAWN (Drawn By)                | {f_drawn_ref} | {f_drawn_rev} | {status(f_drawn_ref, f_drawn_rev)} |\n"
        f"| DESIGNED (Designed By)          | {f_designed_ref} | {f_designed_rev} | {status(f_designed_ref, f_designed_rev)} |\n"
        f"| SCALE (Sheet Scale)             | {f_scale_ref} | {f_scale_rev} | {status(f_scale_ref, f_scale_rev)} |\n"
        f"| TITLE (Drawing Title)           | {f_title_ref} | {f_title_rev} | {status(f_title_ref, f_title_rev)} |\n"
        f"| JOB NO (Job Number)             | {f_job_ref} | {f_job_rev} | {status(f_job_ref, f_job_rev)} |\n"
        f"| MACHINE CODE / UNIT CODE        | {f_mach_ref} | {f_mach_rev} | {status(f_mach_ref, f_mach_rev)} |\n"
        f"| DWG NO (Drawing Number)         | {f_dwg_ref} | {f_dwg_rev} | {status(f_dwg_ref, f_dwg_rev)} |\n"
        f"| UNIT NO (Unit Number)           | {f_unit_ref} | {f_unit_rev} | {status(f_unit_ref, f_unit_rev)} |\n"
        f"| PART NO (Part Number)           | {f_part_ref} | {f_part_rev} | {status(f_part_ref, f_part_rev)} |\n"
    )
    return tbl
