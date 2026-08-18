"""Train the learned-correction bundle from accumulated human feedback.

Pure builder (`build_bundle`) is separated from the async DB fetch (`train_from_feedback`)
so tests can drive it offline with fake feedback objects and no MongoDB. On a successful
train it persists the joblib bundle + meta into the vault and (re)writes the human-readable
Model Card that the user actually reads in Obsidian.
"""
from __future__ import annotations

import asyncio
import time
from collections import Counter
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any, Optional

from . import config
from .feature_extractor import exact_key, exact_pair_key, features_from_snapshot
from .finding_classifier import FindingClassifier
from .model_holder import LearnedModelHolder, model_card_dir, save_bundle, _empty_bundle

try:
    from ...logger import logger
except Exception:  # pragma: no cover
    import logging

    logger = logging.getLogger("learning.trainer")

# Verdict label mapping. Label 1 == "this IS a true discrepancy", label 0 == "not a real
# discrepancy / false alarm / actually matched".
#
# ⚠ Do NOT add a `mispaired_*` verb here. "Badly paired" is not a verdict, and the reasoning is
# in MATCHER_FEEDBACK below — read it before editing this line. That addition was made once,
# and it silently routes the corpus's single most-used verb into the suppression direction.
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

#: A retrain slower than this is logged loudly. Not a failure — it runs off the loop now — but
#: `_cv_accuracy` scales with the corpus and this is the number that would otherwise creep back
#: up unobserved until someone noticed the app was sluggish again.
SLOW_TRAIN_SECONDS = 5.0


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


def majority_class_baseline(balance: Mapping[str, int]) -> Optional[float]:
    """Accuracy of a model that always predicts the most common class. **The floor.**

    `verdict_cv_accuracy` is meaningless on its own, and on this corpus it is actively
    misleading: at 71 class-0 against 41 class-1, always answering *"not a real change"* scores
    **0.634**. A reported 0.733 is therefore about **ten points of skill**, not seventy-three —
    and a reader who does not know the split has no way to tell those apart.

    This is the same rule `retrieval/metrics.py` already enforces for recall, where every rate is
    printed beside `chance_recall_at_k` and a verdict is withheld unless the lift clears 0.15.
    The retrieval side learned it; the learning side reported a bare accuracy for months.

    Returns None for an empty corpus — no labels, no floor, rather than a misleading 0.0.
    """
    total = sum(balance.values())
    if not total:
        return None
    return round(max(balance.values()) / total, 4)


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
        # A correction the human took back teaches nothing — not even that it happened. It is
        # kept in the collection for the audit trail and skipped here, rather than deleted or
        # cancelled by a compensating record, which would leave two rows with identical
        # features and opposite labels in the classifier's training set.
        if getattr(doc, "retracted_at", None):
            continue
        n_total += 1
        snap = _snapshot_of(doc)
        category = snap.get("category") or getattr(doc, "category", None)
        # **Both sides.** Keying a verdict override on one value let a single dismissal of a
        # finding involving `20` force-match every other finding where either side was `20`.
        # See `exact_pair_key`. `entity_text` is the legacy fallback for thin feedback rows with
        # no snapshot; those carry only the revision side, which keys as an ADDED-shaped pair and
        # so matches only other one-sided findings.
        ref_text = snap.get("ref_text")
        rev_text = snap.get("rev_text") or getattr(doc, "entity_text", None)
        key = exact_pair_key(category, ref_text, rev_text)
        # The category override is genuinely a statement about one value ("this text belongs in
        # notes, not views"), so it keeps the single-sided key.
        cat_key = exact_key(category, rev_text or ref_text)
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
                exact_category[cat_key] = str(target)
        # value_correction: captured for the corpus in v1, not yet a verdict/category label.
        # MATCHER_FEEDBACK: likewise captured, deliberately unlabelled. See below.

    metrics: dict = {}
    verdict_clf = None
    balance = {str(k): verdict_labels.count(k) for k in sorted(set(verdict_labels))}
    minority_share = (min(balance.values()) / len(verdict_labels)) if verdict_labels else 0.0

    if len(verdict_labels) >= config.MIN_TRAIN and len(set(verdict_labels)) >= 2:
        if minority_share >= config.MIN_MINORITY_SHARE:
            verdict_clf = FindingClassifier().fit(verdict_rows, verdict_labels)
            metrics["verdict_cv_accuracy"] = _cv_accuracy(verdict_rows, verdict_labels)
        else:
            # Count reached, balance did not. Abstain LOUDLY rather than activate a head whose
            # prior sits on the LOW_THRESH suppression gate — see config.MIN_MINORITY_SHARE.
            # This is recorded in the bundle (and so in the committed .meta.json and the model
            # card) because an abstention nobody can see is the failure mode this codebase has
            # already paid for once.
            metrics["verdict_abstained"] = {
                "reason": "class_imbalance",
                "minority_share": round(minority_share, 4),
                "required": config.MIN_MINORITY_SHARE,
                "detail": (
                    f"{len(verdict_labels)} labels meet MIN_TRAIN={config.MIN_TRAIN}, but the "
                    f"minority class is {round(minority_share * 100, 1)}% of the corpus against a "
                    f"{round(config.MIN_MINORITY_SHARE * 100, 1)}% floor. Add class-1 corrections "
                    f"(confirmed_valid, verdict_changed); more 'dismissed' makes this worse."
                ),
            }
            logger.warning(
                "Verdict head NOT activated: %d labels clear MIN_TRAIN=%d but minority class share "
                "%.3f is below MIN_MINORITY_SHARE=%.2f (balance=%s). Activating here would let the "
                "prior alone cross LOW_THRESH=%.2f and suppress real findings.",
                len(verdict_labels), config.MIN_TRAIN, minority_share,
                config.MIN_MINORITY_SHARE, balance, config.LOW_THRESH,
            )

    metrics["verdict_class_balance"] = balance
    metrics["verdict_minority_share"] = round(minority_share, 4)
    # Recorded whether or not the head activated, and **always beside the accuracy** — see
    # `majority_class_baseline` for why a bare accuracy figure over an unbalanced corpus reads
    # far stronger than it is.
    metrics["verdict_majority_baseline"] = majority_class_baseline(balance)

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

        # Two different reasons produce an inactive head and they need different words. "warming
        # up (38/40)" reads as a counting problem the next click solves; a corpus that has met the
        # count but failed the balance floor is a different situation and must not be reported as
        # if one more `dismissed` would fix it — that click makes it worse.
        abstained = metrics.get("verdict_abstained") or {}
        n_verdict = bundle.get("n_verdict", 0)
        if verdict_ready:
            verdict_status = "✅ active"
            changelog_status = "ACTIVE"
        elif abstained:
            share = abstained.get("minority_share", 0.0)
            verdict_status = (
                f"⛔ held — count met ({n_verdict}/{config.MIN_TRAIN}) but the minority class is "
                f"{round(share * 100, 1)}% against a {round(config.MIN_MINORITY_SHARE * 100, 1)}% "
                f"floor. Needs `confirmed_valid` / `verdict_changed`, not more `dismissed`."
            )
            changelog_status = f"HELD (class imbalance, minority {round(share * 100, 1)}%)"
        else:
            verdict_status = f"⏳ warming up ({n_verdict}/{config.MIN_TRAIN})"
            changelog_status = "warming up"

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
            f"verdict model {changelog_status}."
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
- **Verdict labels**: {n_verdict}  (thresholds to activate: {config.MIN_TRAIN} labels **and** ≥{round(config.MIN_MINORITY_SHARE * 100, 1)}% minority class)
- **Category labels**: {bundle.get('n_category', 0)}
- **Verdict model**: {verdict_status}
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


#: Serialises retrains. Two corrections clicked close together queue two background tasks, and
#: both would otherwise fit a model and write `finding_classifier.joblib` + `.meta.json` at the
#: same time — from two *threads*, since the CPU half is offloaded. The writes are atomic now, so
#: the worst case is a wasted fit rather than a corrupt bundle; the lock removes the waste and
#: makes "the last correction wins" true rather than approximately true.
_TRAIN_LOCK = asyncio.Lock()


def _train_sync(docs: list) -> tuple[dict, dict]:
    """The whole CPU-bound and disk-bound half of a retrain. **Runs in a worker thread.**"""
    bundle = build_bundle(docs)
    save_bundle(bundle)
    _write_model_card(bundle)
    holder = LearnedModelHolder.get_instance()
    holder.reload()
    return bundle, holder.status()


async def train_from_feedback() -> dict:
    """Fetch all feedback, train, persist bundle + card, and hot-reload the in-process model.

    Returns the same shape as LearnedModelHolder.status() so callers can report it.

    ⚠ **Everything after the fetch runs in a worker thread, and that is load-bearing rather than
    tidy.** `build_bundle` fits a classifier and then cross-validates it — `_cv_accuracy` runs a
    3-fold `StratifiedKFold`, fitting a model per fold and calling `predict_one` per test row.
    Measured on the live corpus at 112 verdict labels: **7.2 s, every call.**

    This is called from `BackgroundTasks`, which runs an async task **on the event loop**, so
    before this change a single verdict blocked the whole backend for those 7.2 seconds. The
    desktop app polls `/health` every 5 s and aborts at 3 s
    (`connectionStore.checkHealth`), so every verdict produced a "Connection Lost" and a
    reconnect.

    **It only started happening when the verdict head crossed its activation threshold**, because
    `_cv_accuracy` is inside the branch that only runs once `minority_share >= MIN_MINORITY_SHARE`.
    Below it `build_bundle` abstains and returns in milliseconds — so the cost arrived with the
    milestone, not with a code change, which is why nothing flagged it.

    Same rule `infrastructure/retrieval/service.py` already states for indexing: *"All CPU work is
    offloaded, because fitting a vocabulary over the corpus blocks the event loop for its whole
    duration."* The retrieval layer learned this; the learning layer had not.
    """
    from ...domain.models.audit_feedback import AuditFeedbackDocument

    async with _TRAIN_LOCK:
        docs = await AuditFeedbackDocument.find_all().to_list()
        docs.sort(
            key=lambda d: getattr(d, "created_at", None)
            or datetime.min.replace(tzinfo=timezone.utc)
        )

        started = time.perf_counter()
        bundle, status = await asyncio.to_thread(_train_sync, docs)
        elapsed = time.perf_counter() - started

    logger.info(
        f"[learning] Retrained in {elapsed:.2f}s (off-loop): {bundle.get('n_total')} corrections "
        f"(verdict={bundle.get('n_verdict')}, category={bundle.get('n_category')}), "
        f"verdict_ready={status.get('verdict_ready')}."
    )
    if elapsed > SLOW_TRAIN_SECONDS:
        logger.warning(
            f"[learning] The retrain took {elapsed:.1f}s. It no longer blocks the event loop, "
            f"but it grows with the corpus — `_cv_accuracy` fits a model per fold and predicts "
            f"per row. If this keeps climbing, batch the predictions or sample the CV set."
        )
    return status
