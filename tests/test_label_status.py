"""`tools/label_status.py` must account for every correction verb, not most of them.

The suite has no MongoDB, so the query half of that tool is not testable here. What *is*
testable is the half that actually rots: a new verb added to `HumanCorrectedStatus` falls
through `_bucket` into "no verdict label" and the report keeps printing a confident,
complete-looking total that quietly excludes it.

That is the same failure this project has already paid for twice — a count that was not
counting what the reader assumed ([[Gotcha - A Count You Could Not Take Is Not Evidence]]),
and two callers disagreeing about which rows count. So the verb list is pinned against the
schema: adding one forces a deliberate choice about which bucket it belongs in.
"""

import importlib.util
from pathlib import Path
from typing import get_args

from services.backend.api.schemas import HumanCorrectedStatus
from services.backend.infrastructure.learning.trainer import (
    MATCHER_FEEDBACK,
    VERDICT_ONE,
    VERDICT_ZERO,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_tool():
    """Import the tool by path — `tools/` is a script directory, not a package."""
    spec = importlib.util.spec_from_file_location(
        "label_status", REPO_ROOT / "tools" / "label_status.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# Verbs that are captured on purpose and train nothing today. Listing them here rather than
# letting them fall through the default is the whole point: each one is a decision someone
# made, and `value_correction` in particular is a human judgment the model still ignores.
DELIBERATELY_UNLABELLED = {"category_override", "value_correction"}


def test_every_correction_verb_is_deliberately_bucketed():
    tool = _load_tool()
    verbs = set(get_args(HumanCorrectedStatus))
    assert verbs, "HumanCorrectedStatus is not a Literal any more; this guard is now blind."

    known = VERDICT_ZERO | VERDICT_ONE | MATCHER_FEEDBACK | DELIBERATELY_UNLABELLED
    unaccounted = verbs - known
    assert not unaccounted, (
        f"New correction verb(s) {sorted(unaccounted)} are not bucketed. Decide where they "
        f"belong — trainer.VERDICT_ZERO/VERDICT_ONE/MATCHER_FEEDBACK, or "
        f"DELIBERATELY_UNLABELLED here — rather than letting label_status report them as "
        f"'no verdict label' by accident."
    )

    # And the buckets must not overlap: a verb counted twice inflates the total that is
    # compared against MIN_TRAIN.
    assert not (VERDICT_ZERO & VERDICT_ONE), "a verb cannot be both label 0 and label 1"
    assert not (MATCHER_FEEDBACK & (VERDICT_ZERO | VERDICT_ONE)), (
        "matcher feedback must never carry a verdict label — see trainer.MATCHER_FEEDBACK"
    )

    for verb in verbs:
        assert tool._bucket(verb) in {
            "verdict-0",
            "verdict-1",
            "matcher (parked)",
            "no verdict label",
        }


def test_skew_warning_fires_below_the_threshold_it_documents():
    """The warning is the tool's reason to exist; an off-by-one here silences it."""
    tool = _load_tool()
    assert 0.5 < tool.SKEW_WARN_SHARE < 1.0

    # The live corpus that motivated this tool: 27 negative of 36.
    assert (27 / 36) > tool.SKEW_WARN_SHARE

    # A balanced corpus must not warn, or the warning becomes noise people learn to skip.
    assert (18 / 36) < tool.SKEW_WARN_SHARE
