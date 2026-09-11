"""A Mongo socket with no timeout wedges the whole server, not just one request.

`serverSelectionTimeoutMS` bounds finding a server. It does not bound a read on a socket already
selected, and PyMongo defaults `socketTimeoutMS` to None -- wait forever. So an Atlas connection
that dies without a FIN (a dropped uplink, a NAT reap, a firewall idle-reap) leaves every handler
touching Mongo blocked permanently, `/health` included.

Measured on Server 3 on 2026-09-08: TCP connects, HTTP never answers, `Get-NetTCPConnection` shows
18 CLOSE_WAIT and 0 ESTABLISHED -- every peer had given up while the handlers stayed stuck. It did
not recover on its own. See [[Gotcha - A Dead Atlas Socket Wedged Every Request]].
"""
from __future__ import annotations

import ast
import asyncio
from pathlib import Path

import pytest

from services.backend.infrastructure.database import health as health_module
from services.backend.infrastructure.database.connection import (
    CONNECT_TIMEOUT_MS,
    SOCKET_TIMEOUT_MS,
)

CONNECTION_PY = (
    Path(__file__).resolve().parents[1]
    / "services" / "backend" / "infrastructure" / "database" / "connection.py"
)


def _client_call() -> ast.Call:
    tree = ast.parse(CONNECTION_PY.read_text(encoding="utf-8"))
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "AsyncIOMotorClient"
    ]
    assert len(calls) == 1, f"expected one client construction, found {len(calls)}"
    return calls[0]


def test_the_client_bounds_a_single_socket_operation():
    """The defect itself: without this keyword the read has no deadline at all."""
    kwargs = {kw.arg for kw in _client_call().keywords}
    assert "socketTimeoutMS" in kwargs, (
        "AsyncIOMotorClient is built without socketTimeoutMS, so a dead-but-open Atlas socket "
        "blocks every handler that touches Mongo forever."
    )
    assert "connectTimeoutMS" in kwargs


def test_server_selection_alone_is_not_treated_as_sufficient():
    """It was, and that is why the timeouts looked configured while the server hung."""
    kwargs = {kw.arg for kw in _client_call().keywords}
    assert "serverSelectionTimeoutMS" in kwargs
    assert kwargs & {"socketTimeoutMS"}, "serverSelectionTimeoutMS does not bound a socket read"


def test_the_bounds_are_finite_and_leave_room_for_a_real_query():
    for value in (CONNECT_TIMEOUT_MS, SOCKET_TIMEOUT_MS):
        assert isinstance(value, int) and value > 0
    assert SOCKET_TIMEOUT_MS >= 10_000, "too tight: a slow bulk insert would fail spuriously"
    assert SOCKET_TIMEOUT_MS <= 60_000, "too loose: this is the bound that stops a wedge"


class _HangingClient:
    """A client whose ping never returns — the dead-socket state, without needing a dead socket."""

    class _Admin:
        async def command(self, *_args, **_kwargs):
            await asyncio.sleep(3600)

    admin = _Admin()


@pytest.mark.asyncio
async def test_health_reports_degraded_instead_of_hanging(monkeypatch):
    """The endpoint the desktop client polls must always answer, or failover never fires."""
    monkeypatch.setattr(health_module.db_manager, "client", _HangingClient(), raising=False)
    monkeypatch.setattr(health_module.db_manager, "connected", True, raising=False)
    monkeypatch.setattr(health_module, "PING_TIMEOUT_SEC", 0.05)

    result = await asyncio.wait_for(health_module.check_database_health(), timeout=5)

    assert result["connected"] is False
    assert result["status"] == "degraded"
    assert "timed out" in result["error"]
