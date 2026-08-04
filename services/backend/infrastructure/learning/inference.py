"""Apply the learned model to a finished comparison, POST-cache.

Called from perform_drawing_comparison on BOTH the cache-hit and fresh paths, right before
returning, so a retrain takes effect immediately for every drawing pair and the adjusted
output is NEVER written back into the deterministic comparison cache.

v1 scope (see config.SPATIAL_CATEGORIES and the vault gotcha note): only the three noisy
spatial categories (drawing_views / notes_section / isometric_view) are adjusted, because
their checklist content is a marking table we can regenerate consistently. Precedence per
finding: exact human override (highest) → model prediction (gated by confidence) → abstain
(keep the deterministic verdict). Any failure returns the deterministic response untouched —
the learner can never make the audit crash.
"""
from __future__ import annotations

from typing import Any, Optional

from . import config
from .feature_extractor import exact_key, features_from_marking
from .model_holder import LearnedModelHolder

try:
    from ...logger import logger
except Exception:  # pragma: no cover
    import logging

    logger = logging.getLogger("learning.inference")


def _decide(marking: dict, bundle: dict, verdict_ready: bool) -> tuple[Optional[str], Optional[str]]:
    """Return (new_status, new_category) for one marking, or (None, None) to abstain."""
    orig_status = marking.get("status")
    orig_cat = marking.get("category")

    keys = [exact_key(orig_cat, marking.get("text_content"))]
    if marking.get("original_value"):
        keys.append(exact_key(orig_cat, marking.get("original_value")))

    exact_matched = bundle.get("exact_matched", set())
    exact_changed = bundle.get("exact_changed", set())
    exact_category = bundle.get("exact_category", {})
    verdict_clf = bundle.get("verdict_clf")

    new_cat = None
    for k in keys:
        target = exact_category.get(k)
        if target and target in config.SPATIAL_CATEGORIES and target != orig_cat:
            new_cat = target
            break

    # v1 only adjusts verdicts inside the spatial categories (consistency — see module docstring).
    effective_cat = new_cat or orig_cat
    if effective_cat not in config.SPATIAL_CATEGORIES:
        return None, new_cat

    new_status = None
    # 1) exact human override — highest precision.
    if any(k in exact_matched for k in keys):
        if orig_status != "MATCHED":
            new_status = "MATCHED"
    elif any(k in exact_changed for k in keys):
        # Affirm a real change: only promote a MATCHED; never downgrade an ADDED/REMOVED to CHANGED.
        if orig_status == "MATCHED":
            new_status = "CHANGED"

    # 2) model verdict — only when no exact decision fired and the model is trained enough.
    if new_status is None and verdict_ready and verdict_clf is not None:
        row = features_from_marking({**marking, "category": effective_cat})
        dist = verdict_clf.proba([row])[0]
        p_true = float(dist.get(1, 0.0))
        if orig_status in ("CHANGED", "ADDED", "REMOVED") and p_true < config.LOW_THRESH:
            new_status = "MATCHED"
        elif orig_status == "MATCHED" and p_true > config.HIGH_THRESH:
            new_status = "CHANGED"

    return new_status, new_cat


def _recompute_spatial_categories(response: Any, markings: list[dict]) -> None:
    """Regenerate the marking table + status for each spatial category from the adjusted
    markings, so the checklist rows AND the Completion Parity reflect the changes (not just
    the canvas badges). Reuses the deterministic pipeline's own table builder (lazy import
    breaks the orchestrator<->inference cycle)."""
    from ..audit.comparison.orchestrator import build_marking_table  # lazy: avoids import cycle
    from ...api.schemas import CategoryComparison

    for cat in config.SPATIAL_CATEGORIES:
        cat_marks = [m for m in markings if m.get("category") == cat]
        if not cat_marks:
            continue
        table = build_marking_table(markings, category_filter=cat)
        n_changed = sum(1 for m in cat_marks if m.get("status") != "MATCHED")
        n_matched = len(cat_marks) - n_changed
        label = cat.replace("_", " ")
        setattr(
            response,
            cat,
            CategoryComparison(
                status="CHANGED" if n_changed else "MATCHED",
                difference_summary=f"Found {n_changed} changed / {n_matched} matched {label} (after learned adjustments).",
                reference_content=table,
                revision_content=table,
                engineering_discrepancy_details=f"{len(cat_marks)} finding(s); {n_matched} confirmed matched by the learned model.",
            ),
        )


def apply_learned_adjustments(response: Any, ref_entities: Any = None, rev_entities: Any = None) -> Any:
    """Adjust a PhysicalComparisonResponse in place using the learned model. Safe no-op when
    nothing has been learned yet or on any error."""
    try:
        holder = LearnedModelHolder.get_instance()
        if not holder.has_anything():
            return response
        bundle = holder.bundle
        if not bundle:
            return response

        verdict_ready = holder.verdict_ready()
        markings = [m.model_dump() for m in response.canvas_markings]

        changed_any = False
        n_flipped = 0
        for m in markings:
            new_status, new_cat = _decide(m, bundle, verdict_ready)
            if new_cat and new_cat != m.get("category"):
                m["category"] = new_cat
                changed_any = True
            if new_status and new_status != m.get("status"):
                m["status"] = new_status
                m["details"] = (m.get("details") or "") + " (adjusted by learned model)"
                changed_any = True
                n_flipped += 1

        if not changed_any:
            return response

        from ...api.schemas import CanvasMarking

        response.canvas_markings = [CanvasMarking(**m) for m in markings]
        _recompute_spatial_categories(response, markings)
        logger.info(f"[learning] Applied learned adjustments: {n_flipped} verdict flip(s) across {len(markings)} markings.")
        return response
    except Exception as err:
        logger.warning(f"[learning] apply_learned_adjustments failed; returning deterministic result: {err}")
        return response
