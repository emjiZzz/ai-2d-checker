import pytest
from services.backend.api.v1 import extract_bom_fields, extract_proximity_value

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

def test_extract_proximity_value_stacked_title():
    """
    Validates Fix B3: Stacked multi-row text grouping.
    Ensures that a title split across multiple horizontal lines is correctly gathered,
    sorted top-to-bottom (Y descending), and merged with a newline without hardcoded layers.
    """
    entities = [
        MockEntity("text", "名称 TITLE", 100, 50),
        # Stacked title strings below the label
        MockEntity("text", "水平ルーパー", 100, 40),
        MockEntity("text", "下プレート", 100, 30),
    ]
    
    merged_text, coords = extract_proximity_value(
        entities=entities,
        label_text="名称 TITLE",
        lx=100.0,
        ly=50.0,
        coord_scale=1.0,
        direction='below',
        dx_tol=30.0,
        dy_min=2.0,
        dy_tol=80.0
    )
    
    # The extraction should merge both strings with a newline
    assert merged_text == "水平ルーパー\n下プレート", f"Failed to group stacked text. Got: {merged_text}"
    
    # Ensure coordinates anchor to the top-most entity of the merged block
    # Using the bbox logic from the function: top entity is at Y=40, height=3, ymin=40, ymax=43
    # coords[1] = ymin + (ymax-ymin)/2.0 = 40 + 1.5 = 41.5
    assert coords[1] == 41.5, f"Incorrect geometric anchor for merged text. Got Y={coords[1]}"

def test_extract_bom_fields_shifted_matrix():
    """
    Validates Fix B2: Dynamic anchor-key BOM alignment.
    Ensures that BOM rows are grouped securely by the 'No.' column coordinates
    and perfectly map adjacent cells regardless of Y-axis spacer gaps or minor Y shifts.
    """
    entities = [
        # Table Headers
        MockEntity("text", "No.", 10, 200),
        MockEntity("text", "材質 / Code", 30, 200),
        MockEntity("text", "材料寸法/型式 / Dimension", 60, 200),
        
        # Row 1 (Item 1) - Perfect alignment
        MockEntity("text", "1", 10, 190),
        MockEntity("text", "SUS304", 30, 190),
        MockEntity("text", "t3.0x100x100", 60, 190),
        
        # Spacer/Noise Row (Empty or unrelated data)
        MockEntity("text", " ", 10, 180),
        MockEntity("text", "NOISE", 200, 180),
        
        # Row 2 (Item 2) - Shifted Y alignment simulating sloppy CAD text placement
        MockEntity("text", "2", 10, 170),
        MockEntity("text", "SS400", 30, 173), # Shifted UP by 3 units
        MockEntity("text", "L50x50x5", 60, 168), # Shifted DOWN by 2 units
        
        # Row 3 (Item 3)
        MockEntity("text", "3", 10, 150),
        MockEntity("text", "A5052", 30, 150),
        MockEntity("text", "t5.0x200x200", 60, 150),
    ]
    
    bom_rows, is_assembly = extract_bom_fields(entities)
    
    # We should only extract 3 valid data rows (the spacer/noise should be ignored)
    assert len(bom_rows) == 3, f"Expected 3 extracted rows, got {len(bom_rows)}"
    
    # Validate Row 1
    assert bom_rows[0]["NO"]["value"] == "1"
    assert bom_rows[0]["CODE"]["value"] == "sus304"
    assert bom_rows[0]["DIMENSION"]["value"] == "t3.0x100x100"
    
    # Validate Row 2 (Ensure it snapped the shifted cells to the "2" anchor)
    assert bom_rows[1]["NO"]["value"] == "2"
    assert bom_rows[1]["CODE"]["value"] == "ss400"
    assert bom_rows[1]["DIMENSION"]["value"] == "l50x50x5"
    
    # Validate Row 3
    assert bom_rows[2]["NO"]["value"] == "3"
    assert bom_rows[2]["CODE"]["value"] == "a5052"
    assert bom_rows[2]["DIMENSION"]["value"] == "t5.0x200x200"

def test_extract_bom_fields_ignores_hardcoded_layers():
    """
    Validates that the extraction algorithm operates entirely on spatial proximity
    and bounding boxes, ignoring legacy hardcoded 'BOM' layer names.
    """
    entities = [
        # Headers on a weird layer
        MockEntity("text", "No.", 10, 200, layer="RANDOM_LAYER_1"),
        MockEntity("text", "材質 / Code", 30, 200, layer="RANDOM_LAYER_2"),
        
        # Data on completely unassociated layers
        MockEntity("text", "99", 10, 190, layer="DIMENSIONS"),
        MockEntity("text", "ALUMINUM", 30, 190, layer="0"),
    ]
    
    bom_rows, is_assembly = extract_bom_fields(entities)
    
    assert len(bom_rows) == 1
    assert bom_rows[0]["NO"]["value"] == "99"
    assert bom_rows[0]["CODE"]["value"] == "aluminum"

def test_extract_title_fields_native_blocks():
    from services.backend.api.v1 import extract_title_fields
    
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
        # Add some random text that should be ignored since native block matches
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
