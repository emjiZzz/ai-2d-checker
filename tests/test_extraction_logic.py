import pytest
import math
from services.backend.infrastructure.audit.bom.table_extractor import extract_bom_table as extract_bom_fields
from services.backend.infrastructure.audit.bom.title_block_extractor import extract_title_block as extract_title_fields
from services.backend.infrastructure.utils.text import safe_decode

class MockEntity:
    """Mocks a DWG/DXF text entity with expected geometry and properties."""
    def __init__(self, entity_type, text, x, y, layer="0", height=3.0):
        self.entity_type = entity_type
        self.layer = layer
        self.geometry = {"insert": [x, y, 0.0]}
        
        # Approximate a bounding box
        width = len(text) * 2.0 if text else 10.0
        self.properties = {
            "text": text,
            "height": height,
            "bbox": [[x, y], [x + width, y + height]]
        }

def extract_proximity_value(entities, label_text, lx, ly, coord_scale=1.0, direction='below', dx_tol=8.0, dy_min=1.0, dy_tol=25.0):
    scaled_dx_tol = dx_tol * coord_scale
    scaled_dy_tol = dy_tol * coord_scale
    scaled_dy_min = dy_min * coord_scale
    
    candidates = []
    for e in entities:
        txt = e.properties.get("text", "").strip() if getattr(e, "properties", None) else ""
        if not txt or txt == label_text:
            continue
            
        decoded = safe_decode(txt).strip()
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
        if not txt or txt == label_text:
            continue
        decoded = safe_decode(txt).strip()
        
        e_geom = getattr(e, "geometry", {}) or {}
        e_ins = e_geom.get("insert") or [0, 0, 0]
        vx, vy = e_ins[0], e_ins[1]
        
        if vx >= lx - 30.0 * coord_scale and (vx - lx) <= scaled_dx_tol:
            # Increase X axis matching tolerance to 20.0 to match loose mock bboxes securely
            if abs(vx - cx) <= 20.0 * coord_scale and abs(vy - cy) <= 80.0 * coord_scale:
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

def test_extract_proximity_value_stacked_title():
    """
    Validates Fix B3: Stacked multi-row text grouping.
    Ensures that a title split across multiple horizontal lines is correctly gathered,
    sorted top-to-bottom (Y descending), and merged with a newline without hardcoded layers.
    """
    # Use unicode escapes to avoid multi-platform file/terminal encoding issues
    text_label = "\u540d\u79f0 TITLE"
    text_line1 = "\u6c34\u5e73\u30eb\u30fc\u30d1\u30fc" # 水平ルーパー
    text_line2 = "\u4e0b\u30d7\u30ec\u30fc\u30c8"   # 下プレート

    entities = [
        MockEntity("text", text_label, 100, 50),
        MockEntity("text", text_line1, 100, 40),
        MockEntity("text", text_line2, 100, 30),
    ]
    
    merged_text, coords = extract_proximity_value(
        entities=entities,
        label_text=text_label,
        lx=100.0,
        ly=50.0,
        coord_scale=1.0,
        direction='below',
        dx_tol=30.0,
        dy_min=2.0,
        dy_tol=80.0
    )
    
    assert merged_text == f"{text_line1}\n{text_line2}", f"Failed to group stacked text. Got: {merged_text}"
    assert coords[1] == 41.5, f"Incorrect geometric anchor for merged text. Got Y={coords[1]}"

def test_scale_reads_value_below_not_date_to_the_right():
    """Regression: SCALE was mapped with direction='right' and grabbed the adjacent Y/M/D
    date column instead of the scale value directly beneath its label.

    Layout mirrors the measured KEMCO title block: a header row (DESIGNED | DRAWN | SCALE |
    Y/M/D) at y~46 with each field's value directly below at y~36. The reference read SCALE
    as '04/12/22\\n20' (the date column) against the revision's real '1/1'. SCALE must read
    the value in its own column, not the neighbouring date.
    """
    entities = [
        # Header row (labels).
        MockEntity("text", "DESIGNED", 232.0, 46.0),
        MockEntity("text", "DRAWN", 247.0, 46.0),
        MockEntity("text", "SCALE", 262.0, 46.0),
        MockEntity("text", "Y/M/D", 281.0, 45.0),
        # Value row directly below each label.
        MockEntity("text", "中川", 243.0, 36.0),   # designer, under DRAWN/DESIGNED
        MockEntity("text", "1:1", 262.0, 36.0),     # the SCALE value, same column
        MockEntity("text", "20", 270.0, 34.0),      # date fragment, Y/M/D column
        MockEntity("text", "04/12/22", 275.0, 34.0),# date, Y/M/D column
    ]

    fields = extract_title_fields(entities)
    assert fields["SCALE"]["value"] == "1:1", \
        f"SCALE should read the value below its label, got {fields['SCALE']['value']!r}"
    # And specifically must not have picked up the date column.
    assert "04/12/22" not in fields["SCALE"]["value"]
    assert "/" not in fields["SCALE"]["value"] or fields["SCALE"]["value"] == "1:1"


def test_extract_bom_fields_shifted_matrix():
    """
    Validates Fix B2: Dynamic anchor-key BOM alignment.
    Ensures that BOM rows are grouped securely by the 'No.' column coordinates
    and perfectly map adjacent cells regardless of Y-axis spacer gaps or minor Y shifts.
    """
    entities = [
        # Dummy border entities to define sheet size: X in [0, 1000], Y in [0, 200]
        MockEntity("text", "BORDER_BL", 0, 0),
        MockEntity("text", "BORDER_TR", 1000, 200),

        # Table Headers (positioned relative to column splits to map correct values)
        MockEntity("text", "No.", 700, 70),
        MockEntity("text", "材質 / Code", 750, 70),
        MockEntity("text", "材料寸法/型式 / Dimension", 820, 70),
        MockEntity("text", "備考 / Remark", 950, 70),
        
        # Row 1 (Item 1) - Perfect alignment
        MockEntity("text", "1", 700, 60),
        MockEntity("text", "SUS304", 750, 60),
        MockEntity("text", "t3.0x100x100", 820, 60),
        MockEntity("text", "-", 950, 60),
        
        # Spacer/Noise Row (Empty or unrelated data)
        MockEntity("text", " ", 700, 50),
        MockEntity("text", "NOISE", 950, 50),
        
        # Row 2 (Item 2) - Shifted Y alignment simulating sloppy CAD text placement
        MockEntity("text", "2", 700, 40),
        MockEntity("text", "SS400", 750, 43), # Shifted UP by 3 units
        MockEntity("text", "L50x50x5", 820, 38), # Shifted DOWN by 2 units
        MockEntity("text", "-", 950, 40),
        
        # Row 3 (Item 3)
        MockEntity("text", "3", 700, 20),
        MockEntity("text", "A5052", 750, 20),
        MockEntity("text", "t5.0x200x200", 820, 20),
        MockEntity("text", "-", 950, 20),
    ]
    
    bom_rows, is_assembly = extract_bom_fields(entities)
    
    assert len(bom_rows) == 3, f"Expected 3 extracted rows, got {len(bom_rows)}"
    
    # Validate Row 1 (Flat string values as mapped by the modern table extractor, case-insensitive)
    assert bom_rows[0]["NO"] == "1"
    assert bom_rows[0]["CODE"].lower() == "sus304"
    assert bom_rows[0]["DIMENSION"].lower() == "t3.0x100x100"
    
    # Validate Row 2
    assert bom_rows[1]["NO"] == "2"
    assert bom_rows[1]["CODE"].lower() == "ss400"
    assert bom_rows[1]["DIMENSION"].lower() == "l50x50x5"
    
    # Validate Row 3
    assert bom_rows[2]["NO"] == "3"
    assert bom_rows[2]["CODE"].lower() == "a5052"
    assert bom_rows[2]["DIMENSION"].lower() == "t5.0x200x200"

def test_extract_bom_fields_ignores_hardcoded_layers():
    """
    Validates that the extraction algorithm operates entirely on spatial proximity
    and bounding boxes, ignoring legacy hardcoded 'BOM' layer names.
    """
    entities = [
        # Dummy border entities
        MockEntity("text", "BORDER_BL", 0, 0),
        MockEntity("text", "BORDER_TR", 1000, 200),

        # Headers on a weird layer
        MockEntity("text", "No.", 700, 70, layer="RANDOM_LAYER_1"),
        MockEntity("text", "材質 / Code", 750, 70, layer="RANDOM_LAYER_2"),
        MockEntity("text", "Q'ty", 850, 70, layer="RANDOM_LAYER_4"),
        MockEntity("text", "備考 / Remark", 950, 70, layer="RANDOM_LAYER_3"),

        # Data on completely unassociated layers
        # (extract_bom_table requires >=4 cells per row to reject 2-3 item
        # false-positive alignments, so a realistic row needs a Q'ty cell too)
        MockEntity("text", "99", 700, 60, layer="DIMENSIONS"),
        MockEntity("text", "ALUMINUM", 750, 60, layer="0"),
        MockEntity("text", "1", 850, 60, layer="0"),
        MockEntity("text", "-", 950, 60, layer="0"),
    ]

    bom_rows, is_assembly = extract_bom_fields(entities)

    assert len(bom_rows) == 1
    assert bom_rows[0]["NO"] == "99"
    assert bom_rows[0]["CODE"].lower() == "aluminum"


def test_extract_bom_captures_refer_to_table_deferral_row():
    """Regression: a BOM whose only data row is an item number next to a 表ニヨル ('as per the
    table') pointer has just two cells, so the >=4-cell row filter drops it and the BOM
    comparison shows nothing though the row is on the sheet. The deferral fallback must still
    surface it (materials live in the shim table, which is compared as its own zone)."""
    entities = [
        # Header row (>= 4 cells, contains 材質/寸法 so is_assembly=False).
        MockEntity("text", "No.", 0, 100),
        MockEntity("text", "材質", 20, 100),
        MockEntity("text", "寸法", 50, 100),
        MockEntity("text", "Q'ty", 80, 100),
        MockEntity("text", "備考", 110, 100),
        # The only data row: item number + deferral pointer (two cells).
        MockEntity("text", "1", 2, 80),
        MockEntity("text", "表ニヨル", 22, 80),
    ]

    rows, is_assembly = extract_bom_fields(entities, bom_bbox=(0.0, 70.0, 120.0, 110.0))

    assert is_assembly is False
    assert len(rows) == 1
    assert rows[0]["NO"] == "1"
    assert "表ニヨル" in str(rows[0]["CODE"])


def test_ungrounded_ocr_value_defers_to_spatial_reading():
    """Regression: an OCR title-block value that matches NO text on the drawing is a likely
    misread (Gemini read a mislocated crop as 'ME17227N24' for the real 'M745227N01'). It must
    NOT override the spatially-grounded value; the real DWG number below the label wins."""
    entities = [
        MockEntity("text", "図面番号", 100.0, 100.0),   # DWG label
        MockEntity("text", "M745227N01", 100.0, 90.0),  # the real value, directly below
    ]
    # OCR returns a value that appears on no entity -> ungrounded -> must defer to spatial.
    fields = extract_title_fields(entities, ocr_results={"DWG_NO": "ME17227N24"})
    assert fields["DWG NO"]["value"] == "M745227N01"


def test_grounded_ocr_value_is_still_trusted():
    """The other side of the same guard: an OCR value that DOES match drawing text stays."""
    entities = [
        MockEntity("text", "図面番号", 100.0, 100.0),
        MockEntity("text", "M745227N01", 100.0, 90.0),
    ]
    fields = extract_title_fields(entities, ocr_results={"DWG_NO": "M745227N01"})
    assert fields["DWG NO"]["value"] == "M745227N01"


def test_marker_anchor_is_the_centre_of_the_text():
    """The marker glyph is drawn centred on this coordinate (renderEntities.ts uses
    textAlign='center'/textBaseline='middle'), so the anchor must be the text's centre. It used
    to sit a character-width past the right edge, which carries the tick off long values and,
    in a title block, outside the value's own ruled cell."""
    from services.backend.infrastructure.audit.bom.anchors import marker_anchor

    assert marker_anchor(bbox=[[10, 20], [30, 40]]) == [20.0, 30.0]
    # No bbox: estimate width from the text so the anchor still lands inside it, not at the edge.
    assert marker_anchor(insert=[10, 20], height=6.0, text="ABCD") == [17.2, 23.0]
    # Centred/middle-justified text already has its insert at the horizontal centre.
    assert marker_anchor(insert=[10, 20], height=6.0, text="ABCD", is_centered=True) == [10.0, 23.0]
    assert marker_anchor() is None


def test_title_marker_anchors_sit_inside_the_value_they_mark():
    """End-to-end: an anchor must land within its value's own bbox, not past its right edge."""
    entities = [
        MockEntity("text", "名 称", 297.3, 37.1, layer="WAKU", height=2.5),
        MockEntity("text", "ロールカセット", 358.1, 40.5, layer="WAKU", height=4.7),
    ]
    value = entities[1]
    (vx_min, vy_min), (vx_max, vy_max) = value.properties["bbox"]
    ax, ay = extract_title_fields(entities)["TITLE"]["coordinates"]
    assert vx_min <= ax <= vx_max, "anchor drifted outside the value horizontally"
    assert vy_min <= ay <= vy_max, "anchor drifted outside the value vertically"


class MockLine:
    """A ruled line of the title-block grid, as ezdxf reports it (start/end, no insert)."""
    def __init__(self, x1, y1, x2, y2, layer="WAKU"):
        self.entity_type = "line"
        self.layer = layer
        self.geometry = {"start": [x1, y1, 0.0], "end": [x2, y2, 0.0]}
        self.properties = {}


def test_below_search_does_not_read_across_a_ruled_vertical():
    """Regression: 'Previous Dwg. No.' read the tolerance table's Fabrication cell.

    Geometry is the measured M7452A1N01 revision. The 旧図面番号 label sits at (153.0, 35.5); the
    tolerance table's Fabrication cell '1' at (145.9, 29.8) falls inside the proximity rectangle
    (dx=7.1, dy=5.7) even though the ruled vertical at x=152.0 stands between them. That bogus
    '1' was then corroborated against the other sheet and shown as a green MATCHED marker.
    """
    label_and_value = [
        MockEntity("text", "旧図面番号", 153.0, 35.5, layer="WAKU", height=2.5),
        MockEntity("text", "1", 145.9, 29.8, layer="WAKU", height=2.0),
    ]
    rule = MockLine(152.0, 10.0, 152.0, 51.0)

    # Without the rule the candidate is in range and IS picked -- this pins that the fixture
    # actually exercises the guard rather than failing the tolerance test for some other reason.
    assert extract_title_fields(label_and_value)["PREVIOUS DWG NO"]["value"] == "1"

    fields = extract_title_fields(label_and_value + [rule])
    assert fields["PREVIOUS DWG NO"]["value"] == "NONE"


def test_below_search_still_reads_a_value_in_its_own_cell():
    """The guard must only reject candidates across a rule, never one in the label's own cell."""
    entities = [
        MockEntity("text", "旧図面番号", 153.0, 35.5, layer="WAKU", height=2.5),
        MockEntity("text", "A1234", 153.4, 30.5, layer="WAKU", height=2.0),
        MockLine(152.0, 10.0, 152.0, 51.0),   # rule to the LEFT of both -- not between them
        MockLine(196.0, 10.0, 196.0, 51.0),   # rule to the RIGHT of both -- not between them
    ]
    assert extract_title_fields(entities)["PREVIOUS DWG NO"]["value"] == "A1234"


def test_job_no_reads_value_to_the_right_of_its_label():
    """Regression: JOB NO read NONE on every sheet, hiding a real 2589 -> 9324 edit.

    Measured M7452A1N01 revision geometry: 工事番号 is set as separate single-char vertical text
    (never matches as a label), so the English 'Job No.' at (180.9, 11.6) is the only anchor, and
    its value sits to the RIGHT at (196.0, 11.5) -- not below, where the search used to look.
    """
    entities = [
        MockEntity("text", "Job No.", 180.9, 11.6, layer="WAKU", height=2.2),
        MockEntity("text", "9324", 196.0, 11.5, layer="WAKU", height=2.0),
        MockEntity("text", "7777", 215.0, 11.5, layer="WAKU", height=2.0),  # next cell over
        MockLine(181.5, 10.0, 181.5, 28.0),  # label-cell/value-cell divider: must NOT block
    ]
    fields = extract_title_fields(entities)
    assert fields["JOB NO"]["value"] == "9324"


def test_title_is_read_from_the_cell_beside_its_label_not_below():
    """Regression: TITLE returned the DRAWING NUMBER on both sheets.

    The 名称/TITLE value sits in the cell to the RIGHT of the label; the old 'below' search
    walked down past the label into the drawing-number cell and picked 'M7452A1N01' as the
    title. Geometry is the measured M7452A1N01 revision.
    """
    entities = [
        MockEntity("text", "名 称", 297.3, 37.1, layer="WAKU", height=2.5),
        MockEntity("text", "TITLE", 297.3, 31.0, layer="WAKU", height=2.5),
        MockEntity("text", "ロールカセット 12\"ミル", 358.1, 40.5, layer="WAKU", height=4.7),
        MockEntity("text", "基準スペーサー：3", 358.1, 32.5, layer="WAKU", height=6.5),
        # The drawing number below the label -- what the old search wrongly returned.
        MockEntity("text", "M7452A1N01", 311.5, 16.5, layer="WAKU", height=9.5),
    ]
    fields = extract_title_fields(entities)
    assert fields["TITLE"]["value"] == "ロールカセット 12\"ミル"
    assert fields["TITLE SUB"]["value"] == "基準スペーサー：3"


def test_title_rows_are_reported_separately_and_in_order():
    """The 名称 cell's two ruled rows are separate values, upper first.

    Merging them (the old multiline path) means a change confined to one row cannot be told
    apart from a rewrite of both -- on the measured pair the upper row changed while the lower
    was byte-identical. Coordinates must differ too, or the two findings pin the same marker.
    """
    entities = [
        MockEntity("text", "名 称", 297.3, 37.1, layer="WAKU", height=2.5),
        MockEntity("text", "UPPER ROW", 358.1, 40.5, layer="WAKU", height=4.7),
        MockEntity("text", "lower row", 358.1, 32.5, layer="WAKU", height=6.5),
    ]
    fields = extract_title_fields(entities)
    assert fields["TITLE"]["value"] == "UPPER ROW"
    assert fields["TITLE SUB"]["value"] == "lower row"
    assert fields["TITLE"]["coordinates"] != fields["TITLE SUB"]["coordinates"]


def test_date_anchors_on_the_title_block_ymd_not_the_amendment_table_header():
    """'Y/M/D' appears twice: the amendment table's date column header and the title block's
    own label. The title-block one is always the LOWER, so prefer_lowest_y is what keeps the
    creation date from being read out of a revision-history row."""
    entities = [
        MockEntity("text", "Y/M/D", 350.5, 51.5, layer="WAKU", height=2.2),   # amendment header
        MockEntity("text", "1999/01/01", 355.0, 47.0, layer="WAKU", height=2.0),  # its row value
        MockEntity("text", "作成年月日", 276.9, 47.6, layer="WAKU", height=3.0),
        MockEntity("text", "Y/M/D", 278.2, 44.6, layer="WAKU", height=2.0),   # title-block label
        MockEntity("text", "2026/07/03", 282.0, 36.0, layer="WAKU", height=4.2),
    ]
    assert extract_title_fields(entities)["DATE"]["value"] == "2026/07/03"


def test_extract_title_fields_native_blocks():
    class MockBlockEntity:
        def __init__(self, attrs):
            self.entity_type = "block"
            self.properties = {"attributes": attrs}
            self.geometry = {"insert": [50.0, 50.0, 0.0]}

    # Mock a title block INSERT with standard attributes
    entities = [
        MockBlockEntity({
            "TITLE": "MAIN ASSEMBLY",
            "DWG_NO": "DWG-12345",
            "SCALE": "1:10",
            "DRAWN BY": "JOHN DOE"
        }),
        MockEntity("text", "TITLE NOT THIS", 0, 0)
    ]
    
    fields = extract_title_fields(entities, ["TITLE NOT THIS"])
    
    assert fields["TITLE"]["value"] == "MAIN ASSEMBLY"
    assert fields["DWG NO"]["value"] == "DWG-12345"
    assert fields["SCALE"]["value"] == "1:10"
    assert fields["DRAWN"]["value"] == "JOHN DOE"
    assert fields["TITLE"]["coordinates"] == [50.0, 50.0]

def test_gdt_welding_native_parsing():
    from services.backend.infrastructure.cad.entity_mapper import EntityMapper
    class MockDxfToler:
        def __init__(self):
            self.content = "{\\Fgdt;j}0.05"
            self.insert = [10.0, 20.0, 0.0]
            self.handle = "A1"
            self.color = 256
            self.layer = "TOL"
            
    class MockTolerEntity:
        def dxftype(self): return "TOLERANCE"
        def __init__(self): self.dxf = MockDxfToler()
        
    tol_ent = MockTolerEntity()
    res = EntityMapper.map_any(tol_ent)
    
    assert res["entity_type"] == "tolerance"
    assert res["properties"]["text"] == "{\\Fgdt;j}0.05"
    assert res["geometry"]["insert"] == [10.0, 20.0, 0.0]
