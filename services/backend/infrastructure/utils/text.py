import re
import unicodedata
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


# ---------------------------------------------------------------------------
# Shift-JIS trail bytes that collide with MTEXT markup
#
# A DXF is read byte-preserving (`ezdxf.readfile(..., encoding="latin-1")`) so that
# `dxf_parser.transcode_value` can later recover real Shift-JIS text. Everything that runs
# before that pass -- including this module, via `entity_mapper` -- therefore sees raw CP932
# bytes, one per character.
#
# CP932 allows a trail byte in 0x40-0x7E or 0x80-0xFC. That range contains 0x5C, 0x7B, 0x7D
# and 0x7E: backslash and braces, exactly the characters MTEXT uses for markup. Stripping
# markup on the byte string therefore mutilates any character whose second byte happens to be
# one of them -- the classic Shift-JIS "dame-moji" / 5C problem.
#
# Measured on real customer drawings, in the entities as *stored*:
#     素材調質施工    ->  素材調質詩H       (施 = 0x8E 0x7B; the 0x7B was stripped as `{`)
#     イソナイト施工  ->  イャiイト詩H      (ソ = 0x83 0x5C; the backslash-escape rule then
#                                            also consumed the following byte)
#
# This is not cosmetic. `ZONE_ANCHORS["tolerance"]` contains 表示外公差, and 表 is 0x95 0x5C,
# so that anchor could never match the text actually stored -- a contributor to the tolerance
# zone's measured instability.
#
# Only these four trail bytes need protecting; 0x25 ('%', for the %%c codes) is not a legal
# CP932 trail byte, so the symbol replacements are already safe.
_SJIS_DANGEROUS_TRAIL = frozenset({0x5C, 0x7B, 0x7D, 0x7E})  # \ { } ~
_PUA_BASE = 0xE000
_PUA_CAPACITY = 0xF8FF - 0xE000


def _mask_sjis_markup_collisions(t: str) -> tuple[str, list[str]]:
    """Replace CP932 characters whose trail byte looks like MTEXT markup with placeholders.

    Returns `(masked_text, originals)`. Each masked character gets its OWN placeholder from
    the Unicode private-use area, so that a placeholder removed by the cleaning (e.g. one
    sitting inside a stripped font-change group) cannot shift the restoration of the others.

    Whether we are looking at raw bytes or at real Unicode is detected rather than passed in:
    a byte-preserving string is latin-1 encodable by construction, and post-transcode text
    containing real Japanese is not. So callers that run after `transcode_value`
    (`zone_detector`, `table_extractor`, `context_builder`) transparently skip all of this --
    they have no raw trail bytes to protect.
    """
    try:
        raw = t.encode('latin-1')
    except (UnicodeEncodeError, AttributeError):
        return t, []

    out: list[str] = []
    saved: list[str] = []
    i, n = 0, len(raw)
    while i < n:
        b = raw[i]
        is_lead = 0x81 <= b <= 0x9F or 0xE0 <= b <= 0xFC
        if is_lead and i + 1 < n:
            trail = raw[i + 1]
            if 0x40 <= trail <= 0x7E or 0x80 <= trail <= 0xFC:
                pair = raw[i:i + 2].decode('latin-1')
                if trail in _SJIS_DANGEROUS_TRAIL:
                    if len(saved) >= _PUA_CAPACITY:
                        return t, []          # absurd for a CAD text field; bail unmasked
                    out.append(chr(_PUA_BASE + len(saved)))
                    saved.append(pair)
                else:
                    out.append(pair)
                i += 2
                continue
        out.append(chr(b))
        i += 1

    return ''.join(out), saved


def _unmask_sjis(t: str, saved: list[str]) -> str:
    if not saved:
        return t
    for index, pair in enumerate(saved):
        t = t.replace(chr(_PUA_BASE + index), pair)
    return t


def strip_mtext(t: Any, convert_symbols: bool = True) -> str:
    """
    Canonical CAD text cleanup, used everywhere a text/dimension/tolerance/
    multileader/block-attribute entity's raw content is extracted so every
    entity type goes through the same single normalization pass instead of
    several divergent partial ones (previously: entity_mapper.py's MTEXT
    cleaner never converted %% control codes; map_tolerance/map_multileader
    applied no cleaning at all; this file's own version didn't decode bytes
    or handle every escape form). Consolidates:
      - raw bytes decoding (legacy cp932-encoded Japanese DXF text)
      - legacy "%%x" control codes -> their visual symbol (%%c -> Ø, %%d -> °,
        %%p -> ±; %%u/%%o are underline/overline toggles with no symbol, dropped) --
        gated by `convert_symbols` (see below)
      - \\P paragraph breaks -> space (these are single-value CAD fields, not
        multi-paragraph prose, so a literal embedded newline is not useful)
      - \\~ non-breaking space -> space
      - MTEXT formatting codes (\\W0.8;, \\H2.5;, \\Sstacked/fraction;, etc.) and
        {...} font/color change groups
      - any remaining single backslash escape, keeping the escaped character

    `convert_symbols=False` is REQUIRED when this is called during CAD entity
    extraction (entity_mapper.py), before dxf_parser.py's transcode_value() pass
    runs. That pass re-encodes every string to latin-1 bytes and re-decodes as
    cp932 to recover real Shift-JIS text from a byte-preserving raw file read --
    it assumes every string it sees still represents raw untouched bytes. "Ø"
    (U+00D8) encodes to latin-1 byte 0xD8, which decodes under cp932 as the
    Unicode replacement character (0xD8 falls in cp932's single-byte halfwidth-
    katakana territory) -- introducing a *real* Unicode symbol before that pass
    runs corrupts it into "�", which Gemini then hallucinates into a stray
    katakana character when reasoning about the image. Downstream callers that
    run at comparison/runtime (zone_detector, table_extractor, context_builder),
    reading text that was already safely stored post-transcode, should keep the
    default (True) so raw "%%c"-style codes still resolve to their real symbol.
    """
    if not t:
        return t if isinstance(t, str) else ""

    if isinstance(t, bytes):
        for enc in ('utf-8', 'cp932', 'latin-1'):
            try:
                t = t.decode(enc)
                break
            except (UnicodeDecodeError, AttributeError):
                continue
        else:
            t = t.decode('utf-8', errors='replace')

    # Protect CP932 characters whose trail byte is `\`, `{`, `}` or `~` before ANY markup
    # handling runs -- including the \P replacement immediately below, since `\P` is
    # 0x5C 0x50 and that 0x5C can be the second half of a kanji.
    t, _sjis_masked = _mask_sjis_markup_collisions(t)

    # Replace AutoCAD paragraph breaks with spaces before stripping formatting
    t = t.replace('\\P', ' ')
    # Non-breaking space
    t = t.replace('\\~', ' ')
    if convert_symbols:
        # Replace common AutoCAD symbol codes with their visual equivalents so AI vision matches entity text
        t = t.replace('%%c', 'Ø').replace('%%C', 'Ø')
        t = t.replace('%%d', '°').replace('%%D', '°')
        t = t.replace('%%p', '±').replace('%%P', '±')
        # Underline/overline toggles have no visual symbol -- just drop them
        t = t.replace('%%u', '').replace('%%U', '').replace('%%o', '').replace('%%O', '')
    # Strip MTEXT formatting codes: \X...; (width, height, alignment, tracking,
    # stacked fractions, font/color, etc. -- any backslash-letter code up to its
    # terminating semicolon, regardless of what characters the argument contains)
    t = re.sub(r'\\[A-Za-z][^;]*;', '', t)
    # Strip curly-brace groups for font/color changes
    t = t.replace('{', '').replace('}', '')
    # Strip any remaining single backslash escapes, keeping the escaped character
    t = re.sub(r'\\(.)', r'\1', t)
    return _unmask_sjis(t.strip(), _sjis_masked)


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


# Title-block fields that are SEGMENTS of the drawing number rather than fields in their own
# right, mapped to WHERE in the number each one sits. The DWG No. cell is ruled into sub-cells
# and each carries its own header, so the extractor reported the parts alongside the whole: on
# `M745203N01` the sheet labels `M745` as Machine Type / Mach. code, `203` as Unit No. / Unit
# Code and `N01` as Part No. Four checklist items for one identifier, three of which cannot
# change without the fourth changing too.
#
# The position is what makes the corroboration safe. A plain "is it a substring" test matches
# across segment boundaries — `45` is inside `M745`203N01 without being a segment of anything —
# and this codebase has already shipped one green tick that way (a `Previous Dwg. No.` of `1`
# corroborated against the `1` in `M7452A1N01`; see the ruled-cell-boundary gotcha).
#
# !! These keys are the BOTTOM title block's fields only. The UPPER-LEFT metadata table has its
# own `Unit No.` and `Part No.` columns which are STANDALONE FIELDS, not segments of anything,
# and they keep their own checklist items. Do not point this rule at them: on the live KEMCO
# sheet the UL `Part No.` reads `203`, which really is the middle segment of `M745203N01`, so
# the containment test would call it corroborated and delete a real field. The two are kept
# apart structurally — the UL rows are built by extract_title_ul_kv into the separate
# `title_ul_table` (tagged `zone: 'title_upper_left'`) and never reach this function.
# Pinned by tests/test_dwg_no_component_rows.py.
COMPONENT_OF_DWG_NO_FIELDS = {
    "MACHINE CODE": "prefix",
    "UNIT NO": "infix",
    "PART NO": "suffix",
}


def _norm_component(value: str) -> str:
    """Fold a component or drawing number for segment testing."""
    if not value:
        return ""
    t = unicodedata.normalize("NFKC", str(value)).upper()
    return re.sub(r"[\s\-/.]", "", t)


def is_component_of_dwg_no(value: str, dwg_no: str, position: str = "infix") -> bool:
    """True when `value` is accounted for by `dwg_no` and needs no checklist item of its own.

    A blank/NONE component is trivially accounted for — there is nothing to report. A populated
    one has to actually sit at its expected position in the drawing number: this is the
    difference between *asserting* that these fields are segments of the DWG No. and checking it.

    The check is load-bearing rather than decorative. Suppressing a component unconditionally
    would mean that on any sheet where the DWG No. fails to extract — which it does; the live
    KEMCO revision reads NONE — a changed segment would be reported by nothing at all. This
    project's largest known measurement gap is that false negatives have never been measured
    (see the vault's gap analysis), so the default is to keep a row that cannot be *shown*
    redundant.

    `infix` is the weakest of the three and deliberately so: it demands only that the value sit
    strictly inside the number, since the middle segment has no anchor of its own. In this
    corpus only MACHINE CODE (`prefix`) is ever populated by the spatial extractor, so the tight
    cases are the ones that fire.
    """
    v = _norm_component(value)
    if not v or v == "NONE":
        return True
    d = _norm_component(dwg_no)
    if not d or d == "NONE":
        return False
    if position == "prefix":
        return d.startswith(v)
    if position == "suffix":
        return d.endswith(v)
    start = d.find(v)
    return start > 0 and (start + len(v)) < len(d)


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

    rows = [
        "| FIELD NAME                      | ORIGINAL (Reference) | KMTI (Revision) | STATUS |",
        "|---------------------------------|----------------------|-----------------|--------|",
        f"| QTY (Quantity)                  | {f_qty_ref} | {f_qty_rev} | {status(f_qty_ref, f_qty_rev)} |",
        f"| STOCK QTY (Stock Qty)           | {f_stock_ref} | {f_stock_rev} | {status(f_stock_ref, f_stock_rev)} |",
        f"| DRAWN (Drawn By)                | {f_drawn_ref} | {f_drawn_rev} | {status(f_drawn_ref, f_drawn_rev)} |",
        f"| DESIGNED (Designed By)          | {f_designed_ref} | {f_designed_rev} | {status(f_designed_ref, f_designed_rev)} |",
        f"| SCALE (Sheet Scale)             | {f_scale_ref} | {f_scale_rev} | {status(f_scale_ref, f_scale_rev)} |",
        f"| TITLE (Drawing Title)           | {f_title_ref} | {f_title_rev} | {status(f_title_ref, f_title_rev)} |",
        f"| JOB NO (Job Number)             | {f_job_ref} | {f_job_rev} | {status(f_job_ref, f_job_rev)} |",
        f"| DWG NO (Drawing Number)         | {f_dwg_ref} | {f_dwg_rev} | {status(f_dwg_ref, f_dwg_rev)} |",
    ]

    # Machine Type/Code, Unit No./Unit Code and Part No. are SEGMENTS of the drawing number, not
    # independent fields — `M745203N01` is `M745` + `203` + `N01`, each in its own ruled sub-cell
    # under the DWG No. header. Reporting them beside the DWG No. put four checklist items on the
    # side panel for one identifier, and three of them cannot change without the DWG No. changing
    # too. They are dropped once the DWG No. is shown to account for them; a component the DWG No.
    # does NOT account for keeps its row, because then it is carrying information the DWG No. is
    # not. See is_component_of_dwg_no.
    component_rows = (
        ("MACHINE CODE", "| MACHINE CODE / UNIT CODE        |", f_mach_ref, f_mach_rev),
        ("UNIT NO",      "| UNIT NO (Unit Number)           |", f_unit_ref, f_unit_rev),
        ("PART NO",      "| PART NO (Part Number)           |", f_part_ref, f_part_rev),
    )
    for field_key, label, ref_val, rev_val in component_rows:
        at = COMPONENT_OF_DWG_NO_FIELDS[field_key]
        if is_component_of_dwg_no(ref_val, f_dwg_ref, at) and is_component_of_dwg_no(rev_val, f_dwg_rev, at):
            continue
        rows.append(f"{label} {ref_val} | {rev_val} | {status(ref_val, rev_val)} |")

    return "\n".join(rows) + "\n"
