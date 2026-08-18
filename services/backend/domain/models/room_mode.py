"""What a Room is *for*: an AI comparison, or a manual engineer check.

## Why this is not `comparison_method`

`comparison_method` names **which engine compares two drawings**. It is a `Literal` of one
(`deterministic`) and ADR-006 deleted the picker that used to offer alternatives.

A manual check compares nothing — a human reads the drawings. Folding it into
`comparison_method` would make one field answer two different questions ("which engine ran" and
"did an engine run at all"), which is exactly the confusion `comparison_method.py`'s own
docstring exists to prevent, and it would resurrect a *method* picker ADR-006 removed on
purpose. So this is a separate axis, and the two are orthogonal: a manual-check room still
records `comparison_method` as `deterministic`, it simply never invokes it.

## Why it lives on the Room rather than being a toggle inside one

A room is the unit of work here. An engineer opening a manual-check room is *doing* a manual
check — the mode is a property of the job, not a view setting someone might have left on. It
also makes the two workflows non-overlapping by construction: an AI room never shows stamping
tools, and a manual room never shows engine findings. That second half is load-bearing rather
than cosmetic — a checker who can see what the engine concluded is no longer an independent
observer, and independence is the only reason these markings are worth more than the
corrections `audit_feedback` already collects.

## The default is permanent, not a migration window

Every room written before this field existed is an AI comparison room, and `AI_COMPARISON` is
the default, so those documents load unchanged with no migration. Do not add one: the absent
field and the default mean the same thing.
"""

from typing import Final, Literal

#: What the room is for. Extend deliberately — a third value means a third workflow, not a
#: third rendering of the same one.
RoomMode = Literal["ai_comparison", "manual_check"]

AI_COMPARISON: Final[str] = "ai_comparison"
MANUAL_CHECK: Final[str] = "manual_check"

_VALID: Final[frozenset[str]] = frozenset({AI_COMPARISON, MANUAL_CHECK})


def normalize_room_mode(value: object) -> str:
    """Coerce an incoming value to a known mode, defaulting rather than raising.

    Applied as a `mode="before"` validator so every consumer downstream sees exactly one of two
    spellings. A room document predating this field arrives as `None` and becomes an AI
    comparison room, which is what it always was.

    An *unrecognised* string also defaults rather than raising: this field decides which UI a
    room opens with, and a room that cannot be opened at all is a worse failure than a room
    that opens in the wrong mode — the second is visible and one click from correct.
    """
    if isinstance(value, str) and value in _VALID:
        return value
    return AI_COMPARISON
