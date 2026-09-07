from typing import List
from ....domain.models.audit_violation import AuditViolation
from .rule_base import RuleContext

def validate_units(context: RuleContext) -> List[AuditViolation]:
    violations: List[AuditViolation] = []
    meas = context.drawing.metadata.get("measurement", -1)
    
    if meas == -1:
        violations.append(
            AuditViolation(
                audit_session_id=context.audit_session_id,
                severity="medium",
                category="unsupported_units",
                description="Drawing measurement system is undefined ($MEASUREMENT header missing).",
                recommendation="Explicitly define unit standards (Metric = 1, Imperial = 0) inside CAD workspace parameters.",
                source="rule_engine",
                confidence=1.0,
                standard_reference="ISO 1000 (SI units and recommendations)"
            )
        )
    return violations
