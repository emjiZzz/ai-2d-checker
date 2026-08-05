"""Process-singleton that owns the loaded model bundle and resolves where it lives.

Mirrors VaultSyncManager's get_instance()/reload pattern: the bundle is loaded once and
reused; a retrain calls reload() to force the in-process copy to pick up the new artifact.

**Stage 0h moved the artifact out of the vault.** It used to live only under
`docs/vault/09 - Learned Models/`, which is gitignored — so the model could not be
committed, diffed, or shipped inside the Tauri bundle, and existed on exactly one machine.
That blocked rung 3 outright: a model that cannot be versioned is not trainable
infrastructure.

Resolution order:

| | reads | writes |
| :--- | :--- | :--- |
| `LEARNED_MODEL_DIR` env | yes | yes |
| `services/backend/storage/models/` | yes | yes |
| `docs/vault/09 - Learned Models/` | yes, **deprecated** | no |

The vault stays *readable* so an install that trained before this change keeps working until
its next retrain, at which point the artifact lands in the new location on its own. The
`.joblib` payload is gitignored there; the `.meta.json` beside it is committed, so a training
run is diffable in git without carrying a binary. `Model Card.md` still writes to the vault —
it is documentation for humans, not a build artifact.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import joblib

from . import config
from ..knowledge.vault_sync import VaultSyncManager

try:
    from ...logger import logger
except Exception:  # pragma: no cover - test/util import fallback
    import logging

    logger = logging.getLogger("learning.model_holder")


def _backend_root() -> Path:
    """`services/backend/`, from this file's own location."""
    return Path(__file__).resolve().parent.parent.parent


def learned_model_dir() -> Path:
    """Where a retrain **writes**: the env override, else `services/backend/storage/models/`.

    Never the vault. A write there would recreate the situation Stage 0h exists to end.
    """
    override = os.environ.get(config.MODEL_DIR_ENV)
    directory = Path(override) if override else _backend_root() / config.MODEL_STORAGE_DIRNAME
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def legacy_model_dir() -> Path:
    """`<vault>/09 - Learned Models/` — deprecated, read-only, and **not** created on demand.

    Creating it would resurrect an empty directory in a tree the model no longer belongs in.
    """
    return VaultSyncManager.get_instance().vault_path / config.MODEL_DIRNAME


def model_card_dir() -> Path:
    """The vault, still. `Model Card.md` is the human-readable surface, not a build artifact,
    and documentation is what the vault is for."""
    directory = legacy_model_dir()
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def model_path() -> Path:
    """Where the bundle is **read** from: the new location if it holds one, else the vault.

    Falling back rather than migrating silently. A copy would double the artifact on disk
    with no record of which is authoritative; the next retrain resolves it by writing to the
    new location, and the log line below says which one answered.
    """
    current = learned_model_dir() / config.MODEL_FILENAME
    if current.exists():
        return current
    legacy = legacy_model_dir() / config.MODEL_FILENAME
    if legacy.exists():
        logger.warning(
            f"[learning] Loading the model bundle from its deprecated vault location "
            f"({legacy}). The vault is gitignored, so this artifact cannot be committed or "
            f"shipped. It will move to {current.parent} on the next retrain (Stage 0h)."
        )
        return legacy
    return current


def meta_path() -> Path:
    return learned_model_dir() / config.META_FILENAME


def save_bundle(bundle: dict) -> None:
    # Deliberately `learned_model_dir()`, not `model_path()`: a retrain always writes to the
    # current location even when the bundle it replaces was read from the vault. That is
    # what makes the migration happen by itself rather than needing a script.
    target = learned_model_dir() / config.MODEL_FILENAME
    joblib.dump(bundle, target)
    meta = {
        k: bundle.get(k)
        for k in (
            "schema",
            "trained_at",
            "n_total",
            "n_verdict",
            "n_category",
            "min_train",
            "metrics",
        )
    }
    with open(meta_path(), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, default=str)


def _empty_bundle() -> dict:
    return {
        "schema": config.BUNDLE_SCHEMA,
        "trained_at": None,
        "verdict_clf": None,
        "category_clf": None,
        "exact_matched": set(),
        "exact_changed": set(),
        "exact_category": {},
        "n_total": 0,
        "n_verdict": 0,
        "n_category": 0,
        "min_train": config.MIN_TRAIN,
        "metrics": {},
    }


class LearnedModelHolder:
    _instance: Optional["LearnedModelHolder"] = None

    def __init__(self) -> None:
        self._bundle: Optional[dict] = None
        self._loaded = False

    @classmethod
    def get_instance(cls) -> "LearnedModelHolder":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def reload(self) -> None:
        """Force a re-read of the persisted bundle (call after a retrain)."""
        self._loaded = False
        self._bundle = None
        _ = self.bundle

    @property
    def bundle(self) -> Optional[dict]:
        if not self._loaded:
            self._loaded = True
            try:
                p = model_path()
                if p.exists():
                    self._bundle = joblib.load(p)
                    logger.info(f"[learning] Loaded model bundle from {p} (trained_at={self._bundle.get('trained_at')}).")
                else:
                    self._bundle = None
            except Exception as err:
                logger.warning(f"[learning] Failed to load model bundle, learning inactive: {err}")
                self._bundle = None
        return self._bundle

    # --- readiness gates -------------------------------------------------
    def has_anything(self) -> bool:
        b = self.bundle
        if not b:
            return False
        return bool(
            b.get("exact_matched") or b.get("exact_changed") or b.get("exact_category")
            or b.get("verdict_clf") is not None or b.get("category_clf") is not None
        )

    def verdict_ready(self) -> bool:
        b = self.bundle
        return bool(b and b.get("verdict_clf") is not None and b.get("n_verdict", 0) >= config.MIN_TRAIN)

    def category_ready(self) -> bool:
        b = self.bundle
        return bool(b and b.get("category_clf") is not None and b.get("n_category", 0) >= config.CATEGORY_MIN_TRAIN)

    def status(self) -> dict:
        """Serializable snapshot for GET /audits/learning/status and the UI panel."""
        b = self.bundle or _empty_bundle()
        return {
            "trained_at": b.get("trained_at"),
            "n_total": b.get("n_total", 0),
            "n_verdict": b.get("n_verdict", 0),
            "n_category": b.get("n_category", 0),
            "n_exact_overrides": len(b.get("exact_matched", set())) + len(b.get("exact_changed", set())) + len(b.get("exact_category", {})),
            "min_train": config.MIN_TRAIN,
            "verdict_ready": self.verdict_ready(),
            "category_ready": self.category_ready(),
            "metrics": b.get("metrics", {}),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
