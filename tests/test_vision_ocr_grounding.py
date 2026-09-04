import pytest
import uuid
from unittest.mock import MagicMock, patch
from pydantic import BaseModel, create_model
from typing import Optional

from services.backend.domain.models.drawing_document import DrawingDocument
from services.backend.domain.models.extracted_entity import ExtractedEntity
from services.backend.domain.models.audit_session import AuditSession
from services.backend.domain.models.audit_violation import AuditViolation
from services.backend.domain.models.client import ClientDocument
from services.backend.domain.models.standard_document import StandardDocument
from services.backend.domain.models.standard_chunk import StandardChunk

from services.backend.infrastructure.rendering.image_cropper import crop_title_block_image
from services.backend.infrastructure.audit.bom.title_block_extractor import extract_title_block
from services.backend.infrastructure.audit.comparison.cache_manager import ComparisonCacheManager
from services.backend.infrastructure.audit.comparison.gemini_client import execute_title_block_ocr

# Setup autouse beanie model mocking to prevent db dependency crashes
@pytest.fixture(autouse=True)
def mock_beanie_docs(monkeypatch):
    monkeypatch.setattr(DrawingDocument, "get_pymongo_collection", classmethod(lambda cls: MagicMock()))
    monkeypatch.setattr(ExtractedEntity, "get_pymongo_collection", classmethod(lambda cls: MagicMock()))
    monkeypatch.setattr(AuditSession, "get_pymongo_collection", classmethod(lambda cls: MagicMock()))
    monkeypatch.setattr(AuditViolation, "get_pymongo_collection", classmethod(lambda cls: MagicMock()))
    monkeypatch.setattr(ClientDocument, "get_pymongo_collection", classmethod(lambda cls: MagicMock()))
    monkeypatch.setattr(StandardDocument, "get_pymongo_collection", classmethod(lambda cls: MagicMock()))
    monkeypatch.setattr(StandardChunk, "get_pymongo_collection", classmethod(lambda cls: MagicMock()))

    class MockField:
        def __init__(self, name):
            self.name = name
        def __eq__(self, other):
            return True

    ExtractedEntity.drawing_id = MockField("drawing_id")
    AuditViolation.audit_session_id = MockField("audit_session_id")

class MockEntity:
    """A stand-in for `ExtractedEntity`, kept attribute-compatible with it.

    It previously carried only entity_type/properties/geometry, so any pipeline code reading a
    field the real document defines — `extract_semantic_text_groups` reads `.layer` — blew up with
    AttributeError inside the code under test. The defaults below mirror
    `domain/models/extracted_entity.py` field-for-field; when that model gains a field, this
    should gain it too, otherwise these tests drift back out of contact with production shape.
    """

    def __init__(self, entity_type, text, x, y, geometry=None, layer="0", handle=None,
                 parent_handle=None, space="model", viewport_index=-1):
        self.entity_type = entity_type
        self.layer = layer
        self.handle = handle
        self.parent_handle = parent_handle
        self.space = space
        self.viewport_index = viewport_index
        self.properties = {"text": text}
        self.geometry = geometry if geometry is not None else {"insert": [x, y, 0.0]}

@pytest.fixture
def ref_drawing():
    dwg = DrawingDocument(
        file_name="ref.dxf",
        file_path="uploads/ref.dxf",
        file_hash="ref_hash",
        file_size_bytes=100,
        format="dxf",
        status="completed",
        metadata={"render_bounds": [0, 0, 100, 100]}
    )
    dwg.id = "ref_dwg_id"
    return dwg

@pytest.fixture
def rev_drawing():
    dwg = DrawingDocument(
        file_name="rev.dxf",
        file_path="uploads/rev.dxf",
        file_hash="rev_hash",
        file_size_bytes=100,
        format="dxf",
        status="completed",
        metadata={"render_bounds": [0, 0, 100, 100]}
    )
    dwg.id = "rev_dwg_id"
    return dwg

@pytest.fixture
def ref_entities():
    return [MockEntity("text", "SCALE", 80, 20), MockEntity("text", "1:2", 90, 20)]

@pytest.fixture
def rev_entities():
    return [MockEntity("text", "SCALE", 80, 20), MockEntity("text", "1:2", 90, 20)]

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
        # compute_title_block_bbox() now delegates to extract_dynamic_regions(), whose
        # sheet-bounds calculation (compute_drawing_bounds) only looks at line/polyline
        # geometry -- text-only fixtures produce no bounds signal at all and fall through
        # to a degenerate full-image crop. A border/frame polyline is what every real DXF
        # actually has, so include one here to exercise the real code path.
        MockEntity("polyline", None, 0, 0, geometry={"points": [[0, 0], [100, 0], [100, 100], [0, 100], [0, 0]]}),
        MockEntity("text", "尺度", 80, 20),
        MockEntity("text", "1:2", 90, 20)
    ]

    crop_bytes = crop_title_block_image("some_id", metadata, entities)
    assert crop_bytes is not None

    # With sheet bounds established, the "title" zone falls back to the percentage
    # grid (xMin 0.38-0.98, yMin 0.72-0.98 of the 0-100 sheet) since there's no
    # content-aware anchor phrase in this fixture -> CAD [38,72]-[98,98] -> pixels:
    mock_img.crop.assert_called_with((380, 20, 980, 280))

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
    # Coordinates must fall back to the heuristic proximity search of "図面番号" -> Y=40.
    # No bbox on MockEntity, so marker_anchor() estimates the text CENTRE from the insert:
    # x = 100 + len("MI511") * 3.0 * 0.6 / 2 = 104.5;  y = 40 + 3.0 / 2 = 41.5
    assert res["DWG NO"]["coordinates"] == [104.5, 41.5]

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
    
    try:
        # Ensure cache is clean for rev, but populated for ref
        ComparisonCacheManager.set_cached_ocr(ref_id, ref_hash, ref_cached_ocr)
        
        ocr_res = execute_title_block_ocr(
            api_key="fake_key",
            images={"revision": b"fake_png_bytes"}
        )
        
        assert "revision" in ocr_res
        assert "reference" not in ocr_res
        assert ocr_res["revision"]["SCALE"] == "1/2"
    finally:
        # Clean up the disk write to preserve test hygiene
        cache_file = ComparisonCacheManager._get_ocr_cache_path(ref_id, ref_hash)
        if cache_file.exists():
            cache_file.unlink()

# NOTE: these two tests used to also patch `orchestrator.execute_gemini_cascade` and feed it a
# canned six-category comparison JSON. ADR-006 deleted the LLM comparison path, so the orchestrator
# makes no cascade call at all and the patch target stopped existing — the tests failed at mock
# setup with AttributeError, never reaching an assertion. The fix is deletion, not retargeting:
# the mocked call is gone from the design. What both tests are actually about — title-block OCR
# degrading to heuristics — is still live at orchestrator.py:553 and is what they now exercise.
@patch("services.backend.infrastructure.audit.comparison.gemini_client.execute_title_block_ocr")
@patch("services.backend.infrastructure.rendering.image_cropper.crop_title_block_image")
@pytest.mark.asyncio
async def test_orchestrator_falls_back_on_gemini_ocr_failure(
    mock_crop, mock_ocr, ref_drawing, rev_drawing, ref_entities, rev_entities, monkeypatch
):
    """Test 5: Verify that a transient Gemini failure falls back cleanly to heuristics in orchestrator."""
    monkeypatch.setenv("GEMINI_API_KEY", "mock_key")

    mock_crop.return_value = b"fake_png_bytes"  # both sides "crop" fine
    mock_ocr.side_effect = Exception("503 UNAVAILABLE")

    from services.backend.infrastructure.audit.comparison.orchestrator import perform_drawing_comparison
    request = MagicMock(reference_drawing_id=str(ref_drawing.id), drawing_id=str(rev_drawing.id))

    # Should not raise — falls through to heuristic title_block_fields, comparison still completes
    result = await perform_drawing_comparison(request, ref_drawing, rev_drawing, ref_entities, rev_entities)
    assert result.title_block is not None
    # The fallback is only meaningful if OCR was actually attempted and threw. Without this the
    # test would still pass if OCR were skipped entirely, which is a different code path.
    assert mock_ocr.called

@patch("services.backend.infrastructure.audit.comparison.gemini_client.execute_title_block_ocr")
@patch("services.backend.infrastructure.rendering.image_cropper.crop_title_block_image")
@pytest.mark.asyncio
async def test_orchestrator_skips_ocr_when_crop_returns_none(
    mock_crop, mock_ocr, ref_drawing, rev_drawing, ref_entities, rev_entities, monkeypatch
):
    """Test 7: Verify that a None-crop skips OCR and falls back to heuristics for that drawing in orchestrator."""
    monkeypatch.setenv("GEMINI_API_KEY", "mock_key")

    mock_crop.return_value = None  # neither side has a usable rendering

    from services.backend.infrastructure.audit.comparison.orchestrator import perform_drawing_comparison
    request = MagicMock(reference_drawing_id=str(ref_drawing.id), drawing_id=str(rev_drawing.id))

    result = await perform_drawing_comparison(request, ref_drawing, rev_drawing, ref_entities, rev_entities)
    assert result.title_block is not None
    # The point of the test: missing_crops ends up empty, so no image is sent to Gemini. This
    # assertion is the test — previously it was only stated in a comment, so nothing checked it.
    mock_ocr.assert_not_called()
