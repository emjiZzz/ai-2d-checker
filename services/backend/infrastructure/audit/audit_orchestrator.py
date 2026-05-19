import time
from datetime import datetime
from typing import Tuple
from ...logger import logger
from ...domain.models.drawing_document import DrawingDocument
from ...domain.models.standard_document import StandardDocument
from ...domain.models.standard_chunk import StandardChunk
from ...domain.models.audit_session import AuditSession
from ...domain.models.audit_violation import AuditViolation
from .rule_engine import RuleEngine
from .ai_engine import AIEngine
from .violation_detector import ViolationDetector
from .confidence import ConfidenceScorer

class AuditOrchestrator:
    """
    Orchestrates the drawing compliance audit.
    Manages operational lifecycles, executes rule checking and AI comparative analysis,
    calculates metrics, and saves results in MongoDB.
    """

    @staticmethod
    async def run_audit(drawing_id: str, standard_id: str, session_id: str) -> Tuple[AuditSession, int]:
        """
        Executes standard-based compliance auditing.
        Returns:
            session: Updated AuditSession document.
            violation_count: Total consolidated violations saved.
        """
        start_time = time.time()
        logger.info(f"Triggering standard compliance audit: Drawing {drawing_id} vs Standard {standard_id} (Session: {session_id})")

        # 1. Fetch matching models and validate status
        session = await AuditSession.get(session_id)
        if not session:
            raise FileNotFoundError(f"Target AuditSession not registered: {session_id}")

        drawing = await DrawingDocument.get(drawing_id)
        if not drawing:
            session.status = "failed"
            session.error_message = f"Drawing document not found: {drawing_id}"
            session.completed_at = datetime.utcnow()
            await session.save()
            raise FileNotFoundError(session.error_message)

        standard = await StandardDocument.get(standard_id)
        if not standard:
            session.status = "failed"
            session.error_message = f"Standard document not found: {standard_id}"
            session.completed_at = datetime.utcnow()
            await session.save()
            raise FileNotFoundError(session.error_message)

        # 2. Update session state to processing
        session.status = "processing"
        session.started_at = datetime.utcnow()
        await session.save()

        try:
            # 3. Retrieve standard grounded sections (RAG chunks)
            grounding_chunks = await StandardChunk.find(StandardChunk.standard_id == standard_id).to_list()
            logger.info(f"Retrieved {len(grounding_chunks)} grounded chunks from Standard '{standard.name}'")

            # 4. Trigger Deterministic CAD Rule Engine
            rule_start = time.time()
            rule_violations = await RuleEngine.validate_drawing(session_id, drawing)
            rule_duration = time.time() - rule_start
            logger.info(f"CAD Rule Engine complete in {rule_duration:.4f}s. Detected {len(rule_violations)} infractions.")

            # 5. Trigger Grounded Gemini Vision Orchestrator
            ai_start = time.time()
            ai_violations = await AIEngine.audit_drawing(session_id, drawing, standard, grounding_chunks)
            ai_duration = time.time() - ai_start
            logger.info(f"Gemini Vision Orchestrator complete in {ai_duration:.4f}s. Detected {len(ai_violations)} infractions.")

            # 6. Consolidate and Deduplicate Violations
            consolidated = ViolationDetector.consolidate_violations(rule_violations, ai_violations)

            # 7. Compute Scores
            compliance = ConfidenceScorer.calculate_compliance_score(consolidated)
            confidence = ConfidenceScorer.calculate_average_confidence(consolidated)

            # 8. Save Violations to MongoDB
            if consolidated:
                # Add session_id reference and save
                for v in consolidated:
                    v.audit_session_id = session_id
                await AuditViolation.insert_many(consolidated)

            # 9. Update Session timings and statistics
            total_duration = time.time() - start_time
            session.status = "completed"
            session.compliance_score = compliance
            session.confidence_score = confidence
            session.timings = {
                "rule_engine_seconds": round(rule_duration, 4),
                "ai_engine_seconds": round(ai_duration, 4),
                "total_seconds": round(total_duration, 4)
            }
            session.diagnostics = {
                "grounding_chunks_evaluated": len(grounding_chunks),
                "rule_violations_count": len(rule_violations),
                "ai_violations_count": len(ai_violations),
                "consolidated_violations_count": len(consolidated)
            }
            session.completed_at = datetime.utcnow()
            await session.save()

            logger.info(f"Compliance audit complete for session {session_id} in {total_duration:.4f}s. Compliance: {compliance}%.")
            return session, len(consolidated)

        except Exception as e:
            logger.error(f"Audit pipeline execution crashed: {str(e)}")
            session.status = "failed"
            session.error_message = str(e)
            session.completed_at = datetime.utcnow()
            await session.save()
            raise
