"""Process-singleton that owns the loaded model bundle and resolves its vault location.

Mirrors VaultSyncManager's get_instance()/reload pattern: the bundle is loaded once and
reused; a retrain calls reload() to force the in-process copy to pick up the new artifact.
The model lives in the Obsidian vault (user decision) under `09 - Learned Models/`, resolved
through the SAME VaultSyncManager.vault_path that AutoDocEngine uses for `08 - ...`.
"""
from __future__ import annotations

import json
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


def learned_model_dir() -> Path:
    """`<vault>/09 - Learned Models/`, created on demand. Reuses the vault-path resolution
    already centralized in VaultSyncManager rather than hardcoding a second path."""
    vault_path = VaultSyncManager.get_instance().vault_path
    d = vault_path / config.MODEL_DIRNAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def model_path() -> Path:
    return learned_model_dir() / config.MODEL_FILENAME


def meta_path() -> Path:
    return learned_model_dir() / config.META_FILENAME


def save_bundle(bundle: dict) -> None:
    joblib.dump(bundle, model_path())
    meta = {k: bundle.get(k) for k in ("schema", "trained_at", "n_total", "n_verdict", "n_category", "min_train", "metrics")}
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
