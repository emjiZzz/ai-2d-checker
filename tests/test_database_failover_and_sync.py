import asyncio
import os

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
async def test_database_sync_manager_status_is_reportable():
    """The diagnostics contract, which costs nothing to check."""
    status = sync_manager.get_status()
    assert "cloud_configured" in status
    assert "auto_sync_enabled" in status


@pytest.mark.skipif(
    os.getenv("RUN_LIVE_DB_SYNC") != "1",
    reason="writes to the real cloud database; set RUN_LIVE_DB_SYNC=1 to run it",
)
@pytest.mark.asyncio
async def test_database_sync_manager_execution():
    """A REAL sync between the configured databases. Opt-in, because it MUTATES them.

    This used to run on every `pytest`, upserting every synced collection into the cloud
    database as a side effect of running the suite. That is not a test cost anyone opted into,
    and it is not recoverable from if the sync is wrong.

    It also fails for a reason that is real and is NOT in the code: the live collections hold
    more than one `in_progress` session for the same (room, ref, rev, annotator), which the
    partial unique index `one_in_progress_session_per_pair_per_annotator` refuses on insert
    (`E11000`). `tools/merge_duplicate_check_sessions.py` exists for exactly that and has to be
    run against every environment, including Atlas — these collections are not in
    `sync_manager.SYNC_COLLECTIONS`, so they exist only there. Until that is done, this test
    reports the data condition rather than a defect, which is why failing the whole suite on it
    was misleading.
    """
    status = sync_manager.get_status()
    res = await sync_manager.sync_all()
    assert res is not None
    if status["cloud_configured"]:
        assert res.get("success") is True, res.get("error")
        assert "collections" in res["data"]
