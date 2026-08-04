import math
import logging
from collections import defaultdict
from difflib import SequenceMatcher
import re

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Match thresholds
#
# Matching runs in a NORMALIZED frame -- each drawing's coordinates divided by its own
# `render_bounds` -- whenever both drawings supply bounds. This exists because the two sides
# of a comparison are not necessarily in the same coordinate space at all: a DXF with no
# paper-space viewport is stored in model units, one with a viewport is projected to paper
# units. Measured on the M7452A0N01 pair, the reference spans 982.7 units and the revision
# 393.1 for the same sheet -- exactly 2.500x apart.
#
# `calculate_global_offset` only ever estimated a *translation*, so a scale difference could
# not be pre-aligned away: the offset needed to align that pair varied from -52 to -480 units
# across the sheet. Identical text away from the alignment centroid could therefore never
# pair, and was emitted as REMOVED on one side and ADDED on the other. Normalizing removes
# the scale term entirely -- the "45" title-block label went from unmatchable to a
# 0.003 separation.
#
# The normalized values below are direct conversions of the absolute ones, against the corpus
# reference sheet (1155 x 816.75, diagonal 1414.6). They deliberately preserve the existing
# tuning rather than re-tuning it: this change fixes scale-blindness, nothing else.
STRICT_RADIUS_NORM = 0.005      # was 5.0 units
TWIN_THRESHOLD_NORM = 0.010     # was 10.0 units
FUZZY_THRESHOLD_NORM = 0.150    # was 150.0 units

# Absolute fallbacks in CAD units, used only when a drawing has no usable render_bounds.
# Scale-blind by construction -- see above.
STRICT_RADIUS_ABS = 5.0
TWIN_THRESHOLD_ABS = 10.0
FUZZY_THRESHOLD_ABS = 150.0


# A CHANGED pairing means "the same element, edited" -- so the two texts have to be
# recognisably related. Without this gate the greedy matcher pairs ANY two texts within the
# distance threshold and, for anything but identical text, labels the pair CHANGED. On notes
# (sentences that move around the sheet) that mislabels unrelated content as an edit: measured
# on the KEMCO pair, '2 ロール： 4 (2x2台)' was reported as CHANGED into 'タップ、キリ穴は面取り
# 仕上げのこと' (0.00 char similarity), and '4 ロール：12' into '１' (0.14). A genuine edit on the
# same corpus -- 'シム表' -> 'Ｌ　シム表　ｌ' -- scores 0.75, so 0.40 sits cleanly in the gap.
CHANGED_SIMILARITY_FLOOR = 0.40

# Values made entirely of digits and dimension/measurement punctuation. Two such values
# ('130' -> '125') share few characters yet are a real edit, so they bypass the similarity
# floor. _normalize_text has already folded dia->ø, deg->°, rad->r and stripped spaces.
_NUMERICISH_RE = re.compile(r"^[0-9.,\-/x×øφ°±r():~〜=]+$")


def _plausible_edit(ref_clean: str, rev_clean: str) -> bool:
    """True when two DIFFERENT normalized strings are similar enough to be one element edited
    in place, rather than two unrelated strings that merely sit close together on the sheet."""
    if not ref_clean or not rev_clean:
        return False
    if SequenceMatcher(None, ref_clean, rev_clean).ratio() >= CHANGED_SIMILARITY_FLOOR:
        return True
    if _NUMERICISH_RE.match(ref_clean) and _NUMERICISH_RE.match(rev_clean):
        return True
    return False


def _usable_bounds(bounds) -> bool:
    """True when bounds are a 4-tuple enclosing a positive area."""
    try:
        if not bounds or len(bounds) != 4:
            return False
        return (float(bounds[2]) - float(bounds[0])) > 0 and (float(bounds[3]) - float(bounds[1])) > 0
    except (TypeError, ValueError):
        return False


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
    def _to_match_space(x: float, y: float, bounds) -> tuple[float, float]:
        """Map a CAD coordinate into the frame matching runs in.

        With usable bounds this is the drawing's own render_bounds normalized to a unit
        square, which is what makes the two sides comparable when they are stored at
        different scales. Without bounds the coordinate passes through unchanged, preserving
        the original absolute-unit behaviour for callers that cannot supply them.
        """
        if not _usable_bounds(bounds):
            return (x, y)
        bx0, by0, bx1, by1 = (float(v) for v in bounds)
        return ((x - bx0) / (bx1 - bx0), (y - by0) / (by1 - by0))

    @staticmethod
    def calculate_global_offset(
        ref_entities: list, rev_entities: list,
        ref_bounds=None, rev_bounds=None,
    ) -> tuple[float, float, bool]:
        """
        Finds the global X, Y offset between two drawings by finding the most common
        coordinate shift among exact text matches.

        Operates in the normalized frame when bounds are supplied, so the offset it reports
        is a genuine translation rather than an artifact of the two drawings being at
        different scales. A residual translation is still worth removing -- content really
        can sit shifted on the sheet -- but it is no longer being asked to absorb a scale
        difference it mathematically cannot.

        Returns: (offset_x, offset_y, is_mismatch) in the match space.
        """
        # Normalize both sides or neither. Normalizing one side alone would put the two
        # drawings in frames three orders of magnitude apart and match nothing at all.
        is_normalized = _usable_bounds(ref_bounds) and _usable_bounds(rev_bounds)
        rb = ref_bounds if is_normalized else None
        vb = rev_bounds if is_normalized else None

        ref_text_map = defaultdict(list)
        for e in ref_entities:
            if getattr(e, 'entity_type', '') == 'text':
                txt = SpatialDiffer._get_entity_text(e)
                if txt and len(txt) > 2:
                    raw = SpatialDiffer._get_entity_coords(e)
                    ref_text_map[SpatialDiffer._normalize_text(txt)].append(
                        SpatialDiffer._to_match_space(raw[0], raw[1], rb)
                    )

        deltas_x = []
        deltas_y = []
        matched_count = 0

        for e in rev_entities:
            if getattr(e, 'entity_type', '') == 'text':
                txt = SpatialDiffer._get_entity_text(e)
                norm_txt = SpatialDiffer._normalize_text(txt)
                if txt and len(txt) > 2 and norm_txt in ref_text_map:
                    raw = SpatialDiffer._get_entity_coords(e)
                    rev_coord = SpatialDiffer._to_match_space(raw[0], raw[1], vb)
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
                    # Precision must follow the space. Rounding to 0.1 is harmless in CAD
                    # units but catastrophic in the normalized frame, where the whole sheet
                    # is 1.0 wide -- every offset would collapse to 0.0 or 0.1 and the
                    # median would be meaningless. The values are median-smoothed below, so
                    # this rounding is only about damping float noise.
                    precision = 6 if is_normalized else 1
                    deltas_x.append(round(dx, precision))
                    deltas_y.append(round(dy, precision))
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
    def diff_views(
        ref_entities: list, rev_entities: list, category: str = "drawing_views",
        ref_bounds=None, rev_bounds=None,
    ) -> list[dict]:
        """
        Dynamically compares entities using Adaptive Thresholding.
        Handles both strict digital twins and sloppy human copy-traces.

        `ref_bounds`/`rev_bounds` are each drawing's `render_bounds`. Supply them: without
        them the two sides are matched in raw CAD units, which silently fails whenever the
        drawings are stored at different scales (model space vs paper space). See the module
        header. They are optional only so existing callers keep working unchanged.
        """
        is_normalized = _usable_bounds(ref_bounds) and _usable_bounds(rev_bounds)
        rb = ref_bounds if is_normalized else None
        vb = rev_bounds if is_normalized else None

        offset_x, offset_y, is_mismatch = SpatialDiffer.calculate_global_offset(
            ref_entities, rev_entities, ref_bounds=rb, rev_bounds=vb
        )

        if is_mismatch:
            logger.warning("FORMAT MISMATCH DETECTED: Drawings appear to be completely different.")

        # Build index. `x`/`y` are match-space coordinates; `raw_x`/`raw_y` stay in CAD units
        # because every consumer downstream (coordinate resolution, canvas pins, redline
        # writeback) needs real drawing coordinates, not normalized ones.
        ref_texts = []
        for e in ref_entities:
            if getattr(e, 'entity_type', '') == 'text':
                txt = SpatialDiffer._get_entity_text(e)
                if not txt: continue
                coords = SpatialDiffer._get_entity_coords(e)
                mx, my = SpatialDiffer._to_match_space(coords[0], coords[1], rb)
                ref_texts.append({
                    "id": f"REF-{getattr(e, 'properties', {}).get('handle', '')}",
                    "text": txt,
                    "clean_text": SpatialDiffer._normalize_text(txt),
                    "x": mx,
                    "y": my,
                    "raw_x": coords[0],
                    "raw_y": coords[1],
                    "matched": False
                })

        rev_texts = []
        for e in rev_entities:
            if getattr(e, 'entity_type', '') == 'text':
                txt = SpatialDiffer._get_entity_text(e)
                if not txt: continue
                coords = SpatialDiffer._get_entity_coords(e)
                mx, my = SpatialDiffer._to_match_space(coords[0], coords[1], vb)
                rev_texts.append({
                    "id": f"REV-{getattr(e, 'properties', {}).get('handle', '')}",
                    "text": txt,
                    "clean_text": SpatialDiffer._normalize_text(txt),
                    "x": mx - offset_x,  # Pre-align
                    "y": my - offset_y,  # Pre-align
                    "raw_x": coords[0],
                    "raw_y": coords[1],
                    "matched": False
                })

        if not rev_texts or not ref_texts:
            return []

        # --- PHASE A: Strict Digital Twin Test ---
        strict_radius = STRICT_RADIUS_NORM if is_normalized else STRICT_RADIUS_ABS
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

        space = "normalized" if is_normalized else "absolute CAD units"
        if is_digital_twin:
            logger.info(
                f"Adaptive Engine: Detected strict digital twin (Match Rate {match_rate:.1%}, "
                f"{space}). Using Strict Mode."
            )
            distance_threshold = TWIN_THRESHOLD_NORM if is_normalized else TWIN_THRESHOLD_ABS
        else:
            logger.info(
                f"Adaptive Engine: Detected Copy-Trace drawing (Match Rate {match_rate:.1%}, "
                f"{space}). Using Fuzzy Mode."
            )
            distance_threshold = FUZZY_THRESHOLD_NORM if is_normalized else FUZZY_THRESHOLD_ABS

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
                        if not is_same_text and not _plausible_edit(ref["clean_text"], rev["clean_text"]):
                            # Different, and not similar enough to be one element edited in
                            # place. Pairing these would report an unrelated string as CHANGED;
                            # leave both unmatched so they surface as REMOVED + ADDED instead.
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
                        "ref_coordinates": [ref["raw_x"], ref["raw_y"]]
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
                        "ref_coordinates": [ref["raw_x"], ref["raw_y"]]
                    })

        # Pass 1: Standard threshold
        match_pass(distance_threshold)
        
        # Pass 2: Widened threshold for unmatched leftovers to catch large-distance structural
        # edits — same-text matches only. A cross-text match at 5x the normal search radius was
        # never a structural edit (it's a false pair, most likely on drawings with repeated short
        # dimension labels), so the fallback score+1000 escape hatch is intentionally dropped here.
        widened_floor = FUZZY_THRESHOLD_NORM if is_normalized else FUZZY_THRESHOLD_ABS
        widened_threshold = max(widened_floor, distance_threshold * 5.0)
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
                    "ref_coordinates": [ref["raw_x"], ref["raw_y"]]
                })

        return markings
