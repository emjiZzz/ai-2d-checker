"""Stage 0h — the learned model artifact no longer lives only in the gitignored vault.

`docs/vault/09 - Learned Models/` is excluded from git, so the trained bundle could not be
committed, diffed, or shipped inside the Tauri sidecar: it existed on exactly one machine.
The staged plan is blunt about the consequence — *a model that cannot be committed, diffed,
or shipped is not trainable infrastructure* — and it blocked rung 3 outright.

The migration has to be gentle in one specific way: an install that trained **before** this
change still has its bundle in the vault, and must keep working until its next retrain. So
reads fall back to the old location and writes never do, which makes the move happen by
itself with no migration script and no moment where the model is missing.
"""

import os
from pathlib import Path

import pytest

from services.backend.infrastructure.learning import config, model_holder


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    """Point the write location at a scratch dir and the vault at another."""
    monkeypatch.setenv(config.MODEL_DIR_ENV, str(tmp_path / "models"))

    from services.backend.infrastructure.knowledge.vault_sync import VaultSyncManager

    manager = VaultSyncManager.get_instance()
    original = manager.vault_path
    manager.vault_path = tmp_path / "vault"
    yield tmp_path
    manager.vault_path = original


def test_writes_go_to_storage_not_the_vault(isolated, monkeypatch):
    monkeypatch.delenv(config.MODEL_DIR_ENV, raising=False)
    directory = model_holder.learned_model_dir()

    backend_root = Path(model_holder.__file__).resolve().parent.parent.parent
    assert directory == backend_root / config.MODEL_STORAGE_DIRNAME
    assert "vault" not in str(directory), (
        "A write into the vault recreates exactly the situation Stage 0h exists to end."
    )


def test_env_override_wins(isolated):
    assert model_holder.learned_model_dir() == Path(os.environ[config.MODEL_DIR_ENV])


def test_read_prefers_the_new_location(isolated):
    new = model_holder.learned_model_dir()
    (new / config.MODEL_FILENAME).write_bytes(b"new")
    legacy = model_holder.legacy_model_dir()
    legacy.mkdir(parents=True, exist_ok=True)
    (legacy / config.MODEL_FILENAME).write_bytes(b"old")

    assert model_holder.model_path() == new / config.MODEL_FILENAME


def test_read_falls_back_to_the_vault_so_an_existing_install_keeps_working(isolated):
    """The deprecated path. Without it, everyone who trained before this change would
    silently lose their model — the learned layer would go inert with no error."""
    legacy = model_holder.legacy_model_dir()
    legacy.mkdir(parents=True, exist_ok=True)
    (legacy / config.MODEL_FILENAME).write_bytes(b"old")

    assert model_holder.model_path() == legacy / config.MODEL_FILENAME


def test_with_nothing_trained_the_read_path_points_at_the_new_location(isolated):
    assert model_holder.model_path().parent == model_holder.learned_model_dir()


def test_legacy_dir_is_not_created_on_demand(isolated):
    """Creating it would resurrect an empty directory in a tree the model has left."""
    legacy = model_holder.legacy_model_dir()
    assert not legacy.exists()


def test_model_card_still_writes_to_the_vault(isolated):
    """The card is documentation for humans, which is what the vault is for. Only the
    binary moved."""
    card_dir = model_holder.model_card_dir()
    assert card_dir == model_holder.legacy_model_dir()
    assert card_dir.exists()


def test_save_bundle_writes_to_the_new_location_even_when_the_old_one_holds_a_bundle(isolated):
    """This is what makes the migration happen by itself: a retrain lands in the new place
    regardless of where the bundle it replaces was read from."""
    legacy = model_holder.legacy_model_dir()
    legacy.mkdir(parents=True, exist_ok=True)
    (legacy / config.MODEL_FILENAME).write_bytes(b"old")
    assert model_holder.model_path().parent == legacy  # reading from the vault

    model_holder.save_bundle(model_holder._empty_bundle())

    new = model_holder.learned_model_dir()
    assert (new / config.MODEL_FILENAME).exists()
    assert (new / config.META_FILENAME).exists(), (
        "The .meta.json is the committed half — without it a training run leaves nothing "
        "diffable in git."
    )
    assert model_holder.model_path().parent == new  # now reading from the new location


def test_gitignore_tracks_the_metadata_and_ignores_the_payload():
    """The whole point of the move. Verified against the real `.gitignore` because the rule
    shape is subtle: git never descends into an excluded *directory*, so the parent had to
    become `services/backend/storage/*` before any `!` rule below it could be reached.
    """
    rules = Path(__file__).resolve().parents[1] / ".gitignore"
    text = rules.read_text(encoding="utf-8")

    assert "services/backend/storage/*" in text, (
        "A bare `services/backend/storage/` directory rule makes every negation below it "
        "unreachable, silently — the .meta.json would never be committable."
    )
    assert "!services/backend/storage/models/*.meta.json" in text
    assert "services/backend/storage/models/*" in text
