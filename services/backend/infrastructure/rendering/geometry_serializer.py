from typing import Any

from ...domain.models.extracted_entity import ExtractedEntity
from ...logger import logger


class GeometrySerializer:
    """
    Serializes backend ExtractedEntity documents into normalized,
    frontend-ready JSON payloads for React Konva or PixiJS rendering.
    Handles color mapping, lineweight scaling, and layer grouping.
    """
    
    # Basic mapping of DXF colors to web hex (simplified palette)
    COLOR_MAP = {
        0: "#FFFFFF", # Default / ByBlock
        1: "#FF0000", # Red
        2: "#FFFF00", # Yellow
        3: "#00FF00", # Green
        4: "#00FFFF", # Cyan
        5: "#0000FF", # Blue
        6: "#FF00FF", # Magenta
        7: "#FFFFFF", # White/Black
        8: "#808080", # Dark Grey
        9: "#C0C0C0", # Light Grey
        256: "#FFFFFF" # ByLayer fallback
    }

    @staticmethod
    def serialize_entities(entities: list[ExtractedEntity]) -> dict[str, Any]:
        """
        Groups and normalizes geometry.
        Returns payload: { "layers": { "LAYER_NAME": [ entities ] } }
        """
        layers_map: dict[str, list[dict[str, Any]]] = {}
        
        for ent in entities:
            layer = ent.layer
            
            # Map standard attributes
            color_index = ent.properties.get("color", 256)
            hex_color = GeometrySerializer.COLOR_MAP.get(color_index, "#FFFFFF")
            lineweight = ent.properties.get("lineweight", 1.0)
            if lineweight < 0:
                lineweight = 1.0 # normalize bylayer/byblock negatives
            
            payload = {
                "id": str(ent.id),
                "handle": getattr(ent, "handle", None) or ent.properties.get("handle"),
                "type": ent.entity_type.lower(),
                "geometry": ent.geometry,
                "properties": ent.properties,
                "style": {
                    "stroke": hex_color,
                    "strokeWidth": lineweight / 100.0 if lineweight > 10 else lineweight, # basic normalization
                    "dash": [5, 5] if ent.properties.get("linetype", "").lower() in ["dashed", "hidden"] else None
                }
            }
            
            layers_map.setdefault(layer, []).append(payload)
            
        logger.info(f"Serialized {len(entities)} entities into {len(layers_map)} distinct layers.")
        return {"layers": layers_map}
