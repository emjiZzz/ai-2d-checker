import re

from ...domain.models.audit_violation import AuditViolation
from ...domain.models.drawing_document import DrawingDocument
from ...domain.models.extracted_entity import ExtractedEntity
from ...logger import logger
from .bom_analyzer import BOMAnalyzer
from .rules.rule_base import RuleContext
from .rules.layer_rules import validate_layers, validate_duplicates
from .rules.dimension_rules import (
    validate_dimensions_presence, validate_scales_standard,
    validate_scales_associative, validate_general_tolerances
)
from .rules.title_block_rules import (
    validate_title_block_placeholders, validate_title_block_completeness,
    validate_empty_block_attributes
)
from .rules.annotation_rules import (
    validate_orphan_annotations, validate_gdt_frames, validate_hole_callouts,
    validate_text_heights, validate_center_lines, validate_projection_notes,
    validate_threads, validate_revision_clouds, validate_surface_roughness
)
from .rules.units_rules import validate_units
from ..storage.entity_cache import load_entities


class RuleEngine:
    """
    Deterministic CAD validation engine.
    Executes structural drafting rules on extracted CAD graphic primitives
    and metadata records without requiring AI models.
    """

    @staticmethod
    async def validate_drawing(audit_session_id: str, drawing: DrawingDocument) -> list[AuditViolation]:
        logger.info(f"Initiating rule-based CAD compliance audit for drawing: {drawing.file_name}")
        violations: list[AuditViolation] = []

        # 1. Fetch all associated extracted graphic primitives from database
        entities = await load_entities(str(drawing.id))

        # Group entities by type
        entities_by_type: dict[str, list[ExtractedEntity]] = {}
        for ent in entities:
            entities_by_type.setdefault(ent.entity_type, []).append(ent)

        # Helper to safely retrieve text content from a text/dimension/multileader entity
        def get_text_content(ent) -> str:
            props = ent.properties or {}
            # Fallback chain for standard text properties
            return (props.get("text") or props.get("value") or "").strip()

        # Gather all text values from texts, dimensions, multileaders, and blocks
        all_text_contents = []
        texts = entities_by_type.get("text", [])
        dimensions = entities_by_type.get("dimension", [])
        multileaders = entities_by_type.get("multileader", [])
        blocks = entities_by_type.get("block", [])

        for txt in texts:
            all_text_contents.append(get_text_content(txt))
        for dim in dimensions:
            all_text_contents.append(get_text_content(dim))
        for ml in multileaders:
            all_text_contents.append(get_text_content(ml))
        for blk in blocks:
            attrs = blk.properties.get("attributes", {}) if blk.properties else {}
            for k, v in attrs.items():
                if v:
                    all_text_contents.append(str(v).strip())

        # Construct rule context
        context = RuleContext(
            audit_session_id=audit_session_id,
            drawing=drawing,
            entities=entities,
            entities_by_type=entities_by_type,
            all_text_contents=all_text_contents
        )

        # Execute modular rules
        # 1. Layer rules
        violations.extend(validate_layers(context))
        violations.extend(validate_duplicates(context))

        # 2. Dimension rules
        violations.extend(validate_dimensions_presence(context))
        violations.extend(validate_scales_standard(context))
        violations.extend(validate_scales_associative(context))
        violations.extend(validate_general_tolerances(context))

        # 3. Title block rules
        violations.extend(validate_title_block_placeholders(context))
        violations.extend(validate_title_block_completeness(context))
        violations.extend(validate_empty_block_attributes(context))

        # 4. Annotation rules
        violations.extend(validate_orphan_annotations(context))
        violations.extend(validate_gdt_frames(context))
        violations.extend(validate_hole_callouts(context))
        violations.extend(validate_text_heights(context))
        violations.extend(validate_center_lines(context))
        violations.extend(validate_projection_notes(context))
        violations.extend(validate_threads(context))
        violations.extend(validate_revision_clouds(context))
        violations.extend(validate_surface_roughness(context))

        # 5. Units rules
        violations.extend(validate_units(context))

        # Wire BOM Analyzer (BOM & Balloon Intelligence - Phase 5)
        try:
            bom_rows = BOMAnalyzer.extract_bom_rows(entities)
            balloons = BOMAnalyzer.detect_balloons(entities)
            bom_violations = BOMAnalyzer.reconcile(bom_rows, balloons, audit_session_id)
            violations.extend(bom_violations)
        except Exception as bom_err:
            logger.warning(f"BOM & Balloon reconciliation failed (non-fatal): {bom_err}")

        logger.info(f"Rule-based CAD audit completed. Found {len(violations)} infractions.")
        return violations
