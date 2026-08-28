r"""The Tauri shell's storage-root search must not escape the project it belongs to.

`find_storage_root()` walks up to six parents from the working directory and from the executable
looking for a directory named `storage`. In a checkout that finds the repository's own. From an
installed build there is nothing to find -- so it keeps ascending, and an app installed under
`%LOCALAPPDATA%\KMTI Checker\` is five parents below `C:\`, which puts a stray `C:\storage`
inside the budget.

🔴 That is what shipped. On 2026-08-28 the installed 0.1.8 build read
`C:\storage\secure\.api-token` -- a token published the previous day by a frozen backend that
had been launched from `C:\` (the incident 27fb0ab fixed on the backend side). It decrypts
perfectly, because the key is derived from machine and user rather than from provenance, so
nothing rejected it until the backend answered 401 on every authenticated request. `/health` needs
no token and stayed 200, so the app displayed itself as CONNECTED.

⚠ **Why a test rather than a comment.** The per-user branch already carried a comment calling
itself *"the only branch an INSTALLED build can reach"*. It was wrong for as long as any directory
named `storage` sat above the install location, and a comment cannot notice that.

Parses the Rust rather than restating it, for the same reason as `tests/test_user_token_dir.py`:
nothing type-checks across this language boundary.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
RUST_SECURITY = REPO_ROOT / "apps" / "desktop" / "src-tauri" / "src" / "security" / "mod.rs"


def _rust_source() -> str:
    assert RUST_SECURITY.is_file(), f"missing {RUST_SECURITY}"
    return RUST_SECURITY.read_text(encoding="utf-8")


def _find_storage_root_body() -> str:
    """The body of `find_storage_root`, by brace matching from its signature."""
    source = _rust_source()
    start = source.index("pub fn find_storage_root()")
    open_brace = source.index("{", start)

    depth = 0
    for index in range(open_brace, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[open_brace : index + 1]
    raise AssertionError("unbalanced braces in find_storage_root")


def test_the_checkout_gate_exists() -> None:
    assert "fn looks_like_checkout" in _rust_source()


def _searches_only(body: str) -> str:
    """The function body with the explicit `STORAGE_ROOT` override removed.

    That branch is exempt on purpose and is the only one that is: it accepts a directory the
    operator named, rather than one the search discovered, so a marker check would break the
    override for anyone pointing at a storage directory outside a checkout -- which is its entire
    purpose. Cut by brace matching rather than by line number so it survives edits above it.
    """
    start = body.index('env::var("STORAGE_ROOT")')
    open_brace = body.index("{", start)

    depth = 0
    for index in range(open_brace, len(body)):
        if body[index] == "{":
            depth += 1
        elif body[index] == "}":
            depth -= 1
            if depth == 0:
                return body[:start] + body[index + 1 :]
    raise AssertionError("unbalanced braces in the STORAGE_ROOT override")


def test_every_discovered_storage_directory_is_gated() -> None:
    """No branch may accept a `storage` directory on the strength of its name alone.

    Three searches share one failure: the ascent from the working directory, the ascent from the
    executable, and the relative fallbacks -- which are that ascent unrolled. Gating two of the
    three leaves the defect intact, so this asserts over the whole function body.
    """
    body = _searches_only(_find_storage_root_body())

    accepting_conditions = re.findall(r"if\s+([^\n{]*?\.is_dir\(\)[^\n{]*?)\s*\{", body)
    assert accepting_conditions, "no `is_dir()` branch found -- has the search been rewritten?"

    ungated = [
        condition
        for condition in accepting_conditions
        if "looks_like_checkout" not in condition and "beside_a_checkout" not in condition
    ]

    # The per-user branch is the one legitimate exception: it is not a discovered directory, it is
    # the address the backend publishes to, and it is checked last.
    ungated = [c for c in ungated if "user_root" not in c]

    assert not ungated, (
        "a storage directory is accepted without a project marker beside it, so an installed "
        f"build can bind to a stray one: {ungated}"
    )


def test_the_per_user_root_is_still_the_last_resort() -> None:
    """Order matters: a checkout must keep resolving to its own storage.

    If the per-user branch moved ahead of the searches, every developer's app would read the
    mirrored token and write logs and sessions to `%LOCALAPPDATA%`, which is a different bug in
    the same place.
    """
    body = _find_storage_root_body()
    assert body.index("user_app_data_root()") > body.index("fallback_paths")


def test_this_repository_satisfies_the_marker_the_rust_side_looks_for() -> None:
    """The gate is only correct while the checkout it describes is the one on disk.

    Extracted from the Rust rather than hard-coded, so renaming `pyproject.toml` or restructuring
    `services/` fails here instead of silently sending every dev build to the per-user root.
    """
    body = re.search(
        r"fn looks_like_checkout\(root: &Path\) -> bool \{(.*?)\n\}", _rust_source(), re.S
    )
    assert body, "could not read the marker list out of looks_like_checkout"

    file_markers = re.findall(r'root\.join\("([^"]+)"\)\.is_file\(\)', body.group(1))
    assert any((REPO_ROOT / marker).is_file() for marker in file_markers), (
        f"none of the Rust side's file markers {file_markers} exist at the repository root, so a "
        "development build no longer resolves to the repository's own storage directory"
    )
