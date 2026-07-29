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
from typing import Any

from .spatial_differ import SpatialDiffer


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


def reconcile_relocated_markings(markings: list[dict]) -> list[dict]:
    """Merge unambiguous REMOVED/ADDED pairs of identical text into single MATCHED findings.

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

    if not merged_at:
        return list(markings)

    out: list[dict] = []
    for i, m in enumerate(markings):
        if i in drop:
            continue
        out.append(merged_at.get(i, m))
    return out
