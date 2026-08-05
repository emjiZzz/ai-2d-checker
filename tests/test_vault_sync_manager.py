"""Stage 0g — relocated from `services/backend/tests/test_vault_sync.py`, which had **never
executed**: that directory sits outside `pyproject.toml`'s `testpaths` and its
`infrastructure.*` imports fail collection from the repo root.

Deliberately smaller than the file it replaces. Two of the original three tests read the
**real** vault and asserted that Japanese tolerance keywords came back — but
`08 - Client Domain & CAD Rules/` is gitignored, so those tests asserted a property of one
developer's filesystem and would fail in CI for a reason having nothing to do with the code.
Rewritten against an injected vault path, which `VaultSyncManager.__init__` already accepts
and `test_vault_sync_scope.py` already uses.

Extraction and scoping behaviour is covered in depth by `test_vault_sync_scope.py` and is not
duplicated here. What remains is what that file does not cover: the singleton, and the
default path arithmetic.
"""

from pathlib import Path

from services.backend.infrastructure.knowledge.vault_sync import VaultSyncManager


def test_get_instance_is_a_singleton():
    assert VaultSyncManager.get_instance() is VaultSyncManager.get_instance()


def test_default_vault_path_resolves_to_the_repo_vault():
    """Pins four levels of `parent` arithmetic in `__init__`.

    `vault_sync.py` walks up from its own file to find `docs/vault`. Moving the module one
    directory would silently point the whole rule-sync layer at the wrong tree, and the
    failure mode is a warning plus a fallback to defaults — not a crash.
    """
    manager = VaultSyncManager()
    repo_root = Path(__file__).resolve().parents[1]

    assert isinstance(manager.vault_path, Path)
    assert manager.vault_path == repo_root / "docs" / "vault", (
        f"Expected the repo's docs/vault, got {manager.vault_path}. If the module moved, "
        f"fix the parent arithmetic — do not relax this assertion."
    )


def test_upper_left_anchors_fall_back_to_defaults_without_a_vault(tmp_path):
    """The original asserted this against the real vault. Injected empty path instead, so
    it tests the fallback rather than one machine's files."""
    manager = VaultSyncManager(vault_path=tmp_path / "nonexistent")
    anchors = manager.get_upper_left_anchors()

    assert "map" in anchors
    assert any(a.startswith("unit no") for a in anchors)


def test_live_rules_expose_the_three_rule_families(tmp_path):
    manager = VaultSyncManager(vault_path=tmp_path / "nonexistent")
    rules = manager.load_live_rules(force_reload=True)

    for key in ("tolerance_keywords", "surface_roughness_patterns", "upper_left_anchors"):
        assert key in rules, f"load_live_rules dropped {key!r}; safe_filter reads it by name"
    assert any(k in rules["tolerance_keywords"] for k in ("指示外公差", "指示無き公差")), (
        "The built-in Japanese tolerance defaults are the floor when no vault is present. "
        "Losing them silently disables tolerance-zone exclusion."
    )
    assert rules["surface_roughness_patterns"]
