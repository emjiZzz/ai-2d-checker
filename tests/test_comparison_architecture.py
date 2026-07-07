import pytest
import shutil
from pydantic import ValidationError
from services.backend.infrastructure.audit.comparison.schemas import Coordinate2D, BoundingBox2D
from services.backend.infrastructure.audit.comparison.cache_manager import ComparisonCacheManager
from services.backend.infrastructure.storage.path_resolver import get_storage_root

def test_coordinate_validation_success():
    """Verifies Coordinate2D correctly parses and converts coordinate arrays."""
    c = Coordinate2D.from_list([10.5, 20.7])
    assert c.x == 10.5
    assert c.y == 20.7
    assert c.to_list() == [10.5, 20.7]

def test_coordinate_validation_failure():
    """Verifies Coordinate2D raises ValidationError on malformed list structure."""
    with pytest.raises(ValueError):
        Coordinate2D.from_list([10.5])
    with pytest.raises(ValueError):
        Coordinate2D.from_list([10.5, 20.7, 30.9])

def test_bounding_box_validation_success():
    """Verifies BoundingBox2D correctly parses and converts bbox tuples/lists."""
    b = BoundingBox2D.from_tuple((5.0, 10.0, 15.0, 20.0))
    assert b.xmin == 5.0
    assert b.ymin == 10.0
    assert b.xmax == 15.0
    assert b.ymax == 20.0
    assert b.to_tuple() == (5.0, 10.0, 15.0, 20.0)

def test_bounding_box_validation_failure():
    """Verifies BoundingBox2D raises ValidationError on malformed box sizes."""
    with pytest.raises(ValueError):
        BoundingBox2D.from_tuple((5.0, 10.0, 15.0))
    with pytest.raises(ValueError):
        BoundingBox2D.from_tuple((5.0, 10.0, 15.0, 20.0, 25.0))

def test_cache_manager_flow():
    """Verifies comparison cache store, hit detection, and filesystem unlinking."""
    ref_id = "test_ref_dwg"
    rev_id = "test_rev_dwg"
    ref_hash = "hash_ref_123"
    rev_hash = "hash_rev_456"
    
    mock_payload = {
        "drawing_views": {"status": "MATCHED", "difference_summary": "No changes"},
        "notes_section": {"status": "MATCHED", "difference_summary": "No changes"},
        "bill_of_materials": {"status": "MATCHED", "difference_summary": "No changes"},
        "title_block": {"status": "MATCHED", "difference_summary": "No changes"},
        "isometric_view": {"status": "MATCHED", "difference_summary": "No changes"},
        "other_engineering_references": {"status": "MATCHED", "difference_summary": "No changes"},
        "canvas_markings": []
    }

    # Ensure clean state
    cache_file = ComparisonCacheManager._get_cache_path(ref_id, rev_id, ref_hash, rev_hash)
    if cache_file.exists():
        cache_file.unlink()

    # Cache should miss initially
    assert ComparisonCacheManager.get_cached_comparison(ref_id, rev_id, ref_hash, rev_hash) is None

    # Write cache payload
    ComparisonCacheManager.set_cached_comparison(ref_id, rev_id, ref_hash, rev_hash, mock_payload)
    assert cache_file.exists()

    # Cache should hit and match exactly
    hit_payload = ComparisonCacheManager.get_cached_comparison(ref_id, rev_id, ref_hash, rev_hash)
    assert hit_payload is not None
    assert hit_payload["drawing_views"]["difference_summary"] == "No changes"

    # Simulate invalidation (glob-unlink check as implemented in drawings.py)
    # drawings.py matches str(drawing.id) in f.name and unlinks
    cache_dir = get_storage_root() / "cache"
    for f in cache_dir.glob("gemini_comparison_*.json"):
        if ref_id in f.name:
            f.unlink()

    # File should be deleted and cache should miss again
    assert not cache_file.exists()
    assert ComparisonCacheManager.get_cached_comparison(ref_id, rev_id, ref_hash, rev_hash) is None

def test_compare_values_scale_mismatch():
    """Verifies that compare_values and marking injection treat 1:2 vs 1/2 as CHANGED with standardization details."""
    from services.backend.infrastructure.utils.text import compare_values
    from services.backend.infrastructure.audit.comparison.marking_builder import inject_title_block_markings
    
    # 1. Check compare_values level
    assert compare_values("1:2", "1/2") == "CHANGED"
    assert compare_values("1/2", "1:2") == "CHANGED"
    assert compare_values("1:2", "1:2") == "MATCHED"

    # 2. Check details string appending level
    clean_markings = []
    ref_title_fields = {"SCALE": {"value": "1:2", "coordinates": [0,0]}}
    rev_title_fields = {"SCALE": {"value": "1/2", "coordinates": [0,0]}}
    
    inject_title_block_markings(clean_markings, ref_title_fields, rev_title_fields, [], [])
    
    assert len(clean_markings) == 1
    m = clean_markings[0]
    assert m["status"] == "CHANGED"
    assert "Standardized based on Standard context provided" in m["details"]

