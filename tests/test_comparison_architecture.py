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


class _FellThrough(Exception):
    """Sentinel: the cache-hit fast path was declined and a full comparison began."""


def _cached_payload(diagnostics: dict) -> dict:
    category = {"status": "MATCHED", "difference_summary": "No changes"}
    return {
        "drawing_views": category,
        "notes_section": category,
        "bill_of_materials": category,
        "title_block": category,
        "isometric_view": category,
        "other_engineering_references": category,
        "canvas_markings": [],
        "diagnostics": diagnostics,
    }


async def _serve_cached(monkeypatch, diagnostics: dict):
    from types import SimpleNamespace

    from services.backend.infrastructure.audit.comparison import orchestrator

    monkeypatch.setattr(
        orchestrator.ComparisonCacheManager,
        "get_cached_comparison",
        staticmethod(lambda **_: _cached_payload(diagnostics)),
    )
    monkeypatch.setattr(orchestrator, "apply_learned_adjustments", lambda resp, _a, _b: resp)

    async def _full_run(*_args, **_kwargs):
        raise _FellThrough()

    monkeypatch.setattr(orchestrator, "generate_deterministic_candidates", _full_run)

    drawing = SimpleNamespace(id="dwg", file_hash="hash")
    return await orchestrator.perform_drawing_comparison(
        SimpleNamespace(), drawing, drawing, [], []
    )


async def test_cache_hit_without_audit_session_id_reruns():
    """A cached entry carrying no `audit_session_id` must NOT be served.

    The AuditSession/AuditViolation writes live on the cache-MISS path only, so serving such
    an entry returns findings that exist nowhere in Mongo. The desktop checklist joins its
    markers to those documents to get a reviewable id (persistedViolations.ts), so the whole
    supervisor verdict control silently disappears — and re-testing cannot fix it, because the
    re-test hits the same entry. Every v43 entry on disk before 2026-08-10 was in this state.
    """
    with pytest.MonkeyPatch.context() as mp:
        with pytest.raises(_FellThrough):
            await _serve_cached(mp, {"zone_detection_warnings": []})


async def test_cache_hit_with_audit_session_id_is_served():
    """The fast path still exists — the guard above must not disable caching outright."""
    with pytest.MonkeyPatch.context() as mp:
        response = await _serve_cached(mp, {"audit_session_id": "6a7444aa62659080a5944ef5"})

    assert response.diagnostics.audit_session_id == "6a7444aa62659080a5944ef5"

