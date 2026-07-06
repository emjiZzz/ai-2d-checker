from typing import Any

from ...logger import logger


class ReportBuilder:
    """
    Orchestrates pulling AuditViolations, ReviewSession notes, and diagnostics 
    into a cohesive JSON schema that can be handed off to the PDFGenerator.
    """
    
    @staticmethod
    def build_report_schema(session_id: str, violations: list[Any], annotations: list[Any]) -> dict[str, Any]:
        """
        Compiles the full report schema.
        """
        logger.info(f"Building report schema for session {session_id} with {len(violations)} violations.")
        
        schema = {
            "title": "Engineering Compliance Report",
            "session_id": session_id,
            "executive_summary": "Auto-generated compliance audit.",
            "violations": [{"id": getattr(v, 'id', str(v))} for v in violations],
            "annotations": [{"id": getattr(a, 'id', str(a))} for a in annotations]
        }
        
        return schema
