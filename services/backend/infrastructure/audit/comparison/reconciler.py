import math
from dataclasses import dataclass, field
from typing import Optional

from .candidate import ComparisonCandidate

# Same match radius as the intra-generator dedup already used on AI markings
# (full_ai_orchestrator.py's spatial dedup) — reused here for the cross-generator case,
# per docs/hybrid-comparison-engine-implementation-plan.md, Phase 3 / section 1.3.
MATCH_RADIUS_MM = 5.0


@dataclass
class ReconciledFinding:
    """One finding both generators independently produced and agreed on — trusted directly, no verifier call needed."""
    det_candidate: ComparisonCandidate
    ai_candidate: ComparisonCandidate


@dataclass
class DisputedFinding:
    """
    One finding where the generators disagree, or where only one generator produced
    anything at all. Exactly one of det_candidate/ai_candidate is None for a
    single-source dispute; both are set for a same-location status conflict.
    """
    finding_id: str
    det_candidate: Optional[ComparisonCandidate]
    ai_candidate: Optional[ComparisonCandidate]


@dataclass
class ReconciliationResult:
    confirmed: list[ReconciledFinding] = field(default_factory=list)
    disputed: list[DisputedFinding] = field(default_factory=list)


def _distance_mm(a: ComparisonCandidate, b: ComparisonCandidate) -> Optional[float]:
    """CAD-space distance between two candidates' coordinates. None if either lacks one."""
    ac, bc = a.coordinates, b.coordinates
    if not ac or not bc or len(ac) < 2 or len(bc) < 2:
        return None
    return math.hypot(ac[0] - bc[0], ac[1] - bc[1])


def reconcile_candidates(
    det_candidates: list[ComparisonCandidate],
    ai_candidates: list[ComparisonCandidate],
) -> ReconciliationResult:
    """
    Matches Generator A's and Generator B's candidate lists by location (section 1.3 of
    the implementation plan): fuzzy spatial matching, not exact-key matching, since the
    two generators derive coordinates differently (exact entity handle vs. resolved/
    visual-bbox estimate) — they will not agree on coordinates down to the decimal even
    when they've found the same real difference.

    A det candidate with no ai candidate within MATCH_RADIUS_MM (or vice versa) is a
    single-source dispute, not an auto-trusted finding — "only one generator saw this" is
    exactly the coverage gap Generator B exists to catch, and exactly the kind of thing
    Generator A's entity-mispairing failure mode produces. Both go to the verifier.

    Only an exact status match (both MATCHED, or both the identical CHANGED/ADDED/REMOVED
    value) counts as agreement. A det candidate calling something CHANGED and an ai
    candidate calling the same location ADDED both mean "something is different here," but
    they disagree on *what* — that classification conflict is still worth a human's eyes,
    so it goes to the verifier rather than being silently merged into whichever generator's
    label happened to be picked up first.

    Matching is greedy nearest-neighbor, not globally-optimal bipartite matching — the same
    false-pairing tolerance SpatialDiffer already accepts elsewhere in this codebase.

    `feature` (docs/checklist-taxonomy-grouping-implementation-plan.md) is deliberately
    never a match criterion here — it's a display-grouping tag, not a real-world identity
    signal, and the two generators' `feature` guesses can legitimately disagree on the
    same real finding. hybrid_orchestrator.py resolves which side's `feature` wins on a
    confirmed match; this function only ever reads category/coordinates/status.
    """
    result = ReconciliationResult()
    matched_ai_indices: set[int] = set()

    for det_idx, det in enumerate(det_candidates):
        best_ai_idx: Optional[int] = None
        best_distance: Optional[float] = None

        for ai_idx, ai in enumerate(ai_candidates):
            if ai_idx in matched_ai_indices:
                continue
            if ai.category != det.category:
                continue
            dist = _distance_mm(det, ai)
            if dist is None or dist >= MATCH_RADIUS_MM:
                continue
            if best_distance is None or dist < best_distance:
                best_distance = dist
                best_ai_idx = ai_idx

        if best_ai_idx is None:
            result.disputed.append(
                DisputedFinding(finding_id=f"det-{det_idx}", det_candidate=det, ai_candidate=None)
            )
            continue

        ai = ai_candidates[best_ai_idx]
        matched_ai_indices.add(best_ai_idx)

        if det.status == ai.status:
            result.confirmed.append(ReconciledFinding(det_candidate=det, ai_candidate=ai))
        else:
            result.disputed.append(
                DisputedFinding(
                    finding_id=f"det-{det_idx}-ai-{best_ai_idx}",
                    det_candidate=det,
                    ai_candidate=ai,
                )
            )

    # Any AI candidate never claimed by a det match is single-source on the AI side.
    for ai_idx, ai in enumerate(ai_candidates):
        if ai_idx in matched_ai_indices:
            continue
        result.disputed.append(
            DisputedFinding(finding_id=f"ai-{ai_idx}", det_candidate=None, ai_candidate=ai)
        )

    return result
