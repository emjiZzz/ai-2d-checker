import math
from typing import Dict, List, Tuple, Any
from ...logger import logger
from ...domain.models.extracted_entity import ExtractedEntity

class ViewportGenerator:
    """
    Calculates the global bounding box and normalized zoom extents
    for a given set of extracted DXF primitives.
    """

    @staticmethod
    def calculate_bounds(entities: List[ExtractedEntity]) -> Dict[str, float]:
        """
        Iterates over geometry to find the absolute min/max X and Y coordinates.
        Returns a bounding box dict: { min_x, max_x, min_y, max_y, width, height, center_x, center_y }
        """
        if not entities:
            return {"min_x": 0, "max_x": 0, "min_y": 0, "max_y": 0, "width": 0, "height": 0, "center_x": 0, "center_y": 0}

        min_x = float('inf')
        max_x = float('-inf')
        min_y = float('inf')
        max_y = float('-inf')

        def expand_bounds(x: float, y: float):
            nonlocal min_x, max_x, min_y, max_y
            if x < min_x: min_x = x
            if x > max_x: max_x = x
            if y < min_y: min_y = y
            if y > max_y: max_y = y

        for ent in entities:
            geo = ent.geometry
            if not geo:
                continue
                
            if ent.entity_type == "line" and "start" in geo and "end" in geo:
                expand_bounds(geo["start"][0], geo["start"][1])
                expand_bounds(geo["end"][0], geo["end"][1])
            elif ent.entity_type == "circle" and "center" in geo and "radius" in geo:
                cx, cy = geo["center"][0], geo["center"][1]
                r = geo["radius"]
                expand_bounds(cx - r, cy - r)
                expand_bounds(cx + r, cy + r)
            elif ent.entity_type in ["text", "insert"] and "insert" in geo:
                # Approximate text/block insertion points
                expand_bounds(geo["insert"][0], geo["insert"][1])
            elif ent.entity_type == "polyline" and "points" in geo:
                for pt in geo["points"]:
                    if len(pt) >= 2:
                        expand_bounds(pt[0], pt[1])

        # If we failed to find any valid points
        if min_x == float('inf'):
            return {"min_x": 0, "max_x": 0, "min_y": 0, "max_y": 0, "width": 0, "height": 0, "center_x": 0, "center_y": 0}

        # Apply a 5% margin padding
        width = max_x - min_x
        height = max_y - min_y
        padding_x = width * 0.05
        padding_y = height * 0.05

        final_min_x = min_x - padding_x
        final_max_x = max_x + padding_x
        final_min_y = min_y - padding_y
        final_max_y = max_y + padding_y

        return {
            "min_x": final_min_x,
            "max_x": final_max_x,
            "min_y": final_min_y,
            "max_y": final_max_y,
            "width": final_max_x - final_min_x,
            "height": final_max_y - final_min_y,
            "center_x": (final_min_x + final_max_x) / 2.0,
            "center_y": (final_min_y + final_max_y) / 2.0
        }
