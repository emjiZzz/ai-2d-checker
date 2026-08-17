import asyncio
import pytest
from services.backend.config import settings
from services.backend.infrastructure.database.connection import DatabaseConnectionManager
from services.backend.infrastructure.database.sync_manager import sync_manager


@pytest.mark.asyncio
async def test_database_connection_cloud_primary():
    """Test connecting to the configured primary database."""
    mgr = DatabaseConnectionManager()
    connected = await mgr.connect(max_retries=1, initial_delay=0.1)
    assert connected is True
    assert mgr.is_connected is True
    assert mgr.active_uri is not None
    assert mgr.db is not None
    await mgr.disconnect()
    assert mgr.is_connected is False


@pytest.mark.asyncio
async def test_database_connection_fallback_on_unreachable_primary(monkeypatch):
    """Test that an unreachable primary URI automatically falls back to local MongoDB."""
    # Set fake invalid primary URI
    fake_primary = "mongodb://127.0.0.1:59999"  # Non-existent port
    local_fallback = "mongodb://127.0.0.1:27017"

    monkeypatch.setattr(settings, "MONGO_URI", fake_primary)
    monkeypatch.setattr(settings, "MONGO_FALLBACK_URI", local_fallback)

    mgr = DatabaseConnectionManager()
    connected = await mgr.connect(max_retries=1, initial_delay=0.1)
    
    assert connected is True
    assert mgr.is_connected is True
    assert mgr.is_fallback is True
    assert mgr.active_uri == local_fallback
    await mgr.disconnect()


@pytest.mark.asyncio
async def test_database_sync_manager_status_and_execution():
    """Test the database sync manager diagnostics and sync execution."""
    status = sync_manager.get_status()
    assert "cloud_configured" in status
    assert "auto_sync_enabled" in status

    # Run sync execution
    res = await sync_manager.sync_all()
    assert res is not None
    if status["cloud_configured"]:
        assert res.get("success") is True
        assert "collections" in res["data"]
