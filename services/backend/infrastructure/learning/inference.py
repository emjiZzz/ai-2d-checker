"""Apply the learned model to a finished comparison, POST-cache.

Called from perform_drawing_comparison on BOTH the cache-hit and fresh paths, right before
returning, so a retrain takes effect immediately for every drawing pair and the adjusted
output is NEVER written back into the deterministic comparison cache.

Scope: Exact human overrides (exact_matched / exact_changed) apply across ALL categories
(drawing_views, notes_section, isometric_view, title_block, bill_of_materials, other).
Model-based statistical predictions run on spatial categories where a marking table can be
regenerated consistently. Precedence per finding: exact human override (highest) → model
prediction (gated by confidence) → abstain (keep the deterministic verdict). Any failure returns
the deterministic response untouched — the learner can never make the audit crash.
"""
from __future__ import annotations

from typing import Any, Optional

from . import config
from .feature_extractor import exact_key, features_from_marking, _norm
from .model_holder import LearnedModelHolder

try:
    from ...logger import logger
except Exception:  # pragma: no cover
    import logging

    logger = logging.getLogger("learning.inference")


def _decide(marking: dict, bundle: dict, verdict_ready: bool) -> tuple[Optional[str], Optional[str]]:
    """Return (new_status, new_category) for one marking, or (None, None) to abstain."""
    orig_status = marking.get("status")
    orig_cat = (marking.get("category") or "unknown").removeprefix("comparison_")

    exact_matched = bundle.get("exact_matched", set())
    exact_changed = bundle.get("exact_changed", set())
    exact_category = bundle.get("exact_category", {})
    verdict_clf = bundle.get("verdict_clf")

    keys = set()
    for txt in [
        marking.get("text_content"),
        marking.get("original_value"),
        marking.get("details"),
        f"[{orig_status}] {marking.get('details')}",
    ]:
        if txt:
            keys.add(exact_key(orig_cat, txt))
            keys.add(exact_key("", txt))

    new_cat = None
    for k in keys:
        target = exact_category.get(k)
        if target and target != orig_cat:
            new_cat = target
            break

    effective_cat = (new_cat or orig_cat).removeprefix("comparison_")

    new_status = None
    # 1) Exact key check
    if any(k in exact_matched for k in keys):
        if orig_status != "MATCHED":
            new_status = "MATCHED"
    elif any(k in exact_changed for k in keys):
        if orig_status == "MATCHED":
            new_status = "CHANGED"

    # 2) Substring / token matching for exact overrides
    norm_details = _norm(marking.get("details") or "")
    norm_text = _norm(marking.get("text_content") or "")
    norm_orig = _norm(marking.get("original_value") or "")

    if new_status is None and exact_matched:
        for em in exact_matched:
            em_cat, _, em_val = em.partition("|")
            if (not em_cat or em_cat == orig_cat or em_cat == "unknown") and em_val and len(em_val) >= 2:
                if (em_val in norm_details or em_val in norm_text or em_val in norm_orig or
                    (len(norm_text) >= 2 and norm_text in em_val) or
                    (len(norm_orig) >= 2 and norm_orig in em_val)):
                    if orig_status != "MATCHED":
                        new_status = "MATCHED"
                        break

    if new_status is None and exact_changed:
        for ec in exact_changed:
            ec_cat, _, ec_val = ec.partition("|")
            if (not ec_cat or ec_cat == orig_cat or ec_cat == "unknown") and ec_val and len(ec_val) >= 2:
                if (ec_val in norm_details or ec_val in norm_text or ec_val in norm_orig or
                    (len(norm_text) >= 2 and norm_text in ec_val) or
                    (len(norm_orig) >= 2 and norm_orig in ec_val)):
                    if orig_status == "MATCHED":
                        new_status = "CHANGED"
                        break

    # 3) Model verdict — only when no exact decision fired, category is spatial, and the model is trained enough.
    if new_status is None and effective_cat in config.SPATIAL_CATEGORIES and verdict_ready and verdict_clf is not None:
        row = features_from_marking({**marking, "category": effective_cat})
        dist = verdict_clf.proba([row])[0]
        p_true = float(dist.get(1, 0.0))
        if orig_status in ("CHANGED", "ADDED", "REMOVED") and p_true < config.LOW_THRESH:
            new_status = "MATCHED"
        elif orig_status == "MATCHED" and p_true > config.HIGH_THRESH:
            new_status = "CHANGED"

    return new_status, new_cat


def _update_table_row_status(content: str, text_content: str, original_val: str, details: str, new_status: str) -> str:
    """Helper to update a markdown table row's status column (MATCHED / CHANGED)."""
    if not content:
        return content
    from ..audit.comparison.spatial_differ import SpatialDiffer

    norm_rev = SpatialDiffer._normalize_text(text_content) if text_content else ""
    norm_ref = SpatialDiffer._normalize_text(original_val) if original_val else ""
    norm_det = SpatialDiffer._normalize_text(details) if details else ""

    lines = content.split("\n")
    new_lines = []
    for line in lines:
        if "|" in line:
            parts = [p.strip() for p in line.split("|")]
            # Typical row: | Field | Original | Revision | Status |
            if len(parts) >= 5:
                row_field = SpatialDiffer._normalize_text(parts[1]) if len(parts) > 1 else ""
                row_ref = SpatialDiffer._normalize_text(parts[2]) if len(parts) > 2 else ""
                row_rev = SpatialDiffer._normalize_text(parts[3]) if len(parts) > 3 else ""
                matched_row = False
                if norm_rev and (norm_rev in row_rev or row_rev in norm_rev):
                    matched_row = True
                elif norm_ref and (norm_ref in row_ref or row_ref in norm_ref):
                    matched_row = True
                elif norm_det and (row_field and row_field in norm_det):
                    matched_row = True

                if matched_row:
                    parts[4] = new_status
                    line = " | ".join(parts)
        new_lines.append(line)
    return "\n".join(new_lines)


def _recompute_all_categories(response: Any, markings: list[dict]) -> None:
    """Regenerate or adjust summary tables across categories so the checklist rows and
    inspection summary reflect learned adjustments."""
    from ..audit.comparison.orchestrator import build_marking_table  # lazy: avoids import cycle
    from ...api.schemas import CategoryComparison

    # 1. Spatial categories: full table rebuild
    for cat in config.SPATIAL_CATEGORIES:
        cat_marks = [m for m in markings if (m.get("category") or "").removeprefix("comparison_") == cat]
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

    # 2. Structured table categories: patch table row statuses if markings were adjusted
    for cat in ("title_block", "bill_of_materials", "other_engineering_references"):
        cat_obj = getattr(response, cat, None)
        if not cat_obj:
            continue
        cat_marks = [m for m in markings if (m.get("category") or "").removeprefix("comparison_") == cat]
        if not cat_marks:
            continue

        ref_table = cat_obj.reference_content or ""
        rev_table = cat_obj.revision_content or ""

        for m in cat_marks:
            st = m.get("status", "MATCHED")
            text = m.get("text_content") or ""
            orig = m.get("original_value") or ""
            det = m.get("details") or ""
            ref_table = _update_table_row_status(ref_table, text, orig, det, st)
            rev_table = _update_table_row_status(rev_table, text, orig, det, st)

        n_changed = sum(1 for m in cat_marks if m.get("status") != "MATCHED")
        cat_obj.status = "CHANGED" if n_changed > 0 else "MATCHED"
        cat_obj.reference_content = ref_table
        cat_obj.revision_content = rev_table


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
        _recompute_all_categories(response, markings)
        logger.info(f"[learning] Applied learned adjustments: {n_flipped} verdict flip(s) across {len(markings)} markings.")
        return response
    except Exception as err:
        logger.warning(f"[learning] apply_learned_adjustments failed; returning deterministic result: {err}")
        return response
