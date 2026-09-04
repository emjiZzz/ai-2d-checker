"""Drawing-number extraction, used to reject a reference/revision pair that isn't a pair.

Not `revision_detector.detect_revision`, the obvious place, because that returns `None` on 14 of
14 real corpus sides -- measured. Two structural gates fail on this client's sheets: it reads
only layers matching `am_bor|border|title|title_block` while the number is on `RAHM2`, `WAKU` and
`NoLayerName_001`; and it needs the label and value in one text entity, while this title block
rules them into separate cells (which is why `bom/title_block_extractor.py` pairs them by spatial
proximity). So `part_number` is dead here, and the Phase 7.2 revision chain with it, recorded as
its own defect. This module does not repair it: populating `part_number` would activate
`audits.py`'s dormant `previous_revision_id` auto-link, a live behaviour change arriving as a side
effect of adding a validation guard.

Instead it collects every token shaped like a drawing number, without deciding which is THE
number, because the guard only asks whether both sheets share one. That tolerates noise --
`M745227N01`'s reference carries a stray `C2801P` -- provided the real number is on both sides.
Measured over `storage/eval/pairs/`: 7 of 7 real pairs share a token and 42 of 42 cross-pairings
share none, so zero false accepts and zero false rejects.

`_DRAWING_NUMBER_SHAPE` is tuned to KMTI's `M745203N01` / `M7452A0N01` form; one client, one
scheme. Other numbering returns an empty set, and the caller must read empty as "cannot judge"
and allow the pair -- see `is_pair_mismatch`. Failing open is the safety design: a false reject
deletes a good upload, a false accept only runs the comparison the user asked for.
"""
import re
from typing import Any

# Letter, then digits, then an optional alphanumeric tail: M745203N01, M7452A0N01, C2801P.
# Anchored, so it matches a whole standalone token and never a substring of prose.
_DRAWING_NUMBER_SHAPE = re.compile(r"^[A-Z]\d{3,6}[A-Z0-9]{0,6}$", re.IGNORECASE)

# Below this, a "token" is too generic to identify a drawing (and the shape above already
# requires 4+ characters, so this is a floor, not the primary filter).
_MIN_TOKEN_LENGTH = 5


def extract_drawing_numbers(entities: list[dict[str, Any]]) -> list[str]:
    """Every drawing-number-shaped text token on the sheet, uppercased and sorted.

    Sorted rather than insertion-ordered so the stored value is stable across re-ingests of
    the same file -- it is persisted on the DrawingDocument and compared between drawings.
    """
    found: set[str] = set()

    for item in entities:
        if item.get("entity_type") != "text":
            continue
        props = item.get("properties") or {}
        text = (props.get("text") or props.get("value") or "").strip()
        if len(text) < _MIN_TOKEN_LENGTH:
            continue
        if _DRAWING_NUMBER_SHAPE.match(text):
            found.add(text.upper())

    return sorted(found)


def is_pair_mismatch(reference_numbers: list[str], revision_numbers: list[str]) -> bool:
    """True only when both sides carry drawing numbers and share none of them.

    Absent evidence is never a mismatch. If either side yielded no tokens the answer is
    "cannot judge", and the caller must let the pair through. The cost asymmetry is the
    reason: rejecting deletes a drawing the user just uploaded, while accepting merely runs
    the comparison they asked for.
    """
    if not reference_numbers or not revision_numbers:
        return False
    # Normalised here rather than trusting the caller: `extract_drawing_numbers` uppercases,
    # but this is public and its TypeScript twin (`isDrawingPairMismatch`) normalises too --
    # two spellings of one number must never read as two different drawings.
    left = {n.strip().upper() for n in reference_numbers}
    right = {n.strip().upper() for n in revision_numbers}
    return not (left & right)
