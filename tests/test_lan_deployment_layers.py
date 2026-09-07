"""A LAN deployment is two settings, and configuring one is the failure mode.

`SIDECAR_HOST=0.0.0.0` makes the backend listen on the network. The Host guard in `main.py` is a
separate layer that still defaults to loopback, so a server configured with only the first accepts
the TCP connection and answers every request with 403 "Standalone backend only accepts localhost
requests" -- which reads like a bind problem and is not one. Measured on 192.168.200.129 on
2026-09-07; see [[Gotcha - A LAN Server Bound to the Network and Refused It]].
"""
from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import status

from services.backend.main import ALLOWED_HOST_NAMES, verify_host

REPO = Path(__file__).resolve().parents[1]
TEMPLATE = REPO / "tools" / "scripts" / "server-service" / ".env.template"
LAN_HOST = "192.168.200.129"


def _request(host_header: str) -> SimpleNamespace:
    return SimpleNamespace(headers={"host": host_header})


async def _reached(_request_):
    return "handler ran"


@pytest.mark.asyncio
async def test_a_lan_host_is_refused_by_default():
    """The 403 the deployment actually hit. Binding wider does not move this boundary."""
    response = await verify_host(_request(f"{LAN_HOST}:8080"), _reached)
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert LAN_HOST not in ALLOWED_HOST_NAMES


@pytest.mark.asyncio
async def test_naming_the_host_in_allowed_hosts_admits_it(monkeypatch):
    """`verify_host` resolves the allowlist as a module global, so this patches what it reads."""
    monkeypatch.setattr(
        "services.backend.main.ALLOWED_HOST_NAMES", ALLOWED_HOST_NAMES | {LAN_HOST}
    )
    assert await verify_host(_request(f"{LAN_HOST}:8080"), _reached) == "handler ran"


@pytest.mark.asyncio
async def test_admitting_one_lan_host_does_not_admit_its_neighbours(monkeypatch):
    """Exact match still, or opening a LAN would reopen the rebinding hole."""
    monkeypatch.setattr(
        "services.backend.main.ALLOWED_HOST_NAMES", ALLOWED_HOST_NAMES | {LAN_HOST}
    )
    for spoof in (f"{LAN_HOST}.attacker.com:8080", "192.168.200.130:8080", "192.168.200.12:8080"):
        response = await verify_host(_request(spoof), _reached)
        assert response.status_code == status.HTTP_403_FORBIDDEN


def test_the_template_never_offers_a_wider_bind_without_the_guard():
    """The two live one line apart here because they were configured a week apart in production.

    Whoever deploys reads this file, not `main.py`; a template naming only the bind is how the
    403 gets rediscovered.
    """
    lines = TEMPLATE.read_text(encoding="utf-8").splitlines()
    binds_wide = [i for i, line in enumerate(lines) if re.match(r"^#?\s*SIDECAR_HOST=0\.0\.0\.0", line)]
    assert binds_wide, "the template no longer shows a LAN bind; check this test still applies"
    for i in binds_wide:
        nearby = "\n".join(lines[max(0, i - 20) : i + 6])
        assert "ALLOWED_HOSTS" in nearby, (
            "the template offers SIDECAR_HOST=0.0.0.0 without naming ALLOWED_HOSTS beside it. "
            "That combination is a server that listens on the LAN and 403s all of it."
        )
        assert "API_TOKEN" in nearby, (
            "a LAN bind with no API_TOKEN generates a token onto the server's own disk that no "
            "remote client can read: /health passes, every authenticated request 401s."
        )
