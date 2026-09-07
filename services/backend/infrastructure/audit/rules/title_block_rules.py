from typing import List
from ....domain.models.audit_violation import AuditViolation
from .rule_base import RuleContext

def validate_title_block_placeholders(context: RuleContext) -> List[AuditViolation]:
    violations: List[AuditViolation] = []
    texts = context.entities_by_type.get("text", [])
    placeholders = {"n/a", "unknown", "insert", "placeholder", "company name", "designer", "---", "xxxx"}
    
    for txt in texts:
        val = context.get_text_content(txt)
        val_lower = val.lower()
        
        if any(p in val_lower for p in placeholders) or len(val) == 0:
            if txt.layer.lower() in ("am_bor", "border", "title", "title_block"):
                violations.append(
                    AuditViolation(
                        audit_session_id=context.audit_session_id,
                        severity="high",
                        category="empty_title_block",
                        description=f"Title block metadata placeholder detected: '{val}'",
                        recommendation="Fill all title block fields (Drawn by, Approved, Drawing Number) with authentic production values.",
                        source="rule_engine",
                        confidence=1.0,
                        affected_entities=[{"id": str(txt.id), "type": "text"}],
                        coordinates=txt.geometry.get("coordinates") or txt.geometry.get("insert")
                    )
                )
    return violations

def validate_title_block_completeness(context: RuleContext) -> List[AuditViolation]:
    violations: List[AuditViolation] = []
    REQUIRED_TITLE_FIELDS = {
        "SCALE": ["scale", "尺度"],
        "DWG_NO": ["dwg. no", "図面番号", "drawing number"],
        "TITLE": ["title", "名称"],
        "DESIGNED": ["designed", "設計", "drawn", "作成"],
        "APPROVED": ["approved", "承認", "checked", "検図"],
        "MATERIAL": ["material", "材質", "材料"],
        "REVISION": ["rev", "revision", "改訂"],
        "DATE": ["date", "日付"]
    }

    found_fields = set()
    for txt_val in context.all_text_contents:
        val_lower = txt_val.lower()
        for field_key, keywords in REQUIRED_TITLE_FIELDS.items():
            if any(kw in val_lower for kw in keywords):
                found_fields.add(field_key)

    missing_fields = set(REQUIRED_TITLE_FIELDS.keys()) - found_fields
    if missing_fields:
        violations.append(
            AuditViolation(
                audit_session_id=context.audit_session_id,
                severity="high",
                category="incomplete_title_block",
                description=f"Drawing title block is missing mandatory engineering metadata fields: {', '.join(missing_fields)}.",
                recommendation="Populate all standard title block attributes (Scale, Revision, Drawn, Approved) prior to drawing release.",
                source="rule_engine",
                confidence=0.95,
                standard_reference="ISO 7200 (Technical Product Documentation - Title Blocks)"
            )
        )
    return violations

def validate_empty_block_attributes(context: RuleContext) -> List[AuditViolation]:
    violations: List[AuditViolation] = []
    blocks = context.entities_by_type.get("block", [])
    
    for blk in blocks:
        attrs = blk.properties.get("attributes", {}) if blk.properties else {}
        for tag, val in attrs.items():
            if val is not None and str(val).strip() == "":
                if blk.layer.lower() in ("am_bor", "border", "title", "title_block"):
                    violations.append(
                        AuditViolation(
                            audit_session_id=context.audit_session_id,
                            severity="medium",
                            category="empty_block_attribute",
                            description=f"Empty block attribute tag detected in title block layout: '{tag}'",
                            recommendation=f"Provide a valid value for title block attribute block tag '{tag}'.",
                            source="rule_engine",
                            confidence=0.9,
                            affected_entities=[{"id": str(blk.id), "type": "block"}],
                            standard_reference="ISO 7200 (Title Blocks)"
                        )
                    )
    return violations
