import re
from typing import Any, Dict, List
from ...logger import logger
from ...domain.models.drawing_document import DrawingDocument
from ...domain.models.extracted_entity import ExtractedEntity
from ...domain.models.audit_violation import AuditViolation

class RuleEngine:
    """
    Deterministic CAD validation engine.
    Executes structural drafting rules on extracted CAD graphic primitives
    and metadata records without requiring AI models.
    """

    @staticmethod
    async def validate_drawing(audit_session_id: str, drawing: DrawingDocument) -> List[AuditViolation]:
        logger.info(f"Initiating rule-based CAD compliance audit for drawing: {drawing.file_name}")
        violations: List[AuditViolation] = []

        # 1. Fetch all associated extracted graphic primitives from database
        entities = await ExtractedEntity.find(ExtractedEntity.drawing_id == str(drawing.id)).to_list()

        # Group entities by type
        entities_by_type: Dict[str, List[ExtractedEntity]] = {}
        for ent in entities:
            entities_by_type.setdefault(ent.entity_type, []).append(ent)

        # Standard layers allowlist
        STANDARD_LAYERS = {"0", "defpoints", "am_0", "am_1", "am_bor", "am_txt", "am_dim", "border", "title", "dimensions", "geometry"}
        FORBIDDEN_LAYER_PATTERNS = [r"temp", r"draft", r"delete", r"backup", r"test", r"work", r"junk"]
        STANDARD_SCALES = {"1:1", "1:2", "1:5", "1:10", "1:20", "1:50", "1:100", "2:1", "5:1", "10:1"}

        lines = entities_by_type.get("line", [])
        circles = entities_by_type.get("circle", [])
        arcs = entities_by_type.get("arc", [])
        polylines = entities_by_type.get("polyline", [])
        dimensions = entities_by_type.get("dimension", [])
        texts = entities_by_type.get("text", [])
        blocks = entities_by_type.get("block", [])

        total_geometry = len(lines) + len(circles) + len(arcs) + len(polylines)

        # Rule 1: Missing Dimensions
        # If geometric primitives exist, drawing must have dimensions to define sizing
        if total_geometry > 10 and len(dimensions) < 2:
            violations.append(
                AuditViolation(
                    audit_session_id=audit_session_id,
                    severity="high",
                    category="missing_dimensions",
                    description=f"Drawing contains {total_geometry} geometric shapes but has only {len(dimensions)} dimensions.",
                    recommendation="Ensure all engineering features (shaft lengths, diameters, slot widths) are explicitly dimensioned for manufacturing.",
                    source="rule_engine",
                    confidence=1.0,
                    standard_reference="ISO 129-1 (Principles of Dimensioning)"
                )
            )

        # Rule 2 & 3: Invalid & Forbidden Layers
        for ent in entities:
            layer_lower = ent.layer.lower()
            
            # Check forbidden layer names
            for pattern in FORBIDDEN_LAYER_PATTERNS:
                if re.search(pattern, layer_lower):
                    violations.append(
                        AuditViolation(
                            audit_session_id=audit_session_id,
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
                            audit_session_id=audit_session_id,
                            severity="low",
                            category="invalid_layer",
                            description=f"Drafting standard violation: Entity rests on non-standard layer: '{ent.layer}'",
                            recommendation=f"Reassign graphics from layer '{ent.layer}' to standard naming structures (0, AM_0, AM_DIM).",
                            source="rule_engine",
                            confidence=1.0,
                            standard_reference="ISO 13567 (CAD Layer Guidelines)"
                        )
                    )

        # Rule 4: Empty / Placeholder Title Blocks
        # Scans all text entities looking for default/placeholder title labels
        placeholders = {"n/a", "unknown", "insert", "placeholder", "company name", "designer", "---", "xxxx"}
        for txt in texts:
            val = txt.properties.get("value", "").strip()
            val_lower = val.lower()
            
            # If the text itself matches a placeholder
            if any(p in val_lower for p in placeholders) or len(val) == 0:
                # If it resides on standard border/text layer, flag it
                if txt.layer.lower() in ("am_bor", "border", "title"):
                    violations.append(
                        AuditViolation(
                            audit_session_id=audit_session_id,
                            severity="high",
                            category="empty_title_block",
                            description=f"Title block metadata placeholder detected: '{val}'",
                            recommendation="Fill all title blocks fields (Drawn by, Approved, Drawing Number) with authentic production values.",
                            source="rule_engine",
                            confidence=1.0,
                            affected_entities=[{"id": str(txt.id), "type": "text"}],
                            coordinates=txt.geometry.get("coordinates")
                        )
                    )

        # Rule 5: Duplicate Overlapping Entities
        # Search for exact overlapping line primitives to avoid rendering artifacts or manufacturing double-cuts
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
                            audit_session_id=audit_session_id,
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

        # Rule 6: Invalid / Non-Standard Scales
        for txt in texts:
            val = txt.properties.get("value", "").strip()
            # Look for patterns like Scale: 1:3 or Scale 1:4
            match = re.search(r"scale\s*:?\s*(\d+\s*:\s*\d+)", val, re.IGNORECASE)
            if match:
                scale_val = match.group(1).replace(" ", "")
                if scale_val not in STANDARD_SCALES:
                    violations.append(
                        AuditViolation(
                            audit_session_id=audit_session_id,
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

        # Rule 7: Orphan / Empty Annotations
        for txt in texts:
            val = txt.properties.get("value", "").strip()
            if not val:
                violations.append(
                    AuditViolation(
                        audit_session_id=audit_session_id,
                        severity="low",
                        category="orphan_annotation",
                        description="Empty drawing annotation block detected with no textual details.",
                        recommendation="Remove redundant empty text annotations from drawing workspace.",
                        source="rule_engine",
                        confidence=1.0,
                        affected_entities=[{"id": str(txt.id), "type": "text"}]
                    )
                )

        # Rule 8: Unsupported Units
        # Checks database metadata variables
        meas = drawing.metadata.get("measurement", -1)
        if meas == -1:
            violations.append(
                AuditViolation(
                    audit_session_id=audit_session_id,
                    severity="medium",
                    category="unsupported_units",
                    description="Drawing measurement system is undefined ($MEASUREMENT header missing).",
                    recommendation="Explicitly define unit standards (Metric = 1, Imperial = 0) inside CAD workspace parameters.",
                    source="rule_engine",
                    confidence=1.0,
                    standard_reference="ISO 1000 (SI units and recommendations)"
                )
            )

        logger.info(f"Rule-based CAD audit completed. Found {len(violations)} infractions.")
        return violations
