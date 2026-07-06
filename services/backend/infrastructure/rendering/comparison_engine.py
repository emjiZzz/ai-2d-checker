from typing import Any

from ...domain.models.extracted_entity import ExtractedEntity
from ...logger import logger


class ComparisonEngine:
    """
    Offline geometric diffing engine. Compares two DXF drawings
    and identifies added, removed, and modified entities.
    """

    @staticmethod
    def compare_drawings(base_entities: list[ExtractedEntity], new_entities: list[ExtractedEntity]) -> dict[str, Any]:
        """
        Calculates diff between two entity sets.
        Uses simplistic coordinate hashing for exact matching.
        """
        logger.info(f"Comparing base ({len(base_entities)}) against new ({len(new_entities)})...")
        
        # In a real implementation we would do deep geometric equivalence.
        # For Phase 5 scaffold, we group by type and start/insert coordinates
        def hash_entity(ent: ExtractedEntity) -> str:
            geo = ent.geometry
            if ent.entity_type == "line" and "start" in geo and "end" in geo:
                # Sort coordinates to make direction-agnostic
                c1 = tuple(geo["start"][:2])
                c2 = tuple(geo["end"][:2])
                pts = sorted([c1, c2])
                return f"line_{pts[0]}_{pts[1]}"
            elif ent.entity_type in ["text", "insert"] and "insert" in geo:
                return f"{ent.entity_type}_{tuple(geo['insert'][:2])}_{ent.properties.get('value', '')}"
            return str(ent.id) # fallback

        base_map = {hash_entity(e): e for e in base_entities}
        new_map = {hash_entity(e): e for e in new_entities}

        base_keys = set(base_map.keys())
        new_keys = set(new_map.keys())

        removed_keys = base_keys - new_keys
        added_keys = new_keys - base_keys
        unmodified_keys = base_keys & new_keys

        removed = [base_map[k] for k in removed_keys]
        added = [new_map[k] for k in added_keys]

        logger.info(f"Comparison complete: {len(added)} added, {len(removed)} removed.")
        
        return {
            "added": added,
            "removed": removed,
            "modified": [], # Deep modification tracking would go here
            "unmodified_count": len(unmodified_keys)
        }
