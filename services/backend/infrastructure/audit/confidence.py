
from ...domain.models.audit_violation import AuditViolation
from ...logger import logger


class ConfidenceScorer:
    """
    Computes mathematical compliance scores and confidence ratings for CAD audits.
    Quantifies the severity impact of structural and comparative infractions.
    """

    @staticmethod
    def calculate_compliance_score(violations: list[AuditViolation]) -> float:
        """
        Deducts points from 100.0 based on weighted infraction severities.
        Returns a value bounded in [0.0, 100.0].
        """
        score = 100.0
        
        # Severity weights
        weights = {
            "critical": 25.0,
            "high": 15.0,
            "medium": 8.0,
            "low": 3.0
        }

        for v in violations:
            deduction = weights.get(v.severity.lower(), 5.0)
            score -= deduction

        final_score = max(0.0, min(100.0, score))
        logger.info(f"Computed drawing compliance score: {final_score:.2f}% based on {len(violations)} violations.")
        return round(final_score, 2)

    @staticmethod
    def calculate_average_confidence(violations: list[AuditViolation]) -> float:
        """
        Computes the statistical average of all violation confidence weights.
        If no violations exist, defaults to a high grounding confidence of 0.95.
        """
        if not violations:
            return 0.95

        total_confidence = sum(v.confidence for v in violations)
        avg = total_confidence / len(violations)
        
        final_confidence = max(0.0, min(1.0, avg))
        logger.info(f"Computed aggregate audit matching confidence: {final_confidence:.4f}")
        return round(final_confidence, 4)
