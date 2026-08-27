"""The per-user token directory is declared in three languages and must not drift.

An installed desktop client cannot find `<repo>/storage`, so the backend publishes the API token
to a per-user application-data directory and the Tauri shell reads it back from there. Nothing
type-checks across that boundary: Python computes the path, Rust computes it again, and
`tauri.conf.json` declares the identifier a third time.

⚠ **The failure mode is the expensive kind.** If the two sides disagree, everything works in
development -- where `<repo>/storage` is found first and this path is never used -- and an
installed build silently 401s on every authenticated request while `/health` still returns 200,
so the app reports itself CONNECTED. That is exactly the bug this mechanism was added to fix, and
a drift here recreates it.

Same reasoning as `tests/test_taxonomy_consistency.py`: where a rule cannot be shared, pin the
duplication with a test that parses both sides.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pytest

from services.backend.core.security import APP_IDENTIFIER, TOKEN_DIR_NAME, user_storage_root

REPO_ROOT = Path(__file__).resolve().parents[1]
RUST_SECURITY = REPO_ROOT / "apps" / "desktop" / "src-tauri" / "src" / "security" / "mod.rs"
TAURI_CONF = REPO_ROOT / "apps" / "desktop" / "src-tauri" / "tauri.conf.json"


def _rust_source() -> str:
    assert RUST_SECURITY.is_file(), f"missing {RUST_SECURITY}"
    return RUST_SECURITY.read_text(encoding="utf-8")


def test_the_rust_side_declares_the_same_token_directory() -> None:
    match = re.search(
        r'const\s+TOKEN_DIR_NAME:\s*&str\s*=\s*"([^"]+)"', _rust_source()
    )
    assert match, "no TOKEN_DIR_NAME constant found in the Rust security module"
    assert match.group(1) == TOKEN_DIR_NAME


def test_the_token_directory_is_NOT_the_tauri_identifier() -> None:
    """🔴 The regression that cost a shipped build.

    The token directory used to BE the bundle identifier. That is the desktop app's own data
    directory -- WebView2 keeps its profile there and the uninstaller deletes it -- so an
    uninstall/reinstall removed the published credential, and since it was only written at backend
    startup nothing restored it. From the access log on 2026-08-27: `POST /api/v1/rooms` and
    `GET /api/v1/rooms` both 401 at 05:16 on a freshly reinstalled build, healthy again at 05:18
    only because a diagnostic happened to re-run token initialisation.

    Asserting inequality looks odd until you have paid for the equality once.
    """
    conf = json.loads(TAURI_CONF.read_text(encoding="utf-8"))
    identifier = conf.get("identifier")

    assert identifier == APP_IDENTIFIER, "the recorded bundle identifier has drifted from tauri.conf.json"
    assert TOKEN_DIR_NAME != identifier, (
        "the token directory is the app's own data directory again -- an uninstall will delete "
        "the credential and every authenticated request will 401 until the backend restarts"
    )

    source = _rust_source()
    assert f'"{identifier}"' not in source, (
        "the Rust side still joins a path from the bundle identifier"
    )


def test_the_rust_side_resolves_a_user_data_root_at_all() -> None:
    """A `find_storage_root` with no per-user branch is the pre-fix code, and it 401s once installed."""
    source = _rust_source()
    assert "fn user_app_data_root" in source
    assert "user_app_data_root()" in source, (
        "user_app_data_root is defined but never consulted by find_storage_root -- "
        "which is the same as not having it"
    )


def test_both_sides_prefer_local_app_data_over_roaming_on_windows() -> None:
    """LOCALAPPDATA first, in both implementations.

    The token is encrypted under a machine-derived key, so a roaming profile would sync a
    credential to machines where it cannot decrypt. Cost with no benefit, and it looks like it
    should work -- worth pinning rather than commenting.
    """
    source = _rust_source()
    local_at = source.find("LOCALAPPDATA")
    roaming_at = source.find('env::var("APPDATA")')
    assert local_at != -1, "the Rust side never consults LOCALAPPDATA"
    assert roaming_at == -1 or local_at < roaming_at, (
        "APPDATA is consulted before LOCALAPPDATA; a machine-bound key must not roam"
    )


@pytest.mark.skipif(os.name != "nt", reason="path layout is asserted for the shipping platform")
def test_python_resolves_under_local_app_data() -> None:
    resolved = user_storage_root()
    local = os.environ.get("LOCALAPPDATA")
    if not local:
        pytest.skip("LOCALAPPDATA is not set in this environment")
    assert resolved == Path(local) / TOKEN_DIR_NAME


def test_python_path_ends_with_the_identifier_on_every_platform() -> None:
    assert user_storage_root().name == TOKEN_DIR_NAME


def test_the_mirror_is_not_fatal_when_the_directory_cannot_be_written(monkeypatch) -> None:
    """A backend that cannot publish the token must still start.

    The mirror is a convenience for installed clients; every client that can reach
    `<repo>/storage` is unaffected by its failure. Refusing to start would trade an outage for it.
    """
    from services.backend.core import security

    def _explode() -> Path:
        raise OSError("no such drive")

    monkeypatch.setattr(security, "user_storage_root", _explode)
    security._mirror_token_for_installed_clients("deadbeef")  # must not raise
