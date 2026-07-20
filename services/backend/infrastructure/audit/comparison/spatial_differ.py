import math
import logging
from collections import defaultdict
import re

logger = logging.getLogger(__name__)

class SpatialDiffer:
    @staticmethod
    def _get_entity_text(entity) -> str:
        text = getattr(entity, 'properties', {}).get('text', '')
        if not text:
            return ""
        # Strip MTEXT formatting, replace spaces
        t = text.replace('\\P', '\n')
        t = re.sub(r'\\[A-Za-z0-9\-~|.]+;', '', t.replace('{', '').replace('}', '')).strip()
        return t
        
    @staticmethod
    def _normalize_text(text: str) -> str:
        """
        Normalizes text to gracefully handle standard "Copy-Trace" upgrades.
        For example: "Dia 25" -> "ø25", ignoring extra spaces.
        """
        import unicodedata
        t = unicodedata.normalize("NFKC", text)
        t = t.lower().replace(" ", "").replace("\n", "")
        # Common standard upgrades
        t = t.replace("dia", "ø").replace("diameter", "ø")
        t = t.replace("deg", "°").replace("degrees", "°")
        t = t.replace("rad", "r").replace("radius", "r")
        return t

    @staticmethod
    def _get_entity_coords(entity) -> tuple[float, float]:
        geom = getattr(entity, 'geometry', {})
        if geom and 'insert' in geom and len(geom['insert']) >= 2:
            return (float(geom['insert'][0]), float(geom['insert'][1]))
        return (0.0, 0.0)

    @staticmethod
    def calculate_global_offset(ref_entities: list, rev_entities: list) -> tuple[float, float, bool]:
        """
        Finds the global X, Y offset between two drawings by finding the most common 
        coordinate shift among exact text matches.
        Returns: (offset_x, offset_y, is_mismatch)
        """
        ref_text_map = defaultdict(list)
        for e in ref_entities:
            if getattr(e, 'entity_type', '') == 'text':
                txt = SpatialDiffer._get_entity_text(e)
                if txt and len(txt) > 2:
                    ref_text_map[SpatialDiffer._normalize_text(txt)].append(SpatialDiffer._get_entity_coords(e))

        deltas_x = []
        deltas_y = []
        matched_count = 0

        for e in rev_entities:
            if getattr(e, 'entity_type', '') == 'text':
                txt = SpatialDiffer._get_entity_text(e)
                norm_txt = SpatialDiffer._normalize_text(txt)
                if txt and len(txt) > 2 and norm_txt in ref_text_map:
                    rev_coord = SpatialDiffer._get_entity_coords(e)
                    candidates = ref_text_map[norm_txt]
                    # Pick the nearest ref coordinate when a normalized text has multiple
                    # ref entities (e.g. repeated dimension labels), not just the first in
                    # list order — this only affects offset estimation (median-smoothed below).
                    ref_coord = min(
                        candidates,
                        key=lambda c: (rev_coord[0] - c[0]) ** 2 + (rev_coord[1] - c[1]) ** 2
                    )
                    dx = rev_coord[0] - ref_coord[0]
                    dy = rev_coord[1] - ref_coord[1]
                    deltas_x.append(round(dx, 1))
                    deltas_y.append(round(dy, 1))
                    matched_count += 1

        total_rev_texts = sum(1 for e in rev_entities if getattr(e, 'entity_type', '') == 'text')
        is_mismatch = False
        if total_rev_texts > 20 and matched_count < (total_rev_texts * 0.1):
            is_mismatch = True

        if not deltas_x:
            return (0.0, 0.0, is_mismatch)

        deltas_x.sort()
        deltas_y.sort()
        median_dx = deltas_x[len(deltas_x) // 2]
        median_dy = deltas_y[len(deltas_y) // 2]

        return (median_dx, median_dy, is_mismatch)

    @staticmethod
    def diff_views(ref_entities: list, rev_entities: list, category: str = "drawing_views") -> list[dict]:
        """
        Dynamically compares entities using Adaptive Thresholding.
        Handles both strict digital twins and sloppy human copy-traces.
        """
        offset_x, offset_y, is_mismatch = SpatialDiffer.calculate_global_offset(ref_entities, rev_entities)
        
        if is_mismatch:
            logger.warning("FORMAT MISMATCH DETECTED: Drawings appear to be completely different.")

        # Build index
        ref_texts = []
        for e in ref_entities:
            if getattr(e, 'entity_type', '') == 'text':
                txt = SpatialDiffer._get_entity_text(e)
                if not txt: continue
                coords = SpatialDiffer._get_entity_coords(e)
                ref_texts.append({
                    "id": f"REF-{getattr(e, 'properties', {}).get('handle', '')}",
                    "text": txt,
                    "clean_text": SpatialDiffer._normalize_text(txt),
                    "x": coords[0],
                    "y": coords[1],
                    "matched": False
                })

        rev_texts = []
        for e in rev_entities:
            if getattr(e, 'entity_type', '') == 'text':
                txt = SpatialDiffer._get_entity_text(e)
                if not txt: continue
                coords = SpatialDiffer._get_entity_coords(e)
                rev_texts.append({
                    "id": f"REV-{getattr(e, 'properties', {}).get('handle', '')}",
                    "text": txt,
                    "clean_text": SpatialDiffer._normalize_text(txt),
                    "x": coords[0] - offset_x,  # Pre-align
                    "y": coords[1] - offset_y,  # Pre-align
                    "raw_x": coords[0],
                    "raw_y": coords[1],
                    "matched": False
                })

        if not rev_texts or not ref_texts:
            return []

        # --- PHASE A: Strict Digital Twin Test ---
        strict_radius = 5.0
        strict_matches = 0
        for rev in rev_texts:
            for ref in ref_texts:
                if rev["clean_text"] == ref["clean_text"]:
                    dist = math.sqrt((rev["x"] - ref["x"])**2 + (rev["y"] - ref["y"])**2)
                    if dist <= strict_radius:
                        strict_matches += 1
                        break
        
        match_rate = strict_matches / len(rev_texts)
        is_digital_twin = match_rate >= 0.80

        if is_digital_twin:
            logger.info(f"Adaptive Engine: Detected strict digital twin (Match Rate {match_rate:.1%}). Using Strict Mode.")
            distance_threshold = 10.0
        else:
            logger.info(f"Adaptive Engine: Detected Copy-Trace drawing (Match Rate {match_rate:.1%}). Using Fuzzy Mode.")
            distance_threshold = 150.0  # Wide search radius for jitter tolerance

        # --- PHASE B: Greedy Bipartite Spatial Matching ---
        markings = []

        def match_pass(threshold: float, same_text_only: bool = False):
            potential_pairs = []
            for rev in rev_texts:
                if rev.get("matched"): continue
                for ref in ref_texts:
                    if ref.get("matched"): continue
                    dist = math.sqrt((rev["x"] - ref["x"])**2 + (rev["y"] - ref["y"])**2)
                    if dist <= threshold:
                        is_same_text = rev["clean_text"] == ref["clean_text"]
                        if same_text_only and not is_same_text:
                            # Widened pass: a long-range match between *different* text was
                            # never a structural edit, it's a false pair — skip it entirely
                            # rather than letting the dist+1000 fallback pick it up.
                            continue
                        score = dist if is_same_text else dist + 1000.0
                        potential_pairs.append((score, dist, rev, ref))
            
            potential_pairs.sort(key=lambda x: x[0])
            
            for score, dist, rev, ref in potential_pairs:
                if rev.get("matched") or ref.get("matched"):
                    continue
                
                rev["matched"] = True
                ref["matched"] = True
                
                if rev["clean_text"] == ref["clean_text"]:
                    markings.append({
                        "entity_id": rev["id"],
                        "text_content": rev["text"],
                        "status": "MATCHED",
                        "details": "Element verified and matches reference.",
                        "category": category,
                        "coordinates": [rev["raw_x"], rev["raw_y"]],
                        "ref_coordinates": [ref["x"], ref["y"]]
                    })
                else:
                    markings.append({
                        "entity_id": rev["id"],
                        "text_content": rev["text"],
                        "original_value": ref["text"],
                        "status": "CHANGED",
                        "details": f"Dimension/Note updated: '{ref['text']}' -> '{rev['text']}'",
                        "category": category,
                        "coordinates": [rev["raw_x"], rev["raw_y"]],
                        "ref_coordinates": [ref["x"], ref["y"]]
                    })

        # Pass 1: Standard threshold
        match_pass(distance_threshold)
        
        # Pass 2: Widened threshold for unmatched leftovers to catch large-distance structural
        # edits — same-text matches only. A cross-text match at 5x the normal search radius was
        # never a structural edit (it's a false pair, most likely on drawings with repeated short
        # dimension labels), so the fallback score+1000 escape hatch is intentionally dropped here.
        widened_threshold = max(150.0, distance_threshold * 5.0)
        match_pass(widened_threshold, same_text_only=True)

        # Sweep unmatched REVs -> ADDED
        for rev in rev_texts:
            if not rev["matched"]:
                markings.append({
                    "entity_id": rev["id"],
                    "text_content": rev["text"],
                    "status": "ADDED",
                    "details": f"New element traced/added: {rev['text']}",
                    "category": category,
                    "coordinates": [rev["raw_x"], rev["raw_y"]]
                })

        # Sweep unmatched REFs -> REMOVED
        for ref in ref_texts:
            if not ref["matched"]:
                markings.append({
                    "entity_id": ref["id"],
                    "text_content": ref["text"],
                    "status": "REMOVED",
                    "details": f"Original element missing in trace: {ref['text']}",
                    "category": category,
                    "ref_coordinates": [ref["x"], ref["y"]]
                })

        return markings
