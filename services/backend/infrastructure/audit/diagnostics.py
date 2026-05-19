import time
from typing import Any, Dict, List
from ...logger import logger
from ...domain.models.audit_session import AuditSession
from ...domain.models.audit_violation import AuditViolation

class AuditDiagnostics:
    """
    Compiles detailed runtime audits metrics, timing maps,
    severity distributions, and confidence analytics.
    """

    @staticmethod
    async def get_session_diagnostics(session_id: str) -> Dict[str, Any]:
        """
        Gathers live DB records to present a performance and analytics snapshot.
        """
        logger.info(f"Aggregating audit diagnostics reports for session: {session_id}")
        
        session = await AuditSession.get(session_id)
        if not session:
            raise FileNotFoundError(f"Audit session not found in database: {session_id}")

        violations = await AuditViolation.find(AuditViolation.audit_session_id == session_id).to_list()

        # Distribution maps
        severity_counts = {
            "critical": 0,
            "high": 0,
            "medium": 0,
            "low": 0
        }
        source_counts = {
            "rule_engine": 0,
            "gemini_vision": 0
        }

        for v in violations:
            sev = v.severity.lower()
            if sev in severity_counts:
                severity_counts[sev] += 1
            else:
                severity_counts[sev] = 1
            
            src = v.source.lower()
            if src in source_counts:
                source_counts[src] += 1
            else:
                source_counts[src] = 1

        total_violations = len(violations)
        confidence_distribution = [v.confidence for v in violations]
        
        return {
            "success": True,
            "session_id": session_id,
            "status": session.status,
            "overall_compliance_score": session.compliance_score,
            "overall_confidence_score": session.confidence_score,
            "execution_durations": session.timings,
            "violations_summary": {
                "total": total_violations,
                "by_severity": severity_counts,
                "by_source": source_counts
            },
            "confidence_spread": {
                "min": min(confidence_distribution) if violations else 0.95,
                "max": max(confidence_distribution) if violations else 0.95,
                "average": session.confidence_score or 0.95
            },
            "diagnostics_timestamp": session.completed_at or session.created_at
        }
