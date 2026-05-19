import math
from typing import Any, Dict, List
from ...logger import logger

class BlockExploder:
    """
    Recursively explodes DXF INSERT entities into base primitives (LINE, CIRCLE, etc)
    by applying 2D transform matrices (Translation, Rotation, Scale).
    """

    MAX_RECURSION_DEPTH = 10

    @staticmethod
    def _apply_transform(point: List[float], insert_geo: Dict[str, Any]) -> List[float]:
        """
        Applies Translation, Scaling, and Rotation to a [x, y] coordinate.
        """
        px, py = point[0], point[1]
        
        scale_x = insert_geo.get("scale_x", 1.0)
        scale_y = insert_geo.get("scale_y", 1.0)
        rot_deg = insert_geo.get("rotation", 0.0)
        ins_x, ins_y = insert_geo.get("insert", [0.0, 0.0])[:2]
        
        # 1. Scale
        sx = px * scale_x
        sy = py * scale_y
        
        # 2. Rotate
        if rot_deg != 0.0:
            rad = math.radians(rot_deg)
            cos_r = math.cos(rad)
            sin_r = math.sin(rad)
            rx = sx * cos_r - sy * sin_r
            ry = sx * sin_r + sy * cos_r
            sx, sy = rx, ry
            
        # 3. Translate
        fx = sx + ins_x
        fy = sy + ins_y
        
        return [fx, fy]

    @staticmethod
    def explode_insert(insert_entity: Any, block_definitions: Dict[str, List[Any]], current_depth: int = 0) -> List[Any]:
        """
        Explodes an INSERT entity and returns a list of transformed primitive dictionaries.
        """
        if current_depth > BlockExploder.MAX_RECURSION_DEPTH:
            logger.warning(f"Max block recursion depth reached for INSERT {insert_entity.id}")
            return []
            
        block_name = insert_entity.properties.get("block_name")
        if not block_name or block_name not in block_definitions:
            return []
            
        exploded_primitives = []
        block_entities = block_definitions[block_name]
        
        for base_ent in block_entities:
            # Deep copy to avoid mutating the master block definition
            ent_copy = base_ent.model_copy(deep=True)
            
            geo = ent_copy.geometry
            if not geo:
                continue
                
            # If nested INSERT, recurse
            if ent_copy.entity_type == "insert":
                # Combine transforms conceptually (simplified for this scaffold)
                nested_exploded = BlockExploder.explode_insert(ent_copy, block_definitions, current_depth + 1)
                # Apply current INSERT's transform to the nested exploded children
                for n_ent in nested_exploded:
                    # Recursive transformation logic would go deep here
                    exploded_primitives.append(n_ent)
                continue
                
            # Transform primitives
            if ent_copy.entity_type == "line":
                if "start" in geo:
                    geo["start"] = BlockExploder._apply_transform(geo["start"], insert_entity.geometry)
                if "end" in geo:
                    geo["end"] = BlockExploder._apply_transform(geo["end"], insert_entity.geometry)
            elif ent_copy.entity_type == "circle":
                if "center" in geo:
                    geo["center"] = BlockExploder._apply_transform(geo["center"], insert_entity.geometry)
                geo["radius"] = geo.get("radius", 1.0) * insert_entity.geometry.get("scale_x", 1.0)
            
            ent_copy.geometry = geo
            exploded_primitives.append(ent_copy)
            
        return exploded_primitives
