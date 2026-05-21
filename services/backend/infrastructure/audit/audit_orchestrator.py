import time
from datetime import datetime, timezone
from typing import Tuple, Optional
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
    async def run_audit(drawing_id: str, standard_id: Optional[str], session_id: str, client_name: Optional[str] = None) -> Tuple[AuditSession, int]:
        """
        Executes standard-based compliance auditing.
        Returns:
            session: Updated AuditSession document.
            violation_count: Total consolidated violations saved.
        """
        start_time = time.time()
        logger.info(f"Triggering standard compliance audit: Drawing {drawing_id} vs Standard {standard_id}, Client {client_name} (Session: {session_id})")

        # 1. Fetch matching models and validate status
        session = await AuditSession.get(session_id)
        if not session:
            raise FileNotFoundError(f"Target AuditSession not registered: {session_id}")

        drawing = await DrawingDocument.get(drawing_id)
        if not drawing:
            session.status = "failed"
            session.error_message = f"Drawing document not found: {drawing_id}"
            session.completed_at = datetime.now(timezone.utc)
            await session.save()
            raise FileNotFoundError(session.error_message)

        # Retrieve the applicable standards
        standards_to_evaluate = []
        if client_name:
            # 1. Fetch Universal standards (scope == "universal")
            universal_stds = await StandardDocument.find(StandardDocument.scope == "universal").to_list()
            standards_to_evaluate.extend(universal_stds)
            # 2. Fetch Client-Specific standards (scope == "client_specific" and client_name == client_name)
            client_stds = await StandardDocument.find(
                StandardDocument.scope == "client_specific",
                StandardDocument.client_name == client_name.upper()
            ).to_list()
            standards_to_evaluate.extend(client_stds)
        elif standard_id:
            standard = await StandardDocument.get(standard_id)
            if standard:
                standards_to_evaluate.append(standard)

        if not standards_to_evaluate:
            session.status = "failed"
            session.error_message = f"No engineering standards or rules matched for client '{client_name}' or standard '{standard_id}'."
            session.completed_at = datetime.now(timezone.utc)
            await session.save()
            raise FileNotFoundError(session.error_message)

        # For AI engine calls, use primary client standard or consolidated mock as standard parameter
        primary_standard = standards_to_evaluate[0]

        # 2. Update session state to processing
        session.status = "processing"
        session.started_at = datetime.now(timezone.utc)
        await session.save()

        try:
            # 3. Retrieve standard grounded sections (RAG chunks) for all matching standards
            standard_ids = [str(s.id) for s in standards_to_evaluate]
            grounding_chunks = await StandardChunk.find({"standard_id": {"$in": standard_ids}}).to_list()
            logger.info(f"Retrieved {len(grounding_chunks)} grounded chunks from {len(standards_to_evaluate)} applicable Standards.")

            # 4. Trigger Deterministic CAD Rule Engine
            rule_start = time.time()
            rule_violations = await RuleEngine.validate_drawing(session_id, drawing)
            rule_duration = time.time() - rule_start
            logger.info(f"CAD Rule Engine complete in {rule_duration:.4f}s. Detected {len(rule_violations)} infractions.")

            # 5. Trigger Grounded Gemini Vision Orchestrator
            ai_start = time.time()
            ai_violations = await AIEngine.audit_drawing(session_id, drawing, primary_standard, grounding_chunks)
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
            session.completed_at = datetime.now(timezone.utc)
            await session.save()

            logger.info(f"Compliance audit complete for session {session_id} in {total_duration:.4f}s. Compliance: {compliance}%.")
            return session, len(consolidated)

        except Exception as e:
            logger.error(f"Audit pipeline execution crashed: {str(e)}")
            session.status = "failed"
            session.error_message = str(e)
            session.completed_at = datetime.now(timezone.utc)
            await session.save()
            raise
