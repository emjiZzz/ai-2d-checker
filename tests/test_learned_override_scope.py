"""A human's dismissal must not silently suppress unrelated findings.

The defect this file exists for, reported from live use 2026-08-17 and measured on
`M745230A01`: the checker saw a marker pairing the dimension `25` on the reference with `60` on
the revision and labelling it MATCHED. The deterministic engine had reported it as CHANGED.

`_decide`'s substring branch compared the stored override and the marking in both directions
with a 2-character floor:

```python
(len(norm_orig) >= 2 and norm_orig in em_val)   # the broken half
```

So a marking whose value was `"25"` matched any override key *containing* `"25"` — including
`center0.25mm`, `continuous0.25mm` and `dashed0.25mm`, all of which the checker had legitimately
dismissed because `line_attribute_differ` reports line attributes as ADDED on a re-traced
revision.

The resulting loop is the worst shape available for human-in-the-loop learning: dismissing a
false positive manufactured false negatives. Every correction made the tool quieter *and* less
correct, and nothing in the UI explained why. Measured on that one pair, 12 of 75 findings were
force-matched, including three real dimension changes.

Both directions of the hazard are pinned below: a marking must not inherit an override it is
merely a *fragment* of, and a numeric override must not match a *longer* number containing it.
"""
from __future__ import annotations

import pytest

from services.backend.infrastructure.learning.inference import (
    MIN_OVERRIDE_SUBSTRING_CHARS,
    _decide,
    _override_applies,
)


def _fires(override: str, *, details: str = "", text: str = "", orig: str = "") -> bool:
    return _override_applies(override, details, text, orig)


# ---------------------------------------------------------------------------
# The measured defect
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "override",
    ["center0.25mm", "center0.25mmx5", "continuous0.25mm", "dashed0.25mm", "125"],
)
def test_a_dimension_does_not_inherit_an_override_it_is_only_a_fragment_of(override):
    """`25` must not inherit a dismissal recorded for `CENTER 0.25MM`.

    This is the exact live case: three real dimension changes on M745230A01 were reported to the
    checker as MATCHED because of this.
    """
    assert not _fires(override, text="60", orig="25")
    assert not _fires(override, text="25", orig="55")


def test_a_numeric_override_does_not_match_a_longer_number_containing_it():
    """The symmetric hazard, in the direction that survives: `25` and `125` are different values
    however many characters they share."""
    assert not _fires("25", text="125", orig="130")
    assert not _fires("25", text="0.25", orig="")
    assert _fires("25", text="25", orig=""), "an exact numeric match must still apply"


def test_a_short_non_numeric_override_must_match_outright():
    """Below the substring floor a value identifies nothing; `Ａ` normalised to `a` would
    otherwise fire on every marking whose details contain the letter."""
    short = "ab"
    assert len(short) < MIN_OVERRIDE_SUBSTRING_CHARS
    assert not _fires(short, details="a large abstract note about something")
    assert _fires(short, text="ab")


# ---------------------------------------------------------------------------
# What must keep working
# ---------------------------------------------------------------------------

def test_an_override_still_applies_to_the_finding_it_was_recorded_for():
    assert _fires("center0.25mm", text="center0.25mm")
    assert _fires("center0.25mm", orig="center0.25mm")
    assert _fires("center0.25mm", details="center0.25mm")


def test_an_override_still_applies_where_it_appears_inside_a_longer_description():
    """The forward direction is the useful one and is deliberately kept: a dismissal recorded for
    `center0.25mm` should still fire on a marking whose details spell out more around it."""
    assert _fires("center0.25mm", details="lineattributecenter0.25mmx5addedintrace")


def test_an_empty_override_or_an_empty_marking_never_fires():
    assert not _fires("", text="anything")
    assert not _fires("center0.25mm")


# ---------------------------------------------------------------------------
# Through `_decide`, which is what actually runs
# ---------------------------------------------------------------------------

def _bundle(matched: set[str] | None = None, changed: set[str] | None = None) -> dict:
    return {
        "exact_matched": matched or set(),
        "exact_changed": changed or set(),
        "exact_category": {},
        "verdict_clf": None,
    }


def test_the_live_case_end_to_end():
    """M009 on M745230A01: ref `25`, rev `60`, CHANGED, against a corpus that has dismissed
    `CENTER 0.25MM`. It must stay CHANGED."""
    marking = {
        "status": "CHANGED",
        "category": "drawing_views",
        "text_content": "60",
        "original_value": "25",
        "details": "",
    }
    bundle = _bundle(matched={"drawing_views|center0.25mm", "drawing_views|continuous0.25mmx1"})

    new_status, _new_cat = _decide(marking, bundle, verdict_ready=False)
    assert new_status is None, (
        "a dismissal of the line attribute CENTER 0.25MM suppressed a real dimension change"
    )


def test_a_genuine_dismissal_still_suppresses_its_own_finding():
    """The other half: the override mechanism must keep working, or a checker's correction is
    ignored and they click it again forever."""
    marking = {
        "status": "ADDED",
        "category": "drawing_views",
        "text_content": "CONTINUOUS 1mm",
        "original_value": "",
        "details": "",
    }
    bundle = _bundle(matched={"drawing_views|continuous1mm"})

    new_status, _ = _decide(marking, bundle, verdict_ready=False)
    assert new_status == "MATCHED"


def test_the_same_scoping_applies_to_confirmations_not_only_dismissals():
    """`exact_changed` runs the identical comparison, so it had the identical defect — a
    confirmation of `center0.25mm` would have promoted every finding involving `25`."""
    marking = {
        "status": "MATCHED",
        "category": "drawing_views",
        "text_content": "60",
        "original_value": "25",
        "details": "",
    }
    bundle = _bundle(changed={"drawing_views|center0.25mm"})

    new_status, _ = _decide(marking, bundle, verdict_ready=False)
    assert new_status is None
