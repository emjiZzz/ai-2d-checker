import pytest
from pathlib import Path
from services.backend.infrastructure.cad.pdf_parser import PDFParser
from services.backend.infrastructure.cad.pdf_diff_engine import PDFDiffEngine
from services.backend.infrastructure.audit.report_generator import ReportGenerator

def test_pdf_parser_fallback_robustness(monkeypatch):
    """
    Validates that PDFParser returns clean structural layers and entity counts 
    even when running under fallback mechanisms.
    """
    import sys
    monkeypatch.setitem(sys.modules, "fitz", None)
    
    parser = PDFParser()
    temp_file = Path("dummy_blueprint.pdf")
    
    entities, layers, counts, metadata = parser.parse_file(temp_file)
    
    assert len(layers) == 3
    assert "PDF_Geometry" in [l["layer"] for l in layers]
    assert "PDF_Text" in [l["layer"] for l in layers]
    assert counts["line"] > 0
    assert counts["text"] > 0
    assert metadata["format"] == "pdf"


def test_pdf_diff_engine_color_rules():
    """
    Verifies that PDFDiffEngine applies the exact hexadecimal RGB color keys:
    - Crimson (#ef4444) for Deleted paths
    - Teal (#10b981) for Added paths
    - Charcoal (#27272a) for Unchanged paths
    """
    old_ents = [
        {
            "entity_type": "line",
            "layer": "PDF_Geometry",
            "properties": {"handle": "line_1"},
            "geometry": {"start": [10.0, 10.0, 0.0], "end": [20.0, 20.0, 0.0]}
        },
        {
            "entity_type": "line",
            "layer": "PDF_Geometry",
            "properties": {"handle": "line_2"},
            "geometry": {"start": [50.0, 50.0, 0.0], "end": [100.0, 100.0, 0.0]}
        }
    ]
    
    new_ents = [
        {
            "entity_type": "line",
            "layer": "PDF_Geometry",
            "properties": {"handle": "line_1"},
            "geometry": {"start": [10.0, 10.0, 0.0], "end": [20.0, 20.0, 0.0]} # Unchanged
        },
        {
            "entity_type": "line",
            "layer": "PDF_Geometry",
            "properties": {"handle": "line_3"},
            "geometry": {"start": [200.0, 200.0, 0.0], "end": [300.0, 300.0, 0.0]} # Added
        }
    ]
    
    diff = PDFDiffEngine.compare_documents(old_ents, new_ents)
    
    # 1. Unchanged = Charcoal (#27272a)
    assert len(diff["unchanged"]) == 1
    assert diff["unchanged"][0]["properties"]["stroke"] == "#27272a"
    
    # 2. Added = Teal (#10b981)
    assert len(diff["added"]) == 1
    assert diff["added"][0]["properties"]["stroke"] == "#10b981"
    
    # 3. Removed = Crimson (#ef4444)
    assert len(diff["removed"]) == 1
    assert diff["removed"][0]["properties"]["stroke"] == "#ef4444"

def test_report_generator_sanitization():
    """
    Asserts that filename sanitization blocks illegal path traversals and dot sequences.
    """
    unsafe_name_1 = "../../../unsafe_exec.bat"
    unsafe_name_2 = "drawing..sheet/draft.dwg"
    
    clean_1 = ReportGenerator._sanitize_filename(unsafe_name_1)
    clean_2 = ReportGenerator._sanitize_filename(unsafe_name_2)
    
    assert ".." not in clean_1
    assert "/" not in clean_1
    assert "unsafe_exec.bat" in clean_1 or "unsafe_exec_bat" in clean_1
    assert ".." not in clean_2
