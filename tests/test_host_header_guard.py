"""The Host header guard is the boundary that keeps this sidecar loopback-only.

It regressed once by being written as a prefix match, which accepted `localhost.attacker.com` —
an attacker-registered domain pointed at 127.0.0.1 is the whole DNS-rebinding technique, and the
guard existed specifically to stop it. These tests pin the exact-match behaviour so the cheap
`startswith` form cannot come back.
"""
from types import SimpleNamespace

import pytest
from fastapi import status

from services.backend.main import ALLOWED_HOST_NAMES, _hostname_of, verify_host


@pytest.mark.parametrize("header, expected", [
    ("localhost", "localhost"),
    ("localhost:8080", "localhost"),
    ("LOCALHOST:8080", "localhost"),          # RFC 3986 says the host is case-insensitive
    ("127.0.0.1", "127.0.0.1"),
    ("127.0.0.1:8080", "127.0.0.1"),
    ("127.0.0.1:1420", "127.0.0.1"),          # a non-default SIDECAR_PORT must still pass
    ("  localhost:8080  ", "localhost"),
    ("[::1]:8080", "::1"),
    ("::1", "::1"),
])
def test_hostname_is_extracted_without_the_port(header, expected):
    assert _hostname_of(header) == expected


@pytest.mark.parametrize("header", [
    "localhost.attacker.com",
    "localhost.attacker.com:8080",
    "127.0.0.1.evil.com",
    "localhost-evil.com",
    "evil.com",
    "0.0.0.0:8080",
    "192.168.1.50:8080",
    "",
])
def test_spoofed_hosts_do_not_resolve_to_an_allowed_name(header):
    assert _hostname_of(header) not in ALLOWED_HOST_NAMES


def _request(host_header):
    return SimpleNamespace(headers={"host": host_header})


async def _reached(_request_):
    return "handler ran"


@pytest.mark.asyncio
async def test_rebinding_host_is_rejected_with_403():
    response = await verify_host(_request("localhost.attacker.com"), _reached)
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
@pytest.mark.parametrize("header", ["localhost:8080", "127.0.0.1:8080", "LOCALHOST", "[::1]:8080"])
async def test_loopback_hosts_reach_the_handler(header):
    assert await verify_host(_request(header), _reached) == "handler ran"


def test_guard_does_not_use_a_prefix_match():
    """A direct assertion on the defect itself.

    `startswith`/`in` against the allowlist is the shape that failed. If someone reintroduces it,
    the parametrized cases above catch it — but this states the invariant in one line so the
    reason survives even if those cases are edited.
    """
    for allowed in ALLOWED_HOST_NAMES:
        assert _hostname_of(f"{allowed}.attacker.com") not in ALLOWED_HOST_NAMES
