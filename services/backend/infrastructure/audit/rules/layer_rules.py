import re
from typing import List
from ....domain.models.audit_violation import AuditViolation
from .rule_base import RuleContext

def validate_layers(context: RuleContext) -> List[AuditViolation]:
    violations: List[AuditViolation] = []
    
    STANDARD_LAYERS = {"0", "defpoints", "am_0", "am_1", "am_bor", "am_txt", "am_dim", "border", "title", "dimensions", "geometry"}
    FORBIDDEN_LAYER_PATTERNS = [r"temp", r"draft", r"delete", r"backup", r"test", r"work", r"junk"]

    for ent in context.entities:
        layer_lower = ent.layer.lower()
        
        # Check forbidden layer names
        for pattern in FORBIDDEN_LAYER_PATTERNS:
            if re.search(pattern, layer_lower):
                violations.append(
                    AuditViolation(
                        audit_session_id=context.audit_session_id,
                        severity="medium",
                        category="forbidden_layer_name",
                        description=f"Entity type '{ent.entity_type}' resides on an unauthorized non-production layer: '{ent.layer}'",
                        recommendation="Remove scratchpad layers before submitting production drawings.",
                        source="rule_engine",
                        confidence=1.0,
                        affected_entities=[{"id": str(ent.id), "type": ent.entity_type}],
                        coordinates=ent.geometry.get("coordinates") or ent.geometry.get("start")
                    )
                )
                break
        
        # Check invalid layer names
        if layer_lower not in STANDARD_LAYERS and not any(re.search(pat, layer_lower) for pat in FORBIDDEN_LAYER_PATTERNS):
            # Only flag once per unique layer name to prevent spamming
            if not any(v.description.endswith(f"'{ent.layer}'") for v in violations if v.category == "invalid_layer"):
                violations.append(
                    AuditViolation(
                        audit_session_id=context.audit_session_id,
                        severity="low",
                        category="invalid_layer",
                        description=f"Drafting standard violation: Entity rests on non-standard layer: '{ent.layer}'",
                        recommendation=f"Reassign graphics from layer '{ent.layer}' to standard naming structures (0, AM_0, AM_DIM).",
                        source="rule_engine",
                        confidence=1.0,
                        standard_reference="ISO 13567 (CAD Layer Guidelines)"
                    )
                )
    return violations

def validate_duplicates(context: RuleContext) -> List[AuditViolation]:
    violations: List[AuditViolation] = []
    lines = context.entities_by_type.get("line", [])
    
    seen_lines = []
    duplicate_count = 0
    for line in lines:
        start = line.geometry.get("start")
        end = line.geometry.get("end")
        if not start or not end:
            continue
        
        # Standardize vectors
        coords = sorted([tuple(start[:2]), tuple(end[:2])])
        coords_key = (coords[0], coords[1])
        
        if coords_key in seen_lines:
            duplicate_count += 1
            if duplicate_count <= 5: # Limit reporting count to avoid violation flood
                violations.append(
                    AuditViolation(
                        audit_session_id=context.audit_session_id,
                        severity="medium",
                        category="duplicate_entities",
                        description="Identical duplicate line entity found overlapping at exact same spatial vector coordinates.",
                        recommendation="Purge overlapping coincident lines using CAD 'OVERKILL' tools.",
                        source="rule_engine",
                        confidence=1.0,
                        affected_entities=[{"id": str(line.id), "type": "line"}],
                        coordinates=[start[:2], end[:2]]
                    )
                )
        else:
            seen_lines.append(coords_key)
            
    return violations
