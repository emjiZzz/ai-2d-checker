
from ...domain.models.audit_violation import AuditViolation
from ...logger import logger


class ViolationDetector:
    """
    Consolidates, normalizes, and deduplicates engineering standard violations.
    Combines rule-based checks and AI comparative analysis outputs.
    """

    @staticmethod
    def consolidate_violations(
        rule_violations: list[AuditViolation],
        ai_violations: list[AuditViolation]
    ) -> list[AuditViolation]:
        logger.info(f"Consolidating {len(rule_violations)} rule violations and {len(ai_violations)} AI violations.")
        
        consolidated: list[AuditViolation] = []
        seen_keys = set()

        # Merge and deduplicate
        for v in rule_violations + ai_violations:
            # Construct a uniqueness fingerprint based on category, description, and source
            fingerprint = f"{v.category}:{v.severity}:{hash(v.description)}"
            
            if fingerprint in seen_keys:
                continue

            seen_keys.add(fingerprint)
            
            # Basic validation/normalization of severity ranges
            if v.severity not in ("critical", "high", "medium", "low"):
                v.severity = "medium"

            # Capitalize standard categories for front-end visual aesthetic
            v.category = v.category.replace("_", " ").title()
            
            # Ensure recommendations end with standard formatting punctuation
            if not v.recommendation.endswith("."):
                v.recommendation += "."

            consolidated.append(v)

        logger.info(f"Deduplication complete. Retained {len(consolidated)} final unique drawing violations.")
        return consolidated
