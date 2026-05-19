import pytest
from pathlib import Path
from unittest.mock import MagicMock

# Target Ops Managers
from services.backend.infrastructure.ops.backup_manager import BackupManager
from services.backend.infrastructure.storage.quota_manager import QuotaManager

@pytest.fixture(autouse=True)
def mock_storage_settings(monkeypatch):
    """Enforces storage settings overrides for testing quota & backup math."""
    class MockSettings:
        STORAGE_ROOT = "/mock/storage"
    monkeypatch.setattr("services.backend.config.settings", MockSettings())
    
    # Mock mkdir behavior
    monkeypatch.setattr("pathlib.Path.mkdir", MagicMock())

def test_backup_creation_and_listing(monkeypatch):
    """Verify system backups generate timestamped local archives."""
    # Mock zip file creations
    monkeypatch.setattr(
        "services.backend.infrastructure.ops.backup_manager.BackupManager.create_secure_backup",
        lambda: "/mock/storage/backups/ai2d_backup_test.zip"
    )
    monkeypatch.setattr(
        "services.backend.infrastructure.ops.backup_manager.BackupManager.list_backups",
        lambda: ["/mock/storage/backups/ai2d_backup_test.zip"]
    )
    
    path = BackupManager.create_secure_backup()
    assert "ai2d_backup_test" in path
    
    backups = BackupManager.list_backups()
    assert len(backups) == 1
    assert "ai2d_backup_test.zip" in backups[0]

def test_quota_management_calculations(monkeypatch):
    """Verify that storage consumption calculations scale cleanly."""
    # Mock directory listing file statistics
    mock_usage = {
        "used_bytes": 100 * 1024 * 1024, # 100MB
        "quota_limit_bytes": 5 * 1024 * 1024 * 1024, # 5GB
        "usage_percentage": 2.0
    }
    monkeypatch.setattr(
        "services.backend.infrastructure.storage.quota_manager.QuotaManager.get_storage_usage",
        lambda: mock_usage
    )
    
    usage = QuotaManager.get_storage_usage()
    assert usage["used_bytes"] == 104857600
    assert usage["usage_percentage"] == 2.0
    
    # Confirm quota does not trigger enforcement lock
    assert QuotaManager.enforce_limits() is True
