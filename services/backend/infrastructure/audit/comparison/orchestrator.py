"""Run one drawing comparison: cache, persistence, and the post-cache learned pass.

The engine itself -- every candidate finding and the rules that filter them -- lives in
`candidate_generator.py`. This module was 2049 lines before that split; what is left is the
part that actually orchestrates: check the cache, call the engine, write the AuditSession and
its AuditViolations, apply learned corrections after the cache so a retrain takes effect
without a cache-version bump.

Everything below the import block is re-exported rather than defined. This module is the
historical import site for the whole comparison surface -- seven test modules,
`infrastructure/eval/{runner,sweep}.py` and `infrastructure/learning/inference.py` import
these names from here -- so the façade is a compatibility contract, not convenience.

⚠ `perform_drawing_comparison` calls `generate_deterministic_candidates` by its bare
module-global name on purpose. Python resolves that in *this* module's namespace at call time,
which is what lets `tests/test_comparison_architecture.py` intercept the engine with
`monkeypatch.setattr(orchestrator, "generate_deterministic_candidates", ...)`. Calling it as
`candidate_generator.generate_deterministic_candidates(...)` would silently bypass that patch.
"""

from datetime import datetime, UTC

from ....domain.models.audit_session import AuditSession
from ....domain.models.audit_violation import AuditViolation
from ....domain.models.comparison_method import DETERMINISTIC
from ....domain.models.drawing_document import DrawingDocument
from ....logger import logger
from ....api.schemas import (
    CanvasMarking,
    CategoryComparison,
    ComparisonDiagnostics,
    PhysicalComparisonResponse,
)
from ...learning.inference import apply_learned_adjustments
from .cache_manager import ComparisonCacheManager

# ─── compatibility façade ─────────────────────────────────────────────────────────────
# Unused *here* on purpose: each name below has an existing importer that expects it at
# `orchestrator`. The per-line `noqa` marks that as deliberate public surface rather than
# dead weight. (`X as X` says the same to F401 but trips PLC0414, which this repo enables.)
from .candidate_generator import (
    DROP_SECTION_CALLOUT_LABELS,  # noqa: F401
    FURNITURE_LAYER_TOKENS,  # noqa: F401
    MIN_STRUCTURED_VALUE_LENGTH,  # noqa: F401
    REVISION_TABLE_HEADERS,  # noqa: F401
    _amendment_norm,  # noqa: F401
    _bbox_covers_too_much,  # noqa: F401
    _collect_structured_text_values,  # noqa: F401
    _is_bom_layer,  # noqa: F401
    _is_revision_table_header,  # noqa: F401
    _is_title_layer,  # noqa: F401
    _is_tolerance_layer_or_text,  # noqa: F401
    _learned_rules_for,  # noqa: F401
    _normalize_value_text,  # noqa: F401
    _other_zone_covers,  # noqa: F401
    _point_in_bbox,  # noqa: F401
    _pos_in_bboxes,  # noqa: F401
    _safe_zone_owner,  # noqa: F401
    _ul_corroborates,  # noqa: F401
    amendment_table_bboxes,  # noqa: F401
    build_marking_table,  # noqa: F401
    extract_note_entities,  # noqa: F401
    extract_zone_entities,  # noqa: F401
    generate_deterministic_candidates,
    is_furniture_layer,  # noqa: F401
    is_in_bbox,  # noqa: F401
    is_in_margin,  # noqa: F401
    keep_for_title_extraction,  # noqa: F401
    safe_filter,  # noqa: F401
)
from .title_matcher import (
    UL_BAND_GAP_OUTLIER_FACTOR,  # noqa: F401
    UL_COLUMN_SPLIT_RATIO,  # noqa: F401
    _TITLE_UL_SYNONYMS,  # noqa: F401
    _title_ul_tokens,  # noqa: F401
    _ul_canonical,  # noqa: F401
    _ul_columns,  # noqa: F401
    _ul_synonym_groups,  # noqa: F401
    extract_title_ul_kv,  # noqa: F401
    match_title_ul_pairs,  # noqa: F401
    partition_ul_pairs,  # noqa: F401
    ul_value_band_index,  # noqa: F401
)


async def perform_drawing_comparison(
    request,
    ref_drawing: DrawingDocument,
    rev_drawing: DrawingDocument,
    ref_entities: list,
    rev_entities: list,
    progress_callback=None,
) -> PhysicalComparisonResponse:
    """
    `rag` method entrypoint. Thin wrapper around generate_deterministic_candidates()
    (Generator A) — this function's job is cache handling, response assembly, and
    persistence; the diffing itself lives in the extracted function so `hybrid` can
    reuse it too. Output here is unchanged from before that extraction (Phase 2 of
    docs/hybrid-comparison-engine-implementation-plan.md).
    """
    # Check cache first (unless force_refresh is requested). refresh_ocr implies force_refresh:
    # a re-read OCR value only reaches the output through a fresh comparison run.
    refresh_ocr = getattr(request, "refresh_ocr", False)
    force_refresh = getattr(request, "force_refresh", False) or refresh_ocr
    cached_payload = None if force_refresh else ComparisonCacheManager.get_cached_comparison(
        ref_drawing_id=str(ref_drawing.id),
        rev_drawing_id=str(rev_drawing.id),
        ref_hash=ref_drawing.file_hash,
        rev_hash=rev_drawing.file_hash,
        method=DETERMINISTIC
    )
    if cached_payload:
        try:
            cached_response = PhysicalComparisonResponse(
                drawing_views=CategoryComparison(**cached_payload["drawing_views"]),
                notes_section=CategoryComparison(**cached_payload["notes_section"]),
                bill_of_materials=CategoryComparison(**cached_payload["bill_of_materials"]),
                title_block=CategoryComparison(**cached_payload["title_block"]),
                isometric_view=CategoryComparison(**cached_payload["isometric_view"]),
                other_engineering_references=CategoryComparison(**cached_payload["other_engineering_references"]),
                canvas_markings=[CanvasMarking(**item) for item in cached_payload.get("canvas_markings", [])],
                diagnostics=cached_payload.get("diagnostics"),
            )
            # An entry whose diagnostics carry no `audit_session_id` is served without one ever
            # being created: the AuditSession + AuditViolation writes below sit on the cache-MISS
            # path only, so a hit returns findings that exist nowhere in Mongo.
            #
            # The desktop checklist joins its markers to those documents by that id
            # (apps/desktop/src/utils/persistedViolations.ts) to get an id it can PATCH. Without
            # it every finding is unreviewable -- no supervisor verdict, no visibility toggle --
            # and re-testing cannot fix it, because the re-test hits this same entry.
            #
            # So fall through to a full comparison, which persists the findings, stamps the id and
            # rewrites this entry. Costs one slow run per stale entry, once. If persistence itself
            # is failing the id stays unset and the pair stops caching until that is repaired --
            # deliberate: a finding nobody can sign off on is worse than a slow one.
            if cached_response.diagnostics and cached_response.diagnostics.audit_session_id:
                # Apply the learned model to the cached deterministic result at serve time, so a
                # correction takes effect on already-cached pairs without invalidating the cache.
                return apply_learned_adjustments(cached_response, ref_entities, rev_entities)
            logger.info(
                "Cached comparison carries no audit_session_id (entry predates the field, or its "
                "persistence failed); re-running so this pair's findings are reviewable."
            )
        except Exception as cache_err:
            logger.warning(f"Failed to parse cached drawing comparison, performing full comparison: {cache_err}")

    candidates, parsed, zone_detection_warnings = await generate_deterministic_candidates(
        ref_drawing, rev_drawing, ref_entities, rev_entities, refresh_ocr=refresh_ocr, progress_callback=progress_callback
    )

    clean_markings = [c.model_dump() for c in candidates]

    comparison_response = PhysicalComparisonResponse(
        drawing_views=CategoryComparison(**parsed["drawing_views"]),
        notes_section=CategoryComparison(**parsed["notes_section"]),
        bill_of_materials=CategoryComparison(**parsed["bill_of_materials"]),
        title_block=CategoryComparison(**parsed["title_block"]),
        isometric_view=CategoryComparison(**parsed["isometric_view"]),
        other_engineering_references=CategoryComparison(**parsed["other_engineering_references"]),
        canvas_markings=[CanvasMarking(**item) for item in clean_markings],
        diagnostics=ComparisonDiagnostics(zone_detection_warnings=zone_detection_warnings),
    )

    # Save comparison findings as AuditSession + AuditViolations
    try:
        non_matched = [m for m in clean_markings if m.get("status") != "MATCHED"]
        total_markings = len(clean_markings)
        matched_count = total_markings - len(non_matched)
        comparison_score = round((matched_count / total_markings) * 100, 2) if total_markings > 0 else 100.0

        comparison_session = AuditSession(
            drawing_id=str(rev_drawing.id),
            reference_drawing_id=str(ref_drawing.id),
            standard_id=None,
            client_name=None,
            status="completed",
            compliance_score=comparison_score,
            confidence_score=0.95,
            timings={},
            diagnostics={
                "source": "physical_comparison",
                "comparison_method": DETERMINISTIC,
                "total_markings": total_markings,
                "non_matched": len(non_matched),
            },
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
        )
        await comparison_session.save()

        # Look up previous reviewed violations for this drawing pair to carry forward verdicts and remarks
        from ...learning.feature_extractor import _norm
        prior_reviews: dict[tuple[str, str], AuditViolation] = {}
        prior_reviews_norm: dict[tuple[str, str], AuditViolation] = {}
        try:
            prior_sessions = await AuditSession.find(
                AuditSession.reference_drawing_id == str(ref_drawing.id),
                AuditSession.drawing_id == str(rev_drawing.id),
                AuditSession.id != comparison_session.id
            ).sort(-AuditSession.started_at).limit(5).to_list()

            if prior_sessions:
                prior_session_ids = [str(s.id) for s in prior_sessions]
                reviewed_violations = await AuditViolation.find(
                    {"audit_session_id": {"$in": prior_session_ids}, "resolution_type": {"$ne": None}}
                ).to_list()
                for rv in reviewed_violations:
                    key = (rv.category, rv.description)
                    norm_key = (rv.category, _norm(rv.description))
                    if key not in prior_reviews:
                        prior_reviews[key] = rv
                    if norm_key not in prior_reviews_norm:
                        prior_reviews_norm[norm_key] = rv
        except Exception as review_lookup_err:
            logger.debug(f"[comparison] Previous review lookup: {review_lookup_err}")

        # Check prior reviews and suppress REJECTED false positives
        for m in clean_markings:
            cat = f"comparison_{m.get('category')}"
            desc = f"[{m.get('status')}] {m.get('details')}"
            norm_key = (cat, _norm(desc))
            prior = prior_reviews.get((cat, desc)) or prior_reviews_norm.get(norm_key)
            if prior and prior.resolution_type == "REJECTED":
                m["status"] = "MATCHED"
                if prior.checker_remarks:
                    m["details"] = f"{m.get('details')} (Supervisor Marked Matched: {prior.checker_remarks})"

        SEVERITY_MAP = {"CHANGED": "medium", "ADDED": "high", "REMOVED": "high"}
        violations_to_save = []
        for marking_dict in clean_markings:
            marking = CanvasMarking(**marking_dict)
            coords = None
            if marking.coordinates:
                if isinstance(marking.coordinates, list):
                    if len(marking.coordinates) > 0 and not isinstance(marking.coordinates[0], list):
                        coords = [marking.coordinates]
                    else:
                        coords = marking.coordinates

            cat = f"comparison_{marking.category}"
            desc = f"[{marking.status}] {marking.details}"
            norm_key = (cat, _norm(desc))
            prior = prior_reviews.get((cat, desc)) or prior_reviews_norm.get(norm_key)

            # Save non-matched findings OR findings that carry a supervisor verdict
            if marking.status != "MATCHED" or (prior and prior.resolution_type):
                violations_to_save.append(
                    AuditViolation(
                        audit_session_id=str(comparison_session.id),
                        severity=SEVERITY_MAP.get(marking.status, "medium"),
                        category=cat,
                        description=desc,
                        recommendation=f"Resolve discrepancy in '{marking.text_content}' against the reference drawing.",
                        source="physical_comparison",
                        confidence=0.95,
                        standard_reference=None,
                        affected_entities=[
                            {"entity_id": marking.entity_id, "marker_shape": "BOX"}
                        ] if marking.entity_id else [],
                        coordinates=coords,
                        is_resolved=prior.is_resolved if prior else False,
                        resolved_at=prior.resolved_at if prior else None,
                        checker_remarks=prior.checker_remarks if prior else None,
                        resolution_type=prior.resolution_type if prior else None,
                    )
                )

        if violations_to_save:
            await AuditViolation.insert_many(violations_to_save)

        # Hand the session id back to the client. It was previously created, used as a
        # foreign key and then discarded into a log line, so nothing downstream could ask
        # for this comparison's findings by id -- including the ADR-010 summary endpoint.
        if comparison_response.diagnostics is None:
            comparison_response.diagnostics = ComparisonDiagnostics()
        comparison_response.diagnostics.audit_session_id = str(comparison_session.id)

        logger.info(
            f"Phase 1.4: Persisted {len(violations_to_save)} comparison violations "
            f"(session {comparison_session.id}, score {comparison_score}%, {len(prior_reviews)} carried-forward reviews)."
        )
    except Exception as persist_err:
        logger.warning(f"Comparison violation persistence failed (non-fatal): {persist_err}")

    try:
        ComparisonCacheManager.set_cached_comparison(
            ref_drawing_id=str(ref_drawing.id),
            rev_drawing_id=str(rev_drawing.id),
            ref_hash=ref_drawing.file_hash,
            rev_hash=rev_drawing.file_hash,
            payload=comparison_response.model_dump(),
            method=DETERMINISTIC
        )
    except Exception as cache_write_err:
        logger.warning(f"Failed to cache physical comparison response: {cache_write_err}")

    # Learned adjustments run AFTER the cache write above, so the deterministic result is what
    # gets cached and the model overlay is recomputed fresh on every serve.
    return apply_learned_adjustments(comparison_response, ref_entities, rev_entities)
