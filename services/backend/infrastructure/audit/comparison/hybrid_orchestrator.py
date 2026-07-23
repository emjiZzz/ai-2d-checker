import os
import asyncio
from datetime import datetime, UTC
from typing import Optional

from ....domain.models.audit_session import AuditSession
from ....domain.models.audit_violation import AuditViolation
from ....domain.models.drawing_document import DrawingDocument
from ....logger import logger
from ....config import settings
from ....api.schemas import (
    PhysicalComparisonResponse,
    CategoryComparison,
    CanvasMarking,
    ComparisonDiagnostics,
)
from .cache_manager import ComparisonCacheManager
from .candidate import ComparisonCandidate, to_marking_dict, calibrate_candidate_confidence
from .orchestrator import generate_deterministic_candidates, build_marking_table
from .full_ai_orchestrator import generate_ai_vision_candidates
from .reconciler import reconcile_candidates, DisputedFinding
from .crop_verifier import CropVerificationInput, run_crop_verification
from ...rendering.image_cropper import crop_region_image
from . import taxonomy


# Categories where Generator A's `feature` comes from a structured field/column lookup
# (title-block field map, BOM column map), not a heuristic text guess — strictly more
# trustworthy than Generator B's image-reasoning guess, so it always wins a confirmed-
# both tie (docs/checklist-taxonomy-grouping-implementation-plan.md, decision 5).
_FEATURE_ALWAYS_DETERMINISTIC_CATEGORIES = {"title_block", "bill_of_materials"}


def _confirmed_both_feature(det: ComparisonCandidate, ai: ComparisonCandidate) -> Optional[str]:
    """
    Tie-break for a confirmed-both finding's `feature` tag. For the two structured-lookup
    categories, Generator A's tag always wins. For every other category (drawing_views/
    notes_section/isometric_view/other_engineering_references — decision 5 names three of
    these explicitly; other_engineering_references has no structured Generator A source
    either, so it gets the same treatment as the safer default rather than being left
    unhandled), Generator A's tag wins unless it's the `other` catch-all, in which case
    Generator B's guess — grounded in the actual rendered image — is taken instead of
    leaving a classifiable finding stuck in the unclassified bucket.
    """
    if det.category in _FEATURE_ALWAYS_DETERMINISTIC_CATEGORIES:
        return det.feature
    if det.feature and det.feature != taxonomy.OTHER_FEATURE_KEY:
        return det.feature
    return ai.feature


def _confidence_for_marking(marking: dict) -> float:
    """Per-finding confidence via candidate.py::calibrate_candidate_confidence — see Phase 5."""
    return calibrate_candidate_confidence(
        verification=marking.get("verification"),
        origin=marking.get("origin"),
        resolution_method=marking.get("resolution_method"),
    )


def _describe(cand: Optional[ComparisonCandidate], missing_label: str) -> tuple[str, str]:
    """Human-readable status/details for a disputed finding's crop-verifier prompt, for the side that has no candidate at all."""
    if cand is None:
        return "NOT_FOUND", f"{missing_label} did not detect anything at this location."
    return cand.status, cand.details


def _pick_cad_bbox(
    det: Optional[ComparisonCandidate], ai: Optional[ComparisonCandidate], side: str
) -> Optional[tuple]:
    """
    Picks a CAD-space bbox (or a zero-area point, which crop_region_image pads) to crop
    for one side of a disputed finding. side="rev" reads coordinates/bbox, side="ref"
    reads ref_coordinates/ref_bbox. Prefers det over ai, and bbox over a bare point —
    det's coordinates are exact entity-handle lookups; ai's are at best a resolved text
    match, at worst a normalized visual-bbox estimate.

    Falls back to the OTHER side's geometry when the natural side has none. This is the
    common case for REMOVED (no rev-side geometry by definition — it doesn't exist on
    the revision) and ADDED (no ref-side geometry — it doesn't exist on the reference)
    candidates: without this fallback, `_pick_cad_bbox(..., side="rev")` for a REMOVED
    finding returns None, the caller skips cropping the revision entirely, and the
    verifier's prompt says "(no revision crop available)" — it has nothing to look at
    and can never confirm the item is actually gone. Revision drawings share the same
    CAD origin/scale as their reference, so cropping the revision at the reference's
    coordinates (or vice versa) lets the verifier actually check "is it still there at
    this same spot" instead of being handed an unanswerable question.
    """
    def _try(bbox_attr: str, coord_attr: str) -> Optional[tuple]:
        for cand in (det, ai):
            if cand is None:
                continue
            bbox = getattr(cand, bbox_attr)
            if bbox:
                return (bbox[0][0], bbox[0][1], bbox[1][0], bbox[1][1])
            coords = getattr(cand, coord_attr)
            if coords and len(coords) >= 2:
                x, y = coords[0], coords[1]
                return (x, y, x, y)
        return None

    if side == "rev":
        return _try("bbox", "coordinates") or _try("ref_bbox", "ref_coordinates")
    return _try("ref_bbox", "ref_coordinates") or _try("bbox", "coordinates")


def _base_candidate_for_finding(finding: DisputedFinding) -> ComparisonCandidate:
    """Prefer det_candidate for display fields when both exist (exact coordinates/text); falls back to ai_candidate only when det never produced anything for this finding."""
    return finding.det_candidate if finding.det_candidate is not None else finding.ai_candidate


def _resolve_disputed(finding: DisputedFinding, verdict: Optional[dict]) -> dict:
    """
    Turns one disputed finding plus its (possibly missing) crop-verifier verdict into a
    final marking dict.

    Checks `differs` before `confirms`: the verifier reports both — whether the crops
    show an actual difference at all, and (if so) which generator's account matches
    what it saw. If the verifier looked at the real crops and found no difference,
    that overrides whatever either generator originally claimed; the correct outcome
    is MATCHED, not a review flag for a difference that was never really there. Only
    once a real difference is confirmed (or `differs` is missing/unknown) does
    `confirms` decide which generator's specific account to trust.

    A missing verdict (dropped/failed batch — see crop_verifier.run_crop_verification),
    a "neither" confirms alongside a real difference, or a verdict naming a side that
    doesn't actually exist for this finding, all fall through to CONFLICT — never
    silently resolved to a side without an actual confirmation.
    """
    if verdict is not None:
        if verdict.get("differs") is False:
            base = _base_candidate_for_finding(finding)
            return to_marking_dict(base, verification="corrected_to_matched", status_override="MATCHED")

        confirms = verdict.get("confirms")
        if confirms == "A" and finding.det_candidate is not None:
            return to_marking_dict(finding.det_candidate, verification="confirmed_single")
        if confirms == "B" and finding.ai_candidate is not None:
            return to_marking_dict(finding.ai_candidate, verification="confirmed_single")
    base = _base_candidate_for_finding(finding)
    return to_marking_dict(base, verification="conflict", status_override="CONFLICT")


async def perform_hybrid_comparison(
    request,
    ref_drawing: DrawingDocument,
    rev_drawing: DrawingDocument,
    ref_entities: list,
    rev_entities: list,
) -> PhysicalComparisonResponse:
    """
    `hybrid` method entrypoint (docs/hybrid-comparison-engine-implementation-plan.md).

    Runs the deterministic generator (orchestrator.py::generate_deterministic_candidates)
    and the AI Vision generator (full_ai_orchestrator.py::generate_ai_vision_candidates)
    independently and concurrently — they never see each other's output — reconciles
    their candidate lists by location (reconciler.py), resolves disagreements with a
    narrow crop-based verifier (crop_verifier.py) instead of a one-directional override,
    and returns the same PhysicalComparisonResponse shape as the other three methods.
    """
    cached_payload = ComparisonCacheManager.get_cached_comparison(
        ref_drawing_id=str(ref_drawing.id),
        rev_drawing_id=str(rev_drawing.id),
        ref_hash=ref_drawing.file_hash,
        rev_hash=rev_drawing.file_hash,
        method="hybrid",
    )
    if cached_payload:
        try:
            return PhysicalComparisonResponse(
                drawing_views=CategoryComparison(**cached_payload["drawing_views"]),
                notes_section=CategoryComparison(**cached_payload["notes_section"]),
                bill_of_materials=CategoryComparison(**cached_payload["bill_of_materials"]),
                title_block=CategoryComparison(**cached_payload["title_block"]),
                isometric_view=CategoryComparison(**cached_payload["isometric_view"]),
                other_engineering_references=CategoryComparison(**cached_payload["other_engineering_references"]),
                canvas_markings=[CanvasMarking(**item) for item in cached_payload.get("canvas_markings", [])],
                diagnostics=cached_payload.get("diagnostics"),
            )
        except Exception as cache_err:
            logger.warning(f"[hybrid] Failed to parse cached comparison, re-running: {cache_err}")

    api_key = os.environ.get("GEMINI_API_KEY") or getattr(settings, "GEMINI_API_KEY", None)
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not configured.")

    # Generator A (no LLM call) and Generator B (one Gemini call) don't depend on each
    # other — run them concurrently instead of sequentially like the other methods do.
    # Each is wrapped in its own candidate-stage cache check first (Phase 7): a change
    # to reconciliation/verification logic below invalidates the final "hybrid" cache
    # entry checked above, but shouldn't force re-running either generator if neither
    # one's own logic changed — that's the whole point of splitting the two cache tiers.
    async def _get_det_result():
        cached = ComparisonCacheManager.get_cached_candidates(
            ref_drawing_id=str(ref_drawing.id), rev_drawing_id=str(rev_drawing.id),
            ref_hash=ref_drawing.file_hash, rev_hash=rev_drawing.file_hash, generator="hybrid_gen_a",
        )
        if cached:
            try:
                candidates = [ComparisonCandidate(**c) for c in cached["candidates"]]
                return candidates, cached["category_rollups"], cached["zone_detection_warnings"]
            except Exception as parse_err:
                logger.warning(f"[hybrid] Failed to parse cached Generator A candidates, recomputing: {parse_err}")

        result = await generate_deterministic_candidates(ref_drawing, rev_drawing, ref_entities, rev_entities)
        candidates, category_rollups, zone_detection_warnings = result
        try:
            ComparisonCacheManager.set_cached_candidates(
                ref_drawing_id=str(ref_drawing.id), rev_drawing_id=str(rev_drawing.id),
                ref_hash=ref_drawing.file_hash, rev_hash=rev_drawing.file_hash, generator="hybrid_gen_a",
                payload={
                    "candidates": [c.model_dump() for c in candidates],
                    "category_rollups": category_rollups,
                    "zone_detection_warnings": zone_detection_warnings,
                },
            )
        except Exception as cache_err:
            logger.warning(f"[hybrid] Failed to cache Generator A candidates: {cache_err}")
        return result

    async def _get_ai_result():
        cached = ComparisonCacheManager.get_cached_candidates(
            ref_drawing_id=str(ref_drawing.id), rev_drawing_id=str(rev_drawing.id),
            ref_hash=ref_drawing.file_hash, rev_hash=rev_drawing.file_hash, generator="hybrid_gen_b",
        )
        if cached:
            try:
                candidates = [ComparisonCandidate(**c) for c in cached["candidates"]]
                return candidates, cached["model_used"]
            except Exception as parse_err:
                logger.warning(f"[hybrid] Failed to parse cached Generator B candidates, recomputing: {parse_err}")

        result = await generate_ai_vision_candidates(ref_drawing, rev_drawing, ref_entities, rev_entities)
        candidates, model_used_result = result
        try:
            ComparisonCacheManager.set_cached_candidates(
                ref_drawing_id=str(ref_drawing.id), rev_drawing_id=str(rev_drawing.id),
                ref_hash=ref_drawing.file_hash, rev_hash=rev_drawing.file_hash, generator="hybrid_gen_b",
                payload={
                    "candidates": [c.model_dump() for c in candidates],
                    "model_used": model_used_result,
                },
            )
        except Exception as cache_err:
            logger.warning(f"[hybrid] Failed to cache Generator B candidates: {cache_err}")
        return result

    (det_result, ai_result) = await asyncio.gather(_get_det_result(), _get_ai_result())
    det_candidates, category_rollups, zone_detection_warnings = det_result
    ai_candidates, model_used = ai_result

    # Both generators already resolved + DTO-normalized their own coordinates
    # internally (Phase 2) — no separate "coordinate resolution" pass needed here,
    # per the implementation plan's section 1.2.
    reconciliation = reconcile_candidates(det_candidates, ai_candidates)

    verification_inputs: list[CropVerificationInput] = []
    for finding in reconciliation.disputed:
        det_status, det_details = _describe(finding.det_candidate, "Deterministic generator")
        ai_status, ai_details = _describe(finding.ai_candidate, "AI Vision generator")
        rev_bbox = _pick_cad_bbox(finding.det_candidate, finding.ai_candidate, side="rev")
        ref_bbox = _pick_cad_bbox(finding.det_candidate, finding.ai_candidate, side="ref")
        rev_crop = (
            crop_region_image(str(rev_drawing.id), rev_drawing.metadata, rev_bbox)
            if rev_bbox and rev_drawing.metadata else None
        )
        ref_crop = (
            crop_region_image(str(ref_drawing.id), ref_drawing.metadata, ref_bbox)
            if ref_bbox and ref_drawing.metadata else None
        )
        verification_inputs.append(CropVerificationInput(
            finding_id=finding.finding_id,
            ref_crop=ref_crop,
            rev_crop=rev_crop,
            det_status=det_status,
            det_details=det_details,
            ai_status=ai_status,
            ai_details=ai_details,
        ))

    verdicts = await run_crop_verification(api_key, verification_inputs) if verification_inputs else {}

    final_markings: list[dict] = []
    counts = {"confirmed_both": 0, "confirmed_single": 0, "corrected_to_matched": 0, "conflicts": 0}

    for rf in reconciliation.confirmed:
        marking = to_marking_dict(rf.det_candidate, verification="confirmed_both")
        marking["feature"] = _confirmed_both_feature(rf.det_candidate, rf.ai_candidate)
        final_markings.append(marking)
        counts["confirmed_both"] += 1

    for finding in reconciliation.disputed:
        marking = _resolve_disputed(finding, verdicts.get(finding.finding_id))
        final_markings.append(marking)
        verification = marking["verification"]
        if verification == "conflict":
            counts["conflicts"] += 1
        elif verification == "corrected_to_matched":
            counts["corrected_to_matched"] += 1
        else:
            counts["confirmed_single"] += 1

    # Category-level status AND content: rebuild every category's summary from the
    # FINAL merged/reconciled/verified list, not Generator A's raw pre-reconciliation
    # rollup. This closes two real gaps, not just a staleness nitpick: (1) a category
    # where only Generator B found anything (e.g. notes_section/bill_of_materials in a
    # real run where Generator A produced zero candidates there) previously kept
    # showing Generator A's own "nothing detected" table even though canvas_markings
    # had real findings for that category; (2) a disputed finding the crop verifier
    # resolved to CONFLICT — or corrected back to MATCHED after finding no real
    # difference — never appeared in the table at all, so the checklist panel's
    # per-row view (ChecklistPanel.tsx parses reference_content) was showing
    # Generator A's original, sometimes-wrong guesses as if they were the pipeline's
    # final answer. See hybrid-comparison-engine-implementation-plan.md Phase 6's
    # completion log for the gap this closes.
    #
    # Tradeoff: title_block/bill_of_materials lose their specialized field-paired
    # table format (e.g. "Unit No." REMOVED shown alongside its replacement "45" ADDED
    # as one conceptual field-value change) in favor of the generic per-marking table
    # every other category already uses — that specialized format is built from raw
    # extracted field dicts (ref_title_fields/rev_title_fields), not from
    # canvas_markings, so preserving it while also reflecting reconciled/verified
    # status would need deeper surgery than this pass. Correctness over polish here.
    category_agreement: list[dict] = []
    for cat_key in (
        "drawing_views", "notes_section", "isometric_view",
        "other_engineering_references", "title_block", "bill_of_materials",
    ):
        cat_markings = [m for m in final_markings if m.get("category") == cat_key]
        changed_count = sum(1 for m in cat_markings if m.get("status") != "MATCHED")
        matched_count = len(cat_markings) - changed_count
        conflict_count = sum(1 for m in cat_markings if m.get("status") == "CONFLICT")

        if cat_markings:
            table = build_marking_table(cat_markings)
            category_rollups[cat_key]["status"] = "CHANGED" if changed_count > 0 else "MATCHED"
            category_rollups[cat_key]["reference_content"] = table
            category_rollups[cat_key]["revision_content"] = table
            summary = f"Found {changed_count} changed / {matched_count} matched"
            if conflict_count:
                summary += f" ({conflict_count} needing manual review)"
            summary += "."
            category_rollups[cat_key]["difference_summary"] = summary
            category_rollups[cat_key]["engineering_discrepancy_details"] = (
                f"{len(cat_markings)} finding(s) verified by the hybrid dual-generator pipeline."
            )
        # If cat_markings is empty, neither generator found anything for this category —
        # leave Generator A's own rollup as-is (e.g. its correctly-empty "No notes
        # detected" text); there's nothing to rebuild from.

        gen_a_count = sum(1 for c in det_candidates if c.category == cat_key)
        gen_b_count = sum(1 for c in ai_candidates if c.category == cat_key)
        if gen_a_count == 0 and gen_b_count == 0 and not cat_markings:
            continue  # neither generator nor the final list touched this category at all
        category_agreement.append({
            "category": cat_key,
            "generator_a_candidates": gen_a_count,
            "generator_b_candidates": gen_b_count,
            "confirmed_both": sum(1 for m in cat_markings if m.get("verification") == "confirmed_both"),
            "confirmed_single": sum(1 for m in cat_markings if m.get("verification") == "confirmed_single"),
            "corrected_to_matched": sum(1 for m in cat_markings if m.get("verification") == "corrected_to_matched"),
            "conflicts": sum(1 for m in cat_markings if m.get("verification") == "conflict"),
        })

    comparison_response = PhysicalComparisonResponse(
        drawing_views=CategoryComparison(**category_rollups["drawing_views"]),
        notes_section=CategoryComparison(**category_rollups["notes_section"]),
        bill_of_materials=CategoryComparison(**category_rollups["bill_of_materials"]),
        title_block=CategoryComparison(**category_rollups["title_block"]),
        isometric_view=CategoryComparison(**category_rollups["isometric_view"]),
        other_engineering_references=CategoryComparison(**category_rollups["other_engineering_references"]),
        canvas_markings=[CanvasMarking(**m) for m in final_markings],
        diagnostics=ComparisonDiagnostics(
            model_used=model_used,
            zone_detection_warnings=zone_detection_warnings,
            generator_a_candidates=len(det_candidates),
            generator_b_candidates=len(ai_candidates),
            confirmed_both=counts["confirmed_both"],
            confirmed_single=counts["confirmed_single"],
            corrected_to_matched=counts["corrected_to_matched"],
            conflicts=counts["conflicts"],
            category_agreement=category_agreement,
        ),
    )

    # Save comparison findings as AuditSession + AuditViolations
    try:
        non_matched = [m for m in final_markings if m.get("status") != "MATCHED"]
        total_markings = len(final_markings)
        matched_count = total_markings - len(non_matched)
        comparison_score = round((matched_count / total_markings) * 100, 2) if total_markings > 0 else 100.0
        avg_confidence = (
            sum(_confidence_for_marking(m) for m in final_markings) / total_markings
            if total_markings > 0 else 0.9
        )

        comparison_session = AuditSession(
            drawing_id=str(rev_drawing.id),
            reference_drawing_id=str(ref_drawing.id),
            standard_id=None,
            client_name=None,
            status="completed",
            compliance_score=comparison_score,
            confidence_score=round(avg_confidence, 4),
            timings={},
            diagnostics={
                "source": "physical_comparison",
                "comparison_method": "hybrid",
                "total_markings": total_markings,
                "non_matched": len(non_matched),
                "confirmed_both": counts["confirmed_both"],
                "confirmed_single": counts["confirmed_single"],
                "corrected_to_matched": counts["corrected_to_matched"],
                "conflicts": counts["conflicts"],
            },
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
        )
        await comparison_session.save()

        SEVERITY_MAP = {"CHANGED": "medium", "ADDED": "high", "REMOVED": "high", "CONFLICT": "medium"}
        violations_to_save = []
        for marking_dict in non_matched:
            marking = CanvasMarking(**marking_dict)
            confidence = _confidence_for_marking(marking_dict)
            coords = None
            if marking.coordinates:
                if isinstance(marking.coordinates, list):
                    if len(marking.coordinates) > 0 and not isinstance(marking.coordinates[0], list):
                        coords = [marking.coordinates]
                    else:
                        coords = marking.coordinates

            violations_to_save.append(
                AuditViolation(
                    audit_session_id=str(comparison_session.id),
                    severity=SEVERITY_MAP.get(marking.status, "medium"),
                    category=f"comparison_{marking.category}",
                    description=f"[{marking.status}] {marking.details}",
                    recommendation=(
                        f"Manually review '{marking.text_content}' — the two generators disagreed "
                        "and the crop verifier could not confirm either side."
                        if marking.status == "CONFLICT"
                        else f"Resolve discrepancy in '{marking.text_content}' against the reference drawing."
                    ),
                    source="hybrid_comparison",
                    confidence=confidence,
                    standard_reference=None,
                    affected_entities=[
                        {"entity_id": marking.entity_id, "marker_shape": "BOX"}
                    ] if marking.entity_id else [],
                    coordinates=coords,
                )
            )

        if violations_to_save:
            await AuditViolation.insert_many(violations_to_save)

        logger.info(
            f"[hybrid] Persisted {len(violations_to_save)} violations "
            f"(session {comparison_session.id}, score {comparison_score}%, "
            f"confirmed_both={counts['confirmed_both']}, confirmed_single={counts['confirmed_single']}, "
            f"corrected_to_matched={counts['corrected_to_matched']}, conflicts={counts['conflicts']})."
        )
    except Exception as persist_err:
        logger.warning(f"[hybrid] Violation persistence failed (non-fatal): {persist_err}")

    try:
        ComparisonCacheManager.set_cached_comparison(
            ref_drawing_id=str(ref_drawing.id),
            rev_drawing_id=str(rev_drawing.id),
            ref_hash=ref_drawing.file_hash,
            rev_hash=rev_drawing.file_hash,
            payload=comparison_response.model_dump(),
            method="hybrid",
        )
    except Exception as cache_write_err:
        logger.warning(f"[hybrid] Failed to cache comparison response: {cache_write_err}")

    return comparison_response
