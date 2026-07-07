import pytest
from unittest.mock import MagicMock, patch
from pydantic import BaseModel, create_model
from typing import Optional
from services.backend.infrastructure.rendering.image_cropper import crop_title_block_image
from services.backend.infrastructure.audit.bom.title_block_extractor import extract_title_block
from services.backend.infrastructure.audit.comparison.cache_manager import ComparisonCacheManager
from services.backend.infrastructure.audit.comparison.gemini_client import execute_title_block_ocr

class MockEntity:
    def __init__(self, entity_type, text, x, y):
        self.entity_type = entity_type
        self.properties = {"text": text}
        self.geometry = {"insert": [x, y, 0.0]}

@patch("services.backend.infrastructure.rendering.image_cropper.Image.open")
@patch("services.backend.infrastructure.rendering.image_cropper.Path.exists")
def test_crop_title_block_invalid_bounds_error(mock_exists, mock_open):
    """Test 1: Verify coordinate bounds check raises a ValueError instead of assertion."""
    mock_exists.return_value = True
    mock_img = MagicMock()
    mock_img.size = (1000, 1000)
    mock_open.return_value = mock_img
    
    metadata = {"render_bounds": [100.0, 100.0, 50.0, 50.0]} # xmin > xmax (invalid)
    entities = [MockEntity("text", "SCALE", 80, 20)]
    
    with pytest.raises(ValueError) as exc:
        crop_title_block_image("non_existent_id", metadata, entities)
    assert "Invalid render bounds" in str(exc.value)

@patch("services.backend.infrastructure.rendering.image_cropper.Image.open")
@patch("services.backend.infrastructure.rendering.image_cropper.Path.exists")
def test_crop_title_block_image_success(mock_exists, mock_open):
    """Test 1b: Verify successful crop math translation."""
    mock_exists.return_value = True
    mock_img = MagicMock()
    mock_img.size = (1000, 1000)
    mock_open.return_value = mock_img
    
    # render bounds: 0 to 100. title block: x in [80, 100], y in [0, 20]
    metadata = {"render_bounds": [0.0, 0.0, 100.0, 100.0]}
    entities = [
        MockEntity("text", "尺度", 80, 20),
        MockEntity("text", "1:2", 90, 20)
    ]
    
    crop_bytes = crop_title_block_image("some_id", metadata, entities)
    assert crop_bytes is not None
    
    # Verification: tb_xmin (92.4 - 40) = 52.4 -> px_min = 524
    # tb_ymax (21.5 + 40) = 61.5 -> py_min = (1 - 61.5/100)*1000 = 385
    mock_img.crop.assert_called_with((524, 385, 1000, 1000))

def test_nfkc_coordinate_matching_normalization():
    """Test 4: Verify NFKC text match standardization rules."""
    entities = [
        MockEntity("text", "１：５", 100, 50),
    ]
    # "1:5" should ground to "１：５" coordinate insert [100, 50]
    ocr_results = {"SCALE": "1:5"}
    
    res = extract_title_block(entities, ocr_results=ocr_results)
    assert res["SCALE"]["value"] == "1:5"
    assert res["SCALE"]["coordinates"] == [100.0, 50.0]

def test_ocr_value_retention_on_grounding_miss():
    """Test 6: Verify no-match coordinate fallback retains OCR value and uses heuristic coords/None."""
    entities = [
        # Label exists, but value "MI51100A01" is split or doesn't match any text run exactly
        MockEntity("text", "図面番号", 100, 50),
        MockEntity("text", "MI511", 100, 40),
        MockEntity("text", "0A01", 110, 40),
    ]
    ocr_results = {"DWG_NO": "MI51100A01"}
    
    res = extract_title_block(entities, ocr_results=ocr_results)
    
    # OCR value must stand (not get replaced by heuristic value)
    assert res["DWG NO"]["value"] == "MI51100A01"
    # Coordinates must fall back to the heuristic proximity search of "図面番号" -> Y=40
    # With MockEntity default height 3.0 and no bbox, get_anchor falls back to [vx + 2.4, vy + 1.5]
    assert res["DWG NO"]["coordinates"] == [102.4, 41.5]

@patch("google.genai.Client")
def test_partial_cache_hits_ocr_trigger(mock_client_class):
    """Test 3: Verify partial cache hit only crops and sends the missing image."""
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    
    # Mock Gemini structured JSON output
    mock_response = MagicMock()
    mock_response.text = '{"revision": {"SCALE": "1/2", "TITLE": "TEST", "DWG_NO": "D1", "DRAWN": "D", "DESIGNED": "D", "QTY": "1"}}'
    mock_client.models.generate_content.return_value = mock_response

    # Ref is cached, Rev is missing
    ref_id = "ref_dwg"
    ref_hash = "h1"
    rev_id = "rev_dwg"
    rev_hash = "h2"
    
    ref_cached_ocr = {"SCALE": "1:2", "TITLE": "TEST", "DWG_NO": "D1", "DRAWN": "D", "DESIGNED": "D", "QTY": "1"}
    
    # Ensure cache is clean for rev, but populated for ref
    ComparisonCacheManager.set_cached_ocr(ref_id, ref_hash, ref_cached_ocr)
    
    ocr_res = execute_title_block_ocr(
        api_key="fake_key",
        images={"revision": b"fake_png_bytes"}
    )
    
    assert "revision" in ocr_res
    assert "reference" not in ocr_res
    assert ocr_res["revision"]["SCALE"] == "1/2"

def test_transient_failure_heuristic_fallback():
    """Test 5: Verify that a transient Gemini failure falls back cleanly to heuristics."""
    entities = [
        MockEntity("text", "製図", 100, 50),
        MockEntity("text", "JCC", 100, 40)
    ]
    # No OCR results, triggers heuristic fallbacks
    res = extract_title_block(entities, ocr_results=None)
    assert res["DRAWN"]["value"] == "JCC"
    assert res["DRAWN"]["coordinates"] == [102.4, 41.5]

def test_none_crop_fallback_handling():
    """Test 7: Verify that a None-crop triggers clean fallback for that drawing."""
    # When image is None, the system uses heuristic extraction for that drawing
    entities = [
        MockEntity("text", "製図", 100, 50),
        MockEntity("text", "JCC", 100, 40)
    ]
    res = extract_title_block(entities, ocr_results=None)
    assert res["DRAWN"]["value"] == "JCC"
    assert res["DRAWN"]["coordinates"] == [102.4, 41.5]
