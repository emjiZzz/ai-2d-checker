"""Collapse REMOVED/ADDED pairs that are one piece of unchanged content reported twice.

## The defect

The deterministic engine partitions each drawing into zones and diffs each zone against its
counterpart independently (`orchestrator.generate_deterministic_candidates`). `notes` and
`iso` are detected per drawing rather than pinned from a template -- correctly, since they
genuinely move -- which means the *same* line of text can fall inside the notes box on one
drawing and outside it on the other.

When that happens the line is compared against two different pools. It has no counterpart in
either, so it is emitted twice:

    drawing_views  REMOVED  完成時、バリ、キリ粉はなきこと     <- ref's views pool
    notes_section  ADDED    完成時、バリ、キリ粉はなきこと     <- rev's notes pool

Measured on the M7452A0N01 pair: the reference lays its notes out in two columns and the
revision in one, so five unchanged lines produced ten false findings -- roughly a quarter of
the entire report.

The same shape arises without any zone disagreement, when content simply moves further across
the sheet than the differ's widened same-text threshold (0.150 of sheet). Both cases are one
piece of content reported as two findings, so both are handled here.

## Why MATCHED rather than a new MOVED status

`PhysicalComparisonResponse.status` is `Literal["MATCHED", "CHANGED", "ADDED", "REMOVED",
"CONFLICT"]`, and that model is handed to Gemini as its `response_schema`. Adding a value
would change what the LLM engines are invited to emit, for a defect that only affects the
deterministic one. The relocation is recorded in `details` instead, which costs no schema
change and is not a lie: the content is present, and unchanged, in both drawings.

## Why only unambiguous pairs

Collapsing requires the normalized text to appear exactly once among REMOVED and exactly once
among ADDED. A "1" deleted from the BOM and an unrelated "1" added in the title block must not
be merged into "unchanged" -- that would hide a real deletion. Repeated text is left exactly
as it was; a wrong merge silently destroys a finding, while a missed merge only leaves the
noise that was already there.
"""
from difflib import SequenceMatcher
from typing import Any, Optional

from .spatial_differ import SpatialDiffer, _usable_bounds

# ---------------------------------------------------------------------------
# Fuzzy pass: content that both MOVED and CHANGED
#
# The exact pass below only merges identical text, so a line that was edited *and* landed in
# a different zone stays two findings. Real example from the corpus pair:
#
#     notes_section  REMOVED  素材調質施工 硬度HS35～38度
#     drawing_views  ADDED    素材調質施工 硬度ＨＳ３５～３８     (trailing 度 dropped)
#
# One edit, reported as a deletion plus an unrelated addition, with the actual change --
# the dropped 度 -- never stated anywhere.
#
# Pairing on similarity risks the opposite failure: inventing a CHANGED that hides a genuine
# deletion alongside a genuine addition. Four independent guards, all of which must hold:
#
#   1. High similarity. 0.82 keeps edits like a dropped suffix and rejects merely
#      same-shaped strings.
#   2. Mutually best. The REMOVED's best candidate must be the ADDED, and vice versa.
#   3. Clear margin over the runner-up. If two candidates score within 0.08 the pairing is
#      ambiguous and BOTH are left alone -- a wrong merge destroys a finding, a missed merge
#      only leaves the noise that was already there.
#   4. Bounded movement. Content really does move, but not across the whole sheet. Checked in
#      the normalized frame because the two drawings are not necessarily in the same
#      coordinate space (see spatial_differ's header). Skipped when bounds are unavailable,
#      leaving the other three guards.
#
# Short strings are excluded outright: "8.7" vs "8.65" scores 0.57 and "45" vs "46" scores
# 0.5, so no threshold separates a real edit from a coincidence at that length.
SIMILARITY_THRESHOLD = 0.82
AMBIGUITY_MARGIN = 0.08
MIN_FUZZY_LENGTH = 4
MAX_NORMALIZED_MOVE = 0.25


def _key(marking: dict) -> str:
    """Normalized match key. Uses the differ's own normalizer so that two strings which
    would have matched inside a single pool also reconcile across pools -- otherwise the
    same NFKC/width/spacing rules would apply in one place and not the other."""
    return SpatialDiffer._normalize_text(marking.get("text_content") or "")


def _describe(removed: dict, added: dict) -> str:
    ref_cat = removed.get("category")
    rev_cat = added.get("category")
    if ref_cat != rev_cat:
        return (
            f"Unchanged content, relocated between zones: found in '{ref_cat}' on the "
            f"reference and '{rev_cat}' on the revision. Reported once rather than as a "
            f"removal plus an addition."
        )
    return (
        f"Unchanged content, relocated within '{rev_cat}' by more than the matching "
        f"radius. Reported once rather than as a removal plus an addition."
    )


def _normalized_point(marking: dict, key: str, bounds) -> Optional[tuple]:
    coord = marking.get(key)
    if not coord or len(coord) < 2 or not _usable_bounds(bounds):
        return None
    try:
        return SpatialDiffer._to_match_space(float(coord[0]), float(coord[1]), bounds)
    except (TypeError, ValueError):
        return None


def _moved_too_far(removed: dict, added: dict, ref_bounds, rev_bounds) -> bool:
    """True when the two sit too far apart to plausibly be the same content.

    Returns False when either position is unavailable: the check is a guard, not a
    requirement, and a missing coordinate must not silently block every merge.
    """
    a = _normalized_point(removed, "ref_coordinates", ref_bounds)
    b = _normalized_point(added, "coordinates", rev_bounds)
    if a is None or b is None:
        return False
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5 > MAX_NORMALIZED_MOVE


def _fuzzy_pairs(
    markings: list[dict], removed_idx: list[int], added_idx: list[int],
    ref_bounds, rev_bounds,
) -> dict:
    """Mutually-best, unambiguous, similar REMOVED/ADDED pairs. Returns {removed_i: added_i}."""
    scores: dict = {}
    for r_i in removed_idx:
        r_key = _key(markings[r_i])
        if len(r_key) < MIN_FUZZY_LENGTH:
            continue
        for a_i in added_idx:
            a_key = _key(markings[a_i])
            if len(a_key) < MIN_FUZZY_LENGTH:
                continue
            ratio = SequenceMatcher(None, r_key, a_key).ratio()
            if ratio >= SIMILARITY_THRESHOLD:
                scores[(r_i, a_i)] = ratio

    def ranked(fixed: int, others: list, as_removed: bool) -> list:
        out = [
            (scores[(fixed, o) if as_removed else (o, fixed)], o)
            for o in others
            if ((fixed, o) if as_removed else (o, fixed)) in scores
        ]
        out.sort(reverse=True)
        return out

    pairs: dict = {}
    for r_i in removed_idx:
        best = ranked(r_i, added_idx, as_removed=True)
        if not best:
            continue
        # Guard 3, from the REMOVED side.
        if len(best) > 1 and (best[0][0] - best[1][0]) < AMBIGUITY_MARGIN:
            continue
        a_i = best[0][1]

        # Guard 2 and 3 again, from the ADDED side: the pairing must be mutual and equally
        # unambiguous, or a single ADDED could claim several REMOVEDs.
        reverse = ranked(a_i, removed_idx, as_removed=False)
        if not reverse or reverse[0][1] != r_i:
            continue
        if len(reverse) > 1 and (reverse[0][0] - reverse[1][0]) < AMBIGUITY_MARGIN:
            continue

        if _moved_too_far(markings[r_i], markings[a_i], ref_bounds, rev_bounds):
            continue

        pairs[r_i] = a_i
    return pairs


def reconcile_relocated_markings(
    markings: list[dict], ref_bounds=None, rev_bounds=None,
) -> list[dict]:
    """Merge REMOVED/ADDED pairs that are one piece of content reported twice.

    Two passes:
      * identical text  -> MATCHED, i.e. unchanged content that merely relocated;
      * similar text    -> CHANGED, i.e. content that was edited *and* relocated, which the
                           per-zone diffs could never pair because they never shared a pool.

    `ref_bounds`/`rev_bounds` are each drawing's `render_bounds`, used only to bound how far
    content may have moved. Omitting them costs one of the fuzzy pass's four guards.

    Returns a new list; the input is not mutated. Order is preserved, with each merged
    finding taking the position of the REMOVED marking it replaces so that a report does not
    reshuffle when reconciliation kicks in.
    """
    if not markings:
        return list(markings)

    removed_by_key: dict[str, list[int]] = {}
    added_by_key: dict[str, list[int]] = {}

    for i, m in enumerate(markings):
        status = m.get("status")
        if status == "REMOVED":
            removed_by_key.setdefault(_key(m), []).append(i)
        elif status == "ADDED":
            added_by_key.setdefault(_key(m), []).append(i)

    merged_at: dict[int, dict] = {}
    drop: set[int] = set()

    for key, removed_idx in removed_by_key.items():
        added_idx = added_by_key.get(key)
        # Ambiguous multiplicity is left alone -- see the module docstring.
        if not added_idx or len(removed_idx) != 1 or len(added_idx) != 1:
            continue
        if not key:
            continue

        r_i, a_i = removed_idx[0], added_idx[0]
        removed, added = markings[r_i], markings[a_i]

        merged: dict[str, Any] = dict(added)
        merged["status"] = "MATCHED"
        merged["details"] = _describe(removed, added)
        # The revision's category and coordinates describe the drawing as it now stands;
        # the reference coordinate is carried over so the finding can still be pinned on
        # both canvases.
        if removed.get("ref_coordinates") is not None:
            merged["ref_coordinates"] = removed["ref_coordinates"]
        merged.pop("original_value", None)

        merged_at[r_i] = merged
        drop.add(a_i)

    # Second pass: content that was edited as well as relocated. Only findings the exact pass
    # did not already consume are eligible.
    leftover_removed = [
        i for i, m in enumerate(markings)
        if m.get("status") == "REMOVED" and i not in merged_at and i not in drop
    ]
    leftover_added = [
        i for i, m in enumerate(markings)
        if m.get("status") == "ADDED" and i not in merged_at and i not in drop
    ]

    for r_i, a_i in _fuzzy_pairs(
        markings, leftover_removed, leftover_added, ref_bounds, rev_bounds
    ).items():
        removed, added = markings[r_i], markings[a_i]
        merged = dict(added)
        merged["status"] = "CHANGED"
        merged["original_value"] = removed.get("text_content")
        merged["details"] = (
            f"Edited and relocated: '{removed.get('text_content')}' -> "
            f"'{added.get('text_content')}'. Found in '{removed.get('category')}' on the "
            f"reference and '{added.get('category')}' on the revision, so the two were never "
            f"compared directly; reported once rather than as a removal plus an addition."
        )
        if removed.get("ref_coordinates") is not None:
            merged["ref_coordinates"] = removed["ref_coordinates"]
        merged_at[r_i] = merged
        drop.add(a_i)

    if not merged_at:
        return list(markings)

    out: list[dict] = []
    for i, m in enumerate(markings):
        if i in drop:
            continue
        out.append(merged_at.get(i, m))
    return out
