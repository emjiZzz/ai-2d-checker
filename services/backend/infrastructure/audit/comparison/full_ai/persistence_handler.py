"""
persistence_handler.py — Handles AuditSession and AuditViolation database persistence and cache saving.
"""

from datetime import datetime, UTC
from typing import Any

from .....domain.models.audit_session import AuditSession
from .....domain.models.audit_violation import AuditViolation
from .....logger import logger
from .....api.schemas import CanvasMarking, PhysicalComparisonResponse
from ..cache_manager import ComparisonCacheManager


class FullAIPersistenceHandler:
    """
    Handles MongoDB database persistence for full-AI audit sessions & violations,
    and manages disk caching via ComparisonCacheManager.
    """

    @staticmethod
    async def persist_audit_results(
        ref_drawing: Any,
        rev_drawing: Any,
        parsed_data: dict[str, Any],
        comparison_response: PhysicalComparisonResponse,
        method: str,
        ref_png_used: bool = True,
        rev_png_used: bool = True
    ) -> None:
        """
        Creates and saves AuditSession, computes compliance score, inserts non-MATCHED AuditViolations,
        and saves output to ComparisonCacheManager.
        """
        try:
            canvas_markings_raw = parsed_data.get("canvas_markings", [])
            non_matched = [m for m in canvas_markings_raw if m.get("status") != "MATCHED"]
            total_markings = len(canvas_markings_raw)
            matched_count = total_markings - len(non_matched)
            comparison_score = (
                round((matched_count / total_markings) * 100, 2) if total_markings > 0 else 100.0
            )

            comparison_session = AuditSession(
                drawing_id=str(rev_drawing.id),
                reference_drawing_id=str(ref_drawing.id),
                standard_id=None,
                client_name=None,
                status="completed",
                compliance_score=comparison_score,
                confidence_score=0.80,
                timings={},
                diagnostics={
                    "source": "physical_comparison",
                    "comparison_method": method,
                    "total_markings": total_markings,
                    "non_matched": len(non_matched),
                    "ref_png_used": ref_png_used,
                    "rev_png_used": rev_png_used,
                },
                started_at=datetime.now(UTC),
                completed_at=datetime.now(UTC),
            )
            await comparison_session.save()

            SEVERITY_MAP = {"CHANGED": "medium", "ADDED": "high", "REMOVED": "high"}
            violations_to_save = []
            for marking_dict in non_matched:
                marking = CanvasMarking(**marking_dict)
                coords = None
                if marking.coordinates:
                    if isinstance(marking.coordinates, list):
                        if len(marking.coordinates) > 0 and not isinstance(
                            marking.coordinates[0], list
                        ):
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
                            f"Resolve discrepancy in '{marking.text_content}' against the reference drawing."
                        ),
                        source="full_ai_comparison",
                        confidence=0.80,
                        standard_reference=None,
                        affected_entities=(
                            [{"entity_id": marking.entity_id, "marker_shape": "BOX"}]
                            if marking.entity_id
                            else []
                        ),
                        coordinates=coords,
                    )
                )

            if violations_to_save:
                await AuditViolation.insert_many(violations_to_save)

            logger.info(
                f"[full_ai] Persisted {len(violations_to_save)} violations "
                f"(session {comparison_session.id}, score {comparison_score}%)."
            )
        except Exception as persist_err:
            logger.warning(f"[full_ai] Violation persistence failed (non-fatal): {persist_err}")

        # Write result payload to cache
        try:
            ComparisonCacheManager.set_cached_comparison(
                ref_drawing_id=str(ref_drawing.id),
                rev_drawing_id=str(rev_drawing.id),
                ref_hash=ref_drawing.file_hash,
                rev_hash=rev_drawing.file_hash,
                payload=comparison_response.model_dump(),
                method=method,
            )
        except Exception as cache_write_err:
            logger.warning(f"[full_ai] Failed to cache comparison response: {cache_write_err}")
