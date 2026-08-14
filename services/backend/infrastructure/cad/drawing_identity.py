"""Drawing-number extraction, used to reject a reference/revision pair that isn't a pair.

## Why this is not `revision_detector.detect_revision`

`detect_revision` populates `part_number` and is the obvious place for this. It cannot be
used, because **it returns `None` on 14 of 14 real corpus sides** -- measured, not assumed.
Two independent gates fail on this client's sheets, and both are structural rather than a
tuning problem:

1. It only reads text on layers matching `am_bor|border|title|title_block`. The measured
   layers carrying the number are `RAHM2`, `WAKU` and `NoLayerName_001`.
2. It requires the label and the value in **one** text entity (`DWG NO: M745203N01`). This
   title block rules the label and the value into separate cells, so they are separate
   entities -- which is precisely why `bom/title_block_extractor.py` has to do a spatial
   proximity search to pair them.

So `part_number` is dead on these drawings, and with it the Phase 7.2 revision chain. That
is recorded as its own defect; this module deliberately does **not** repair it, because
populating `part_number` would activate `audits.py`'s dormant `previous_revision_id`
auto-link (a live behaviour change) as a side effect of adding a validation guard.

## What this does instead

Collects every text token *shaped* like a drawing number. It does **not** try to identify
which one is THE number, and does not need to: the guard asks only whether the two sheets
**share** one. That tolerates noise -- `M745227N01`'s reference carries a stray `C2801P` --
as long as the real number is present on both sides.

Measured over the eval corpus (`storage/eval/pairs/`), which is the only ground truth
available: **7 of 7 real reference/revision pairs share a token, and 42 of 42 cross-pairings
share none.** Zero false accepts, zero false rejects.

⚠ **One client, one numbering scheme.** `_DRAWING_NUMBER_SHAPE` is tuned to KMTI's
`M745203N01` / `M7452A0N01` form. On a drawing whose numbering does not match, this returns
an empty set, and the *caller must treat empty as "cannot judge" and allow the pair* -- see
`is_pair_mismatch`. Failing open is the whole safety design: a false reject deletes a good
upload, a false accept only lets through the comparison the user already asked for.
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

    **Absent evidence is never a mismatch.** If either side yielded no tokens the answer is
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
