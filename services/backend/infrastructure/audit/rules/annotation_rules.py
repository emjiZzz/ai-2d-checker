import re
from typing import List
from ....domain.models.audit_violation import AuditViolation
from .rule_base import RuleContext

def validate_orphan_annotations(context: RuleContext) -> List[AuditViolation]:
    violations: List[AuditViolation] = []
    texts = context.entities_by_type.get("text", [])
    
    for txt in texts:
        val = context.get_text_content(txt)
        if not val:
            violations.append(
                AuditViolation(
                    audit_session_id=context.audit_session_id,
                    severity="low",
                    category="orphan_annotation",
                    description="Empty drawing annotation block detected with no textual details.",
                    recommendation="Remove redundant empty text annotations from drawing workspace.",
                    source="rule_engine",
                    confidence=1.0,
                    affected_entities=[{"id": str(txt.id), "type": "text"}]
                )
            )
    return violations

def validate_gdt_frames(context: RuleContext) -> List[AuditViolation]:
    violations: List[AuditViolation] = []
    tolerances = context.entities_by_type.get("tolerance", [])
    gdt_symbols = ["⊙", "⌖", "⊥", "◎", "⊘", "∥", "↗", "⌯", "⌒", "⏊", "⌯"]
    gdt_text_pattern = re.compile(r'(\|[a-zA-Z0-9\.\s⌀/]+\|[a-zA-Z0-9\.\s]+\|?)')
    
    for tol in tolerances:
        content = context.get_text_content(tol)
        if content:
            if not any(sym in content for sym in gdt_symbols) and not gdt_text_pattern.search(content):
                violations.append(
                    AuditViolation(
                        audit_session_id=context.audit_session_id,
                        severity="high",
                        category="malformed_gdt_frame",
                        description=f"GD&T feature control frame has non-standard contents: '{content}'",
                        recommendation="Ensure GD&T frames contain standard symbols (position, parallelism, perpendicularity) and valid datum references.",
                        source="rule_engine",
                        confidence=0.9,
                        affected_entities=[{"id": str(tol.id), "type": "tolerance"}],
                        standard_reference="ISO 1101 (GD&T - Geometrical Tolerancing)"
                    )
                )
    return violations

def validate_hole_callouts(context: RuleContext) -> List[AuditViolation]:
    violations: List[AuditViolation] = []
    hole_pattern = re.compile(r'(?:⌀|Ø|%%c)\s*(\d+(?:\.\d+)?)', re.IGNORECASE)
    valid_hole_spec = re.compile(
        r'(?:⌀|Ø|%%c)\s*\d+(?:\.\d+)?'                     # Diameter
        r'(?:\s*[A-H][1-9]\d*)?'                            # Optional standard tolerance class (H7, f6)
        r'(?:\s*[xX✕ラ]\s*\d+)?'                             # Optional depth/length multiplier
        r'(?:\s*(?:deep|depth|▽|⌴|thru|通シ|キリ))?',          # Depth description
        re.IGNORECASE
    )
    
    for txt_val in context.all_text_contents:
        if hole_pattern.search(txt_val):
            if len(txt_val.strip()) > 1 and not valid_hole_spec.search(txt_val):
                violations.append(
                    AuditViolation(
                        audit_session_id=context.audit_session_id,
                        severity="medium",
                        category="invalid_hole_callout",
                        description=f"Non-standard diameter hole machining callout formatting: '{txt_val}'",
                        recommendation="Match standard callout formatting: Ø[Diameter][Tolerance Class][x Depth] or Thru.",
                        source="rule_engine",
                        confidence=0.85,
                        standard_reference="ISO 129-1 (Principles and Presentation of Dimensioning)"
                    )
                )
    return violations

def validate_text_heights(context: RuleContext) -> List[AuditViolation]:
    violations: List[AuditViolation] = []
    texts = context.entities_by_type.get("text", [])
    standard_heights = {2.5, 3.5, 5.0, 7.0, 10.0, 14.0}
    non_std_font_count = 0
    
    for txt in texts:
        h = txt.properties.get("height", 2.5) if txt.properties else 2.5
        if txt.properties and txt.properties.get("layout_space", "model").lower() != "model":
            continue
            
        if not any(abs(h - std) < 0.1 for std in standard_heights):
            non_std_font_count += 1
            if non_std_font_count <= 3:
                violations.append(
                    AuditViolation(
                        audit_session_id=context.audit_session_id,
                        severity="low",
                        category="non_standard_text_height",
                        description=f"Text annotation height '{h:.2f} mm' violates drafting visibility guidelines.",
                        recommendation="Set text annotation sizes to standardized ISO values: 2.5mm, 3.5mm, 5.0mm, or 7.0mm.",
                        source="rule_engine",
                        confidence=0.9,
                        affected_entities=[{"id": str(txt.id), "type": "text"}],
                        standard_reference="ISO 3098 (Technical Drawings - Lettering)"
                    )
                )
    return violations

def validate_center_lines(context: RuleContext) -> List[AuditViolation]:
    violations: List[AuditViolation] = []
    circles = context.entities_by_type.get("circle", [])
    
    large_circles = [c for c in circles if c.properties.get("radius", 0) > 2.0]
    if large_circles:
        has_center_lines = any("center" in (e.layer or "").lower() for e in context.entities)
        if not has_center_lines:
            violations.append(
                AuditViolation(
                    audit_session_id=context.audit_session_id,
                    severity="medium",
                    category="missing_center_lines",
                    description=f"Drawing contains {len(large_circles)} concentric cylindrical features but no center-line geometries.",
                    recommendation="Draw dash-dot center lines (alternating long/short dashes) indicating axes of symmetry.",
                    source="rule_engine",
                    confidence=0.8,
                    standard_reference="ISO 128-20 (Technical Drawings - General Principles of Presentation)"
                )
            )
    return violations

def validate_projection_notes(context: RuleContext) -> List[AuditViolation]:
    violations: List[AuditViolation] = []
    projection_note = any("projection" in val.lower() or "angle" in val.lower() or "角法" in val for val in context.all_text_contents)
    
    if not projection_note:
        violations.append(
            AuditViolation(
                audit_session_id=context.audit_session_id,
                severity="high",
                category="missing_projection_type",
                description="No projection system declaration detected (First Angle vs Third Angle).",
                recommendation="Declare projection system in notes or insert the ISO projection symbol (cone frustum diagram).",
                source="rule_engine",
                confidence=0.85,
                standard_reference="ISO 128-30 (Technical Drawings - Projection Methods)"
            )
        )
    return violations

def validate_threads(context: RuleContext) -> List[AuditViolation]:
    violations: List[AuditViolation] = []
    thread_pattern = re.compile(r'\b(M\s*\d+)\b', re.IGNORECASE)
    
    for txt_val in context.all_text_contents:
        for thread_match in thread_pattern.finditer(txt_val):
            spec = thread_match.group(1).upper()
            if len(txt_val.strip()) <= 4:
                violations.append(
                    AuditViolation(
                        audit_session_id=context.audit_session_id,
                        severity="medium",
                        category="unclear_thread_specification",
                        description=f"Fastener screw thread specified solely as coarse profile: '{txt_val}'",
                        recommendation="Explicitly qualify thread pitch, class, or depth specs (e.g. M12x1.75 - 6g or M12 THRU).",
                        source="rule_engine",
                        confidence=0.8,
                        standard_reference="ISO 965 (ISO General Purpose Metric Screw Threads)"
                    )
                )
    return violations

def validate_revision_clouds(context: RuleContext) -> List[AuditViolation]:
    violations: List[AuditViolation] = []
    has_revision_spec = any(re.search(r"rev\s*[B-Z]", val.lower()) for val in context.all_text_contents)
    
    if has_revision_spec:
        has_rev_cloud_layer = any("rev" in (e.layer or "").lower() or "cloud" in (e.layer or "").lower() for e in context.entities)
        if not has_rev_cloud_layer:
            violations.append(
                AuditViolation(
                    audit_session_id=context.audit_session_id,
                    severity="medium",
                    category="missing_revision_clouds",
                    description="Drawing title block lists revised status but no revision clouds mark sheet modifications.",
                    recommendation="Surround all updated geometric or annotative details with revision cloud layers (ISO 7573).",
                    source="rule_engine",
                    confidence=0.8,
                    standard_reference="ISO 7573 (Technical Drawings - Item Lists)"
                )
            )
    return violations

def validate_surface_roughness(context: RuleContext) -> List[AuditViolation]:
    violations: List[AuditViolation] = []
    tight_tolerance_exists = any(re.search(r'\b[Hh][6-8]\b', val) for val in context.all_text_contents)
    has_roughness_spec = any("ra" in val.lower() or "ry" in val.lower() or "rz" in val.lower() or "roughness" in val.lower() or "仕上げ" in val for val in context.all_text_contents)
    
    if tight_tolerance_exists and not has_roughness_spec:
        violations.append(
            AuditViolation(
                audit_session_id=context.audit_session_id,
                severity="medium",
                category="missing_surface_roughness",
                description="Drawing requests tight machining tolerances (H6/H7) but lacks surface roughness indicators (Ra, Rz).",
                recommendation="Explicitly stamp surface finish roughness standards (e.g., Ra 3.2 or Ra 1.6) on precision faces.",
                source="rule_engine",
                confidence=0.85,
                standard_reference="ISO 1302 (Geometrical Product Specifications (GPS) - Indication of Surface Texture)"
            )
        )
    return violations
