import time
from pathlib import Path
from typing import Any, Dict, List, Tuple
from ...logger import logger

class PDFDiffEngine:
    """
    Structural & Visual PDF comparison engine.
    Compares reference baseline PDF vs revision PDF, isolating added, removed, and modified vector/text segments.
    """
    @staticmethod
    def compare_documents(old_entities: List[Dict[str, Any]], new_entities: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """
        Runs structural comparisons on geometry and text coordinates.
        Categorizes elements into deleted (crimson), added (teal), and unchanged (charcoal).
        """
        logger.info(f"Running structural PDF diff analysis. Comparing {len(old_entities)} baseline vs {len(new_entities)} revision entities.")
        start_time = time.time()
        
        diff_results = {
            "added": [],
            "removed": [],
            "modified": [],
            "unchanged": []
        }

        # Index reference entities by their coordinates to match identical paths
        old_keys = {}
        for ent in old_entities:
            geo = ent.get("geometry", {})
            ent_type = ent.get("entity_type")
            
            # Formulate coordinate-based identity key
            key = None
            if ent_type == "line" and geo.get("start") and geo.get("end"):
                s, e = geo["start"], geo["end"]
                key = f"line_{round(s[0], 2)}_{round(s[1], 2)}_{round(e[0], 2)}_{round(e[1], 2)}"
            elif ent_type == "polyline" and geo.get("points"):
                pts = geo["points"]
                if pts:
                    key = f"poly_{round(pts[0][0], 2)}_{round(pts[0][1], 2)}_{len(pts)}"
            elif ent_type == "text" and geo.get("insert"):
                ins = geo["insert"]
                text_val = ent.get("properties", {}).get("text", "")
                key = f"text_{round(ins[0], 2)}_{round(ins[1], 2)}_{text_val}"
            
            if key:
                old_keys[key] = ent

        # Compare new entities against reference index
        for ent in new_entities:
            geo = ent.get("geometry", {})
            ent_type = ent.get("entity_type")
            
            key = None
            if ent_type == "line" and geo.get("start") and geo.get("end"):
                s, e = geo["start"], geo["end"]
                key = f"line_{round(s[0], 2)}_{round(s[1], 2)}_{round(e[0], 2)}_{round(e[1], 2)}"
            elif ent_type == "polyline" and geo.get("points"):
                pts = geo["points"]
                if pts:
                    key = f"poly_{round(pts[0][0], 2)}_{round(pts[0][1], 2)}_{len(pts)}"
            elif ent_type == "text" and geo.get("insert"):
                ins = geo["insert"]
                text_val = ent.get("properties", {}).get("text", "")
                key = f"text_{round(ins[0], 2)}_{round(ins[1], 2)}_{text_val}"

            if key and key in old_keys:
                # Unchanged geometry
                ent_copy = dict(ent)
                ent_copy["properties"] = dict(ent_copy.get("properties", {}))
                ent_copy["properties"]["stroke"] = "#27272a" # Unchanged = Charcoal
                ent_copy["properties"]["color"] = "#27272a"
                diff_results["unchanged"].append(ent_copy)
                # Remove from old keys to trace what was deleted
                old_keys.pop(key)
            else:
                # Added geometry
                ent_copy = dict(ent)
                ent_copy["properties"] = dict(ent_copy.get("properties", {}))
                ent_copy["properties"]["stroke"] = "#10b981" # Added = Teal
                ent_copy["properties"]["color"] = "#10b981"
                diff_results["added"].append(ent_copy)

        # Remaining reference keys represent deleted baseline paths
        for ent in old_keys.values():
            ent_copy = dict(ent)
            ent_copy["properties"] = dict(ent_copy.get("properties", {}))
            ent_copy["properties"]["stroke"] = "#ef4444" # Deleted = Crimson
            ent_copy["properties"]["color"] = "#ef4444"
            diff_results["removed"].append(ent_copy)

        duration = time.time() - start_time
        logger.info(f"PDF structural comparison complete in {duration:.4f}s. Added: {len(diff_results['added'])}, Removed: {len(diff_results['removed'])}")
        return diff_results
