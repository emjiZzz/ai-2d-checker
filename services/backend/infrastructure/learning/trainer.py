"""Train the learned-correction bundle from accumulated human feedback.

Pure builder (`build_bundle`) is separated from the async DB fetch (`train_from_feedback`)
so tests can drive it offline with fake feedback objects and no MongoDB. On a successful
train it persists the joblib bundle + meta into the vault and (re)writes the human-readable
Model Card that the user actually reads in Obsidian.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any, Optional

from . import config
from .feature_extractor import exact_key, features_from_snapshot
from .finding_classifier import FindingClassifier
from .model_holder import LearnedModelHolder, model_card_dir, save_bundle, _empty_bundle

try:
    from ...logger import logger
except Exception:  # pragma: no cover
    import logging

    logger = logging.getLogger("learning.trainer")

# Verdict label mapping. Label 1 == "this IS a true discrepancy", label 0 == "not a real
# discrepancy / false alarm / actually matched".
VERDICT_ZERO = {"dismissed", "verdict_matched"}
VERDICT_ONE = {"confirmed_valid", "verdict_changed", "confirmed_change"}

# Pairing feedback: the human says the engine matched the wrong two entities, or missed a
# match that exists. **Captured, never mapped to a verdict label**, and the restraint is the
# point — both available mappings would teach the verdict head something false:
#
#   * label 0 ("not a real discrepancy") would suppress a finding that may well be genuine.
#     "260 was reported as ADDED but it has a counterpart" usually means there IS a change,
#     described wrongly — not that there is no change.
#   * label 1 ("true discrepancy") would affirm a finding whose pairing the human just
#     rejected, teaching the model that the mispairing was correct.
#
# The statement is about the *matcher*, and there is no matcher head to train yet — that is
# Stage 3. Collecting the labels before the model exists is the same bet `AuditFeedbackDocument`
# already paid off on: by the time the model is worth building, the data is there.
MATCHER_FEEDBACK = {"mispaired_missing_counterpart", "mispaired_wrong_match"}


def _snapshot_of(doc: Any) -> dict:
    snap = getattr(doc, "finding_snapshot", None)
    if isinstance(snap, dict) and snap:
        return snap
    # Legacy / thin feedback with no snapshot: synthesize the little we have so the row is
    # still usable (text + category + original status).
    return {
        "rev_text": getattr(doc, "entity_text", None),
        "category": getattr(doc, "category", None),
        "det_status": getattr(doc, "original_status", None),
    }


def _cv_accuracy(rows: list[dict], labels: list) -> Optional[float]:
    """Stratified k-fold accuracy, or None when there isn't enough per-class data to split."""
    counts = Counter(labels)
    if len(counts) < 2 or min(counts.values()) < 2:
        return None
    try:
        import numpy as np
        from sklearn.model_selection import StratifiedKFold

        folds = min(3, min(counts.values()))
        if folds < 2:
            return None
        skf = StratifiedKFold(n_splits=folds, shuffle=True, random_state=0)
        y = np.array(labels)
        idx = np.arange(len(labels))
        accs = []
        for tr, te in skf.split(idx, y):
            model = FindingClassifier().fit([rows[i] for i in tr], [labels[i] for i in tr])
            preds = [model.predict_one(rows[i])[0] for i in te]
            accs.append(sum(1 for p, i in zip(preds, te) if p == labels[i]) / len(te))
        return round(sum(accs) / len(accs), 4)
    except Exception as err:  # pragma: no cover - numerical/edge guard
        logger.warning(f"[learning] CV accuracy computation failed: {err}")
        return None


def build_bundle(docs: list) -> dict:
    """Pure: turn a list of feedback documents (or fakes) into a model bundle dict."""
    bundle = _empty_bundle()
    verdict_rows: list[dict] = []
    verdict_labels: list[int] = []
    cat_rows: list[dict] = []
    cat_labels: list[str] = []
    exact_matched: set = set()
    exact_changed: set = set()
    exact_category: dict = {}
    n_total = 0

    for doc in docs:
        status = getattr(doc, "human_corrected_status", None)
        if not status:
            continue
        n_total += 1
        snap = _snapshot_of(doc)
        category = snap.get("category") or getattr(doc, "category", None)
        text = snap.get("rev_text") or snap.get("ref_text") or getattr(doc, "entity_text", None)
        key = exact_key(category, text)
        row = features_from_snapshot(snap)

        if status in VERDICT_ZERO:
            verdict_rows.append(row)
            verdict_labels.append(0)
            exact_matched.add(key)
            exact_changed.discard(key)
        elif status in VERDICT_ONE:
            verdict_rows.append(row)
            verdict_labels.append(1)
            exact_changed.add(key)
            exact_matched.discard(key)
        elif status == "category_override":
            target = getattr(doc, "corrected_category", None)
            if target:
                cat_rows.append(row)
                cat_labels.append(str(target))
                exact_category[key] = str(target)
        # value_correction: captured for the corpus in v1, not yet a verdict/category label.
        # MATCHER_FEEDBACK: likewise captured, deliberately unlabelled. See below.

    metrics: dict = {}
    verdict_clf = None
    if len(verdict_labels) >= config.MIN_TRAIN and len(set(verdict_labels)) >= 2:
        verdict_clf = FindingClassifier().fit(verdict_rows, verdict_labels)
        metrics["verdict_cv_accuracy"] = _cv_accuracy(verdict_rows, verdict_labels)
        metrics["verdict_class_balance"] = {str(k): verdict_labels.count(k) for k in sorted(set(verdict_labels))}

    category_clf = None
    if len(cat_labels) >= config.CATEGORY_MIN_TRAIN and len(set(cat_labels)) >= 2:
        category_clf = FindingClassifier().fit(cat_rows, cat_labels)
        metrics["category_classes"] = sorted(set(cat_labels))

    bundle.update(
        trained_at=datetime.now(timezone.utc).isoformat(),
        verdict_clf=verdict_clf,
        category_clf=category_clf,
        exact_matched=exact_matched,
        exact_changed=exact_changed,
        exact_category=exact_category,
        n_total=n_total,
        n_verdict=len(verdict_labels),
        n_category=len(cat_labels),
        min_train=config.MIN_TRAIN,
        metrics=metrics,
    )
    return bundle


def _write_model_card(bundle: dict) -> None:
    """(Re)write the human-readable Model Card in the vault. This is the second-brain surface.

    Stage 0h split the two apart: the `.joblib` is a build artifact and now lives under
    `services/backend/storage/models/`, while the card stays here because documentation is
    what the vault is for. They are no longer siblings, which is why this uses
    `model_card_dir()` rather than `learned_model_dir()`.
    """
    try:
        card = model_card_dir() / config.CARD_FILENAME
        trained_at = bundle.get("trained_at")
        verdict_ready = bundle.get("verdict_clf") is not None and bundle.get("n_verdict", 0) >= config.MIN_TRAIN
        metrics = bundle.get("metrics", {})

        # Preserve any existing changelog lines; prepend a new dated one.
        prior_changelog: list[str] = []
        if card.exists():
            try:
                existing = card.read_text(encoding="utf-8", errors="ignore")
                if "## Changelog" in existing:
                    tail = existing.split("## Changelog", 1)[1]
                    prior_changelog = [ln for ln in tail.splitlines() if ln.strip().startswith("- ")]
            except Exception:
                prior_changelog = []
        new_line = (
            f"- {trained_at} — trained on {bundle.get('n_total', 0)} corrections "
            f"(verdict labels: {bundle.get('n_verdict', 0)}, category labels: {bundle.get('n_category', 0)}); "
            f"verdict model {'ACTIVE' if verdict_ready else 'warming up'}."
        )
        changelog = "\n".join([new_line, *prior_changelog[:40]])

        overrides_sample = list(bundle.get("exact_matched", set()))[:10]

        body = f"""---
title: Learned Model Card
type: learned-model
tags: [learned-model, hitl]
---

# 🧠 Learned Correction Model — Card

> Auto-generated on each retrain. The compiled model is `{config.MODEL_FILENAME}` in this
> folder; this note is the human-readable summary. Trained purely on human corrections —
> no LLM involved.

- **Last trained**: {trained_at or "never"}
- **Total corrections**: {bundle.get('n_total', 0)}
- **Verdict labels**: {bundle.get('n_verdict', 0)}  (threshold to activate model: {config.MIN_TRAIN})
- **Category labels**: {bundle.get('n_category', 0)}
- **Verdict model**: {"✅ active" if verdict_ready else f"⏳ warming up ({bundle.get('n_verdict', 0)}/{config.MIN_TRAIN})"}
- **Exact-match overrides**: {len(bundle.get('exact_matched', set()))} matched, {len(bundle.get('exact_changed', set()))} changed, {len(bundle.get('exact_category', {}))} reclassified

## Metrics
```json
{metrics}
```

## Sample of learned "not a real change" patterns
{chr(10).join(f'- `{k}`' for k in overrides_sample) or '- (none yet)'}

## Changelog
{changelog}
"""
        card.write_text(body, encoding="utf-8")
    except Exception as err:  # pragma: no cover - card is best-effort, never fatal
        logger.warning(f"[learning] Failed to write Model Card: {err}")


async def train_from_feedback() -> dict:
    """Fetch all feedback, train, persist bundle + card, and hot-reload the in-process model.

    Returns the same shape as LearnedModelHolder.status() so callers can report it.
    """
    from ...domain.models.audit_feedback import AuditFeedbackDocument

    docs = await AuditFeedbackDocument.find_all().to_list()
    docs.sort(key=lambda d: getattr(d, "created_at", None) or datetime.min.replace(tzinfo=timezone.utc))

    bundle = build_bundle(docs)
    save_bundle(bundle)
    _write_model_card(bundle)
    holder = LearnedModelHolder.get_instance()
    holder.reload()
    logger.info(
        f"[learning] Retrained: {bundle.get('n_total')} corrections "
        f"(verdict={bundle.get('n_verdict')}, category={bundle.get('n_category')}), "
        f"verdict_ready={holder.verdict_ready()}."
    )
    return holder.status()
