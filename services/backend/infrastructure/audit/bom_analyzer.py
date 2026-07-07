# Compatibility shim — new code should import directly from infrastructure.audit.bom.*
# This file exists so existing call sites in audits.py / rule_engine.py don't need
# to change in the same commit as the extraction. Remove once all call sites are migrated.
from .bom.row_extractor import extract_bom_rows, detect_balloons, reconcile
from .bom.table_extractor import extract_bom_table, extract_dynamic_regions, build_bom_table
from .bom.title_block_extractor import extract_title_block
from .bom.spatial_utils import (
    find_drawing_text_coordinates, compute_bom_bbox, compute_title_block_bbox,
)
from .bom.constants import ITEM_NO_PATTERN, map_signature_value

class BOMAnalyzer:
    """DEPRECATED shim. Use infrastructure.audit.bom.* directly in new code."""
    extract_bom_rows = staticmethod(extract_bom_rows)
    detect_balloons = staticmethod(detect_balloons)
    reconcile = staticmethod(reconcile)
    extract_bom_table = staticmethod(extract_bom_table)
    extract_dynamic_regions = staticmethod(extract_dynamic_regions)
    build_bom_table = staticmethod(build_bom_table)
    extract_title_block = staticmethod(extract_title_block)
    find_drawing_text_coordinates = staticmethod(find_drawing_text_coordinates)
    compute_bom_bbox = staticmethod(compute_bom_bbox)
    compute_title_block_bbox = staticmethod(compute_title_block_bbox)
    ITEM_NO_PATTERN = ITEM_NO_PATTERN
    map_signature_value = staticmethod(map_signature_value)
