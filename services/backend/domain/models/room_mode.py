"""What a Room is for: an AI comparison, or a manual engineer check.

Separate from `comparison_method`, which names which engine runs. A manual check runs none, so
folding the two would make one field answer both "which engine" and "whether any engine", and
would resurrect the method picker ADR-006 removed. A manual-check room still records
`deterministic`; it simply never invokes it.

It is a property of the room rather than a view toggle so the workflows cannot overlap: a manual
room never shows engine findings. That is load-bearing, not cosmetic. A checker who can see what
the engine concluded is not an independent observer, and independence is the only thing that
makes these markings worth more than the corrections `audit_feedback` already collects.

`AI_COMPARISON` is the default, so rooms predating this field load unchanged. Do not write a
migration: the absent field and the default mean the same thing.
"""

from typing import Final, Literal

#: What the room is for. Extend deliberately — a third value means a third workflow, not a
#: third rendering of the same one.
RoomMode = Literal["ai_comparison", "manual_check"]

AI_COMPARISON: Final[str] = "ai_comparison"
MANUAL_CHECK: Final[str] = "manual_check"

_VALID: Final[frozenset[str]] = frozenset({AI_COMPARISON, MANUAL_CHECK})


def normalize_room_mode(value: object) -> str:
    """Coerce to a known mode, defaulting rather than raising.

    A `mode="before"` validator, so downstream sees one of two spellings. A document predating
    the field arrives as `None` and becomes an AI comparison room, which is what it was. An
    unrecognised string also defaults: a room that cannot open at all is a worse failure than one
    that opens in the wrong mode, which is visible and one click from correct.
    """
    if isinstance(value, str) and value in _VALID:
        return value
    return AI_COMPARISON
