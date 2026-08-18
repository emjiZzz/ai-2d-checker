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

import re
from typing import Any, Optional

from . import config
from .feature_extractor import exact_key, exact_pair_key, features_from_marking, _norm
from .model_holder import LearnedModelHolder

try:
    from ...logger import logger
except Exception:  # pragma: no cover
    import logging

    logger = logging.getLogger("learning.inference")


#: Values made entirely of digits and dimension punctuation. Mirrors
#: `spatial_differ._NUMERICISH_RE`, which the engine uses for the same judgement one layer down.
_NUMERIC_OVERRIDE_RE = re.compile(r"^[0-9.,\-/x×øφ°±r():~〜=]+$")

#: Below this length a non-numeric override cannot identify anything by substring, so it must
#: match a value outright. A convention, stated as one — nothing has measured it.
MIN_OVERRIDE_SUBSTRING_CHARS = 3


def _override_applies(
    override_value: str,
    norm_details: str,
    norm_text: str,
    norm_orig: str,
) -> bool:
    """Does a stored human override apply to this marking? **One direction only.**

    A human dismissed (or confirmed) a finding whose normalised text was `override_value`. This
    answers *"is this marking that same finding"*, and nothing else.

    ⚠ **The reverse test — "is this marking's value a fragment of the override" — is deliberately
    absent, and removing it is the fix for a measured defect.** It let the dimension `25` inherit
    a dismissal recorded for the line attribute `CENTER 0.25MM`, because `"25"` is a substring of
    `"center0.25mm"`. On `M745230A01` that force-matched three real dimension changes —
    `25 -> 60`, `55 -> 25`, `170 -> 20` — and reported them to the checker as MATCHED.

    The shape of that bug is the worst available for a human-in-the-loop system: `line_attribute_differ`
    emits false positives on a re-traced revision, the checker correctly dismisses them, and each
    dismissal silently converts real dimension findings into **false negatives**. The correction
    makes the tool quieter and less correct at the same time, and nothing in the UI shows why.

    **A numericish override must match exactly.** `25` and `125` are different values however many
    characters they share — the same rule `spatial_differ._is_edited_in_place` applies when it
    lets two numericish strings bypass the similarity floor.

    Guarded by `tests/test_learned_override_scope.py`.
    """
    if not override_value:
        return False

    fields = tuple(f for f in (norm_details, norm_text, norm_orig) if f)
    if not fields:
        return False

    if _NUMERIC_OVERRIDE_RE.match(override_value):
        return any(override_value == field for field in fields)
    if len(override_value) < MIN_OVERRIDE_SUBSTRING_CHARS:
        return any(override_value == field for field in fields)
    return any(override_value in field for field in fields)


def _decide(marking: dict, bundle: dict, verdict_ready: bool) -> tuple[Optional[str], Optional[str]]:
    """Return (new_status, new_category) for one marking, or (None, None) to abstain."""
    orig_status = marking.get("status")
    orig_cat = (marking.get("category") or "unknown").removeprefix("comparison_")

    norm_text = _norm(marking.get("text_content") or "")
    norm_orig = _norm(marking.get("original_value") or "")
    is_identical_match = bool(norm_text and (norm_text == norm_orig or not norm_orig)) and (orig_status == "MATCHED")

    # Protect true identical matches: A mathematically verified identical dimension ('60'=='60')
    # must NEVER be flipped to CHANGED by a bare number key in historical feedback.
    if is_identical_match:
        return None, None

    exact_matched = bundle.get("exact_matched", set())
    exact_changed = bundle.get("exact_changed", set())
    exact_category = bundle.get("exact_category", {})
    verdict_clf = bundle.get("verdict_clf")

    # A verdict override is keyed on **both sides of the finding**, via the same
    # `exact_pair_key` the trainer stores with — one construction, so a lookup and a write can
    # never drift into disagreeing. Building the transition string here by hand happened to
    # normalise to the identical key, which is exactly the kind of coincidence that keeps working
    # right up until `_normalize_text` changes.
    #
    # `20 -> 3` therefore keys as `drawing_views|20->3` and cannot be matched by a dismissal of
    # `60 -> 20`, which was the live defect: one click on a finding involving `20` force-matched
    # every other finding where either side was `20`.
    keys = {
        exact_pair_key(orig_cat, marking.get("original_value"), marking.get("text_content")),
        exact_pair_key("", marking.get("original_value"), marking.get("text_content")),
    }
    # The details string describes the whole finding, so it is pair-scoped already and stays a
    # useful second address for it.
    for txt in (marking.get("details"), f"[{orig_status}] {marking.get('details')}"):
        if txt and txt.strip():
            keys.add(exact_key(orig_cat, txt))
            keys.add(exact_key("", txt))

    # The category override is a statement about one value ("this text belongs in notes, not
    # views"), not about a transition, so it is looked up single-sided — matching how the
    # trainer stores it.
    cat_keys = {
        exact_key(orig_cat, t)
        for t in (marking.get("text_content"), marking.get("original_value"))
        if t
    }
    new_cat = None
    for k in cat_keys:
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
            if (not em_cat or em_cat == orig_cat or em_cat == "unknown") and em_val:
                if _override_applies(em_val, norm_details, norm_text, norm_orig):
                    if orig_status != "MATCHED":
                        new_status = "MATCHED"
                        break

    if new_status is None and exact_changed:
        for ec in exact_changed:
            ec_cat, _, ec_val = ec.partition("|")
            if (not ec_cat or ec_cat == orig_cat or ec_cat == "unknown") and ec_val:
                if _override_applies(ec_val, norm_details, norm_text, norm_orig):
                    if orig_status == "MATCHED":
                        new_status = "CHANGED"
                        break

    # 3) Model verdict — only when no exact decision fired, category is spatial, and the model is trained enough.
    if new_status is None and effective_cat in config.SPATIAL_CATEGORIES and verdict_ready and verdict_clf is not None:
        row = features_from_marking({**marking, "category": effective_cat})
        dist = verdict_clf.proba([row])[0]
        p_true = float(dist.get(1, 0.0))
        
        # Mathematical identity guard: A classifier must NEVER flip identical dimensions ('60'=='60')
        # to CHANGED, nor claim two conflicting different numbers ('20' vs '3') are MATCHED.
        is_same_text = norm_text and norm_orig and (norm_text == norm_orig)
        is_conflicting_numeric = norm_text and norm_orig and (norm_text != norm_orig) and \
                                bool(re.match(r"^[0-9.,\-/x×øφ°±r():~〜=]+$", norm_text)) and \
                                bool(re.match(r"^[0-9.,\-/x×øφ°±r():~〜=]+$", norm_orig))

        if orig_status in ("CHANGED", "ADDED", "REMOVED") and p_true < config.LOW_THRESH:
            if not is_conflicting_numeric:
                new_status = "MATCHED"
        elif orig_status == "MATCHED" and p_true > config.HIGH_THRESH:
            if not is_same_text:
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
