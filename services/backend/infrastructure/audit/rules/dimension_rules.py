import re
from typing import List
from ....domain.models.audit_violation import AuditViolation
from .rule_base import RuleContext

def validate_dimensions_presence(context: RuleContext) -> List[AuditViolation]:
    violations: List[AuditViolation] = []
    lines = context.entities_by_type.get("line", [])
    circles = context.entities_by_type.get("circle", [])
    arcs = context.entities_by_type.get("arc", [])
    polylines = context.entities_by_type.get("polyline", [])
    dimensions = context.entities_by_type.get("dimension", [])
    
    total_geometry = len(lines) + len(circles) + len(arcs) + len(polylines)
    
    if total_geometry > 10 and len(dimensions) < 2:
        violations.append(
            AuditViolation(
                audit_session_id=context.audit_session_id,
                severity="high",
                category="missing_dimensions",
                description=f"Drawing contains {total_geometry} geometric shapes but has only {len(dimensions)} dimensions.",
                recommendation="Ensure all engineering features (shaft lengths, diameters, slot widths) are explicitly dimensioned for manufacturing.",
                source="rule_engine",
                confidence=1.0,
                standard_reference="ISO 129-1 (Principles of Dimensioning)"
            )
        )
    return violations

def validate_scales_standard(context: RuleContext) -> List[AuditViolation]:
    violations: List[AuditViolation] = []
    texts = context.entities_by_type.get("text", [])
    STANDARD_SCALES = {"1:1", "1:2", "1:5", "1:10", "1:20", "1:50", "1:100", "2:1", "5:1", "10:1"}
    
    for txt in texts:
        val = context.get_text_content(txt)
        match = re.search(r"scale\s*:?\s*(\d+\s*[:/]\s*\d+)", val, re.IGNORECASE)
        if match:
            scale_val = match.group(1).replace(" ", "").replace("/", ":")
            if scale_val not in STANDARD_SCALES:
                violations.append(
                    AuditViolation(
                        audit_session_id=context.audit_session_id,
                        severity="medium",
                        category="invalid_scale",
                        description=f"Non-standard drafting scale ratio declared: '{scale_val}'",
                        recommendation="Only use standard ISO scale ratios e.g., 1:1, 1:2, 1:5, 1:10, 2:1, 5:1.",
                        source="rule_engine",
                        confidence=1.0,
                        affected_entities=[{"id": str(txt.id), "type": "text"}],
                        standard_reference="ISO 5455 (Technical Drawings - Scales)"
                    )
                )
    return violations

def validate_scales_associative(context: RuleContext) -> List[AuditViolation]:
    violations: List[AuditViolation] = []
    dimensions = context.entities_by_type.get("dimension", [])
    
    # Find scale
    declared_scale = 1.0
    for txt_val in context.all_text_contents:
        match = re.search(r"scale\s*:?\s*(\d+)\s*[:/]\s*(\d+)", txt_val, re.IGNORECASE)
        if match:
            n1, n2 = float(match.group(1)), float(match.group(2))
            if n2 > 0:
                declared_scale = n1 / n2
                break
                
    mismatch_count = 0
    for dim in dimensions:
        text_val = context.get_text_content(dim)
        meas = dim.properties.get("measurement") if dim.properties else None
        if meas is not None and text_val:
            try:
                clean_text_val = re.sub(r'[^\d\.]', '', text_val)
                if clean_text_val:
                    stated_val = float(clean_text_val)
                    if stated_val > 0:
                        expected_len = meas * declared_scale
                        ratio = stated_val / expected_len if expected_len > 0 else 1.0
                        if not (0.95 <= ratio <= 1.05) and stated_val != round(expected_len):
                            mismatch_count += 1
                            if mismatch_count <= 2:
                                violations.append(
                                    AuditViolation(
                                        audit_session_id=context.audit_session_id,
                                        severity="high",
                                        category="dimension_scale_mismatch",
                                        description=f"Dimension callout text '{text_val}' differs significantly from physical entity vector size ({stated_val:.2f} vs {expected_len:.2f} expected).",
                                        recommendation="Do not override text annotations manually. Match drawings scale or update associative geometries.",
                                        source="rule_engine",
                                        confidence=0.9,
                                        affected_entities=[{"id": str(dim.id), "type": "dimension"}],
                                        standard_reference="ISO 5455 (Technical Drawings - Scales)"
                                    )
                                )
            except ValueError:
                pass
    return violations

def validate_general_tolerances(context: RuleContext) -> List[AuditViolation]:
    violations: List[AuditViolation] = []
    tolerance_declarations = ["iso 2768", "jis b 0405", "asme y14.5", "din 7168", "一般公差", "general tolerance"]
    full_text_aggregate = " ".join(context.all_text_contents).lower()
    has_tolerance_standard = any(decl in full_text_aggregate for decl in tolerance_declarations)
    
    if not has_tolerance_standard:
        violations.append(
            AuditViolation(
                audit_session_id=context.audit_session_id,
                severity="high",
                category="missing_general_tolerances",
                description="No default general tolerance standard (e.g., ISO 2768-m, JIS B 0405) declared in notes block.",
                recommendation="Explicitly append the tolerance standards block to drawing notes (e.g. 'General Tolerances per ISO 2768-m').",
                source="rule_engine",
                confidence=0.95,
                standard_reference="ISO 2768 (General Tolerances for Linear and Angular Dimensions)"
            )
        )
    return violations
