"""Every marking status the app can write must be one the corpus bridge can read.

`MarkingStatus` is a `Literal` in `domain/models/ground_truth.py`; the bridge decides what each
member becomes through three maps. Nothing tied them together, so `MISMATCHED` -- writable by the
UI since the context menu offered it -- reached `from_manual_check` as "unknown marking status"
and blocked a whole pair, because the bridge refuses partial drafts by design.

The failure shape is what makes this worth a test rather than a comment: the status is only
rejected at conversion time, long after the engineer has done the labelling, and it takes the
entire session with it rather than the one marking.

Deliberately a membership check over the maps rather than a conversion test. A conversion test
would need a payload and would pass for a status nobody has used yet; this fails the moment a
member is added without deciding what it means.
"""

from __future__ import annotations

import typing

from services.backend.domain.models.ground_truth import MarkingStatus
from services.backend.infrastructure.eval.manual_check_bridge import (
    FINDING_STATUS_SIDE,
    NON_FINDING_REASONS,
    STATUS_ALIASES,
)


def _members() -> set[str]:
    return set(typing.get_args(MarkingStatus))


def test_every_marking_status_is_handled_by_the_bridge() -> None:
    handled = set(FINDING_STATUS_SIDE) | set(NON_FINDING_REASONS) | set(STATUS_ALIASES)
    missing = _members() - handled
    assert not missing, (
        f"MarkingStatus members the bridge cannot convert: {sorted(missing)}. "
        "Add each to FINDING_STATUS_SIDE (it is a finding), NON_FINDING_REASONS (it is not), or "
        "STATUS_ALIASES (it is another status under a different name). Leaving one out does not "
        "degrade the conversion, it refuses the entire session."
    )


def test_the_bridge_handles_no_status_the_model_forbids() -> None:
    """The mirror. A map key that is not a `MarkingStatus` is dead code or a typo."""
    handled = set(FINDING_STATUS_SIDE) | set(NON_FINDING_REASONS) | set(STATUS_ALIASES)
    unknown = handled - _members()
    assert not unknown, (
        f"The bridge maps statuses that `MarkingStatus` does not allow: {sorted(unknown)}."
    )


def test_an_alias_resolves_to_a_status_the_bridge_can_actually_convert() -> None:
    """An alias pointing at another alias, or at nothing, fails at conversion rather than here."""
    targets = set(FINDING_STATUS_SIDE) | set(NON_FINDING_REASONS)
    for source, target in STATUS_ALIASES.items():
        assert target in targets, (
            f"STATUS_ALIASES maps {source!r} to {target!r}, which is neither a finding status nor "
            "a non-finding one."
        )


def test_no_status_is_both_a_finding_and_a_non_finding() -> None:
    overlap = set(FINDING_STATUS_SIDE) & set(NON_FINDING_REASONS)
    assert not overlap, f"Statuses claimed by both maps: {sorted(overlap)}"


def test_mismatched_is_changed() -> None:
    """Pinned against the UI, which counts them together in ChecklistPanel and ManualMarkingList."""
    assert STATUS_ALIASES.get("MISMATCHED") == "CHANGED"
