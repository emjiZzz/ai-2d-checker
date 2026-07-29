import pytest
from pathlib import Path
from infrastructure.knowledge.vault_sync import VaultSyncManager

def test_vault_sync_manager_initialization():
    """Verify VaultSyncManager resolves repo root and vault path correctly."""
    sync_mgr = VaultSyncManager.get_instance()
    assert sync_mgr.vault_path is not None
    assert isinstance(sync_mgr.vault_path, Path)

def test_vault_sync_loads_live_rules():
    """Verify load_live_rules extracts tolerance keywords and surface roughness patterns."""
    sync_mgr = VaultSyncManager.get_instance()
    rules = sync_mgr.load_live_rules(force_reload=True)
    
    assert "tolerance_keywords" in rules
    assert "surface_roughness_patterns" in rules
    assert "upper_left_anchors" in rules

    # Verify Japanese tolerance keywords extracted from vault / defaults
    keywords = rules["tolerance_keywords"]
    assert "指示外公差" in keywords or "指示無き公差" in keywords
    assert "機械加工" in keywords or "製造加工" in keywords

    # Verify surface roughness patterns
    patterns = rules["surface_roughness_patterns"]
    assert len(patterns) > 0

def test_vault_sync_upper_left_anchors():
    """Verify upper left anchor keywords include map and part no."""
    sync_mgr = VaultSyncManager.get_instance()
    anchors = sync_mgr.get_upper_left_anchors()
    assert "map" in anchors
    assert "unit no" in anchors or "unit no." in anchors
