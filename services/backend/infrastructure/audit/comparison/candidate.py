from typing import Literal, Optional

from pydantic import BaseModel


class ComparisonCandidate(BaseModel):
    """
    Intermediate finding produced by a single generator (deterministic or AI Vision)
    in the hybrid comparison pipeline, before reconciliation/verification decide
    whether it's trusted.

    Deliberately has no `verification` field: no single candidate knows its own
    verification outcome — that's only known once the reconciler has compared it
    against the other generator's candidates, so it's attached later, not carried here.

    Superset of CanvasMarking's fields so candidate -> CanvasMarking is a straight
    copy (see `to_marking_dict`) once `verification` is known.
    """

    text_content: str
    status: Literal["MATCHED", "CHANGED", "ADDED", "REMOVED"]
    details: str
    category: Literal[
        "drawing_views",
        "notes_section",
        "bill_of_materials",
        "title_block",
        "isometric_view",
        "other_engineering_references",
    ] = "drawing_views"
    origin: Literal["deterministic", "ai_vision"]

    entity_id: Optional[str] = None
    coordinates: Optional[list[float]] = None
    ref_coordinates: Optional[list[float]] = None
    bbox: Optional[list[list[float]]] = None
    ref_bbox: Optional[list[list[float]]] = None
    original_value: Optional[str] = None
    visual_bbox: Optional[list[float]] = None
    ref_visual_bbox: Optional[list[float]] = None

    # Set during each generator's own per-candidate coordinate resolution pass
    # (section 1.2 of the implementation plan), before reconciliation ever runs.
    resolution_method: Optional[Literal["entity_handle", "visual_bbox_fallback", "unresolved"]] = None

    # Sub-item taxonomy key within `category` (docs/checklist-taxonomy-grouping-
    # implementation-plan.md) — e.g. category="title_block", feature="scale". Set
    # independently by each generator before reconciliation; never a match criterion
    # in reconciler.py. See taxonomy.py for the canonical key list and
    # taxonomy.OTHER_FEATURE_KEY for the always-valid catch-all fallback.
    feature: Optional[str] = None


def to_marking_dict(
    candidate: ComparisonCandidate,
    verification: Literal["confirmed_both", "confirmed_single", "corrected_to_matched", "conflict", "unverified"],
    status_override: Optional[str] = None,
) -> dict:
    """
    Converts a resolved ComparisonCandidate into the dict shape CanvasMarking expects.

    status_override lets the reconciler/verifier promote a candidate's status to
    CONFLICT without mutating the candidate itself, so both generators' raw output
    stays intact for diagnostics/audit-trail purposes even after the final status
    is decided.
    """
    data = candidate.model_dump()
    if status_override is not None:
        data["status"] = status_override
    data["verification"] = verification
    return data


def calibrate_candidate_confidence(
    verification: Literal["confirmed_both", "confirmed_single", "corrected_to_matched", "conflict", "unverified"],
    origin: Optional[Literal["deterministic", "ai_vision"]],
    resolution_method: Optional[Literal["entity_handle", "visual_bbox_fallback", "unresolved"]],
) -> float:
    """
    Per-finding confidence for the hybrid pipeline (docs/hybrid-comparison-engine-
    implementation-plan.md, Phase 5) — mirrors ai_engine.py::_calibrate_confidence's
    shape (base score x penalty multiplier(s), clamped) instead of the flat
    per-verification-outcome constant Phase 4 shipped as a placeholder.

    `origin` here means "which generator's account the final marking is based on"
    (i.e. which one won a confirmed_single dispute, or the sole side for a
    single-source finding) — not which generator merely happened to run.

    No third factor for "which cascade model answered" (Pro/Flash/Fallback) — the
    plan's earlier draft floated it, but a single Gemini call's model choice doesn't
    map cleanly onto individual findings within that call's response, and the plan's
    own detailed Phase 5 spec only enumerates these two factors. Left out rather than
    added speculatively.
    """
    base_by_verification = {
        # Both generators independently produced the same finding — the strongest
        # possible corroboration this pipeline can produce.
        "confirmed_both": 0.97,
        # Disputed, but the crop verifier confirmed one side. Deterministic slightly
        # outranks AI Vision here — its account was still grounded in exact CAD data,
        # the AI Vision account was not.
        "confirmed_single": 0.90 if origin == "deterministic" else 0.85,
        # The verifier looked at the actual crops and found no real difference at all —
        # both generators' original claims were wrong, not just disagreeing with each
        # other. A clean negative result observed directly against the drawings, so it
        # ranks close to confirmed_both despite requiring an override of both sides.
        "corrected_to_matched": 0.93,
        # Neither side could be confirmed against the crops — deliberately low, and
        # always paired with status="CONFLICT" so it reads as "needs review" without
        # needing a separate boolean flag duplicating that same signal.
        "conflict": 0.50,
        # Not currently produced by hybrid_orchestrator.py (every disputed finding is
        # run through the verifier) — kept for schema completeness/future use, e.g. a
        # later cost optimization that skips verification for some disputes.
        "unverified": 0.60,
    }
    score = base_by_verification.get(verification, 0.5)

    resolution_multiplier = {
        "entity_handle": 1.0,
        "visual_bbox_fallback": 0.9,
        "unresolved": 0.7,
    }
    score *= resolution_multiplier.get(resolution_method, 0.7)

    return max(0.1, min(1.0, round(score, 4)))
