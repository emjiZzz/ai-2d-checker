"""The lift threshold is hand-mirrored across the language boundary; pin it so it cannot drift.

`MIN_MEANINGFUL_LIFT` exists twice — `tools/label_status.py` and
`apps/desktop/src/components/settings/LearningPanel.tsx` — because no runtime type sharing exists
between Python and TypeScript here. That is the same situation as the comparison taxonomy, which
`tests/test_taxonomy_consistency.py` handles the same way, and the rule this repo states for it is
blunt: unpinned deliberate duplication is just duplication.

Both numbers answer one question — *"below what lift over the majority-class baseline should we
tell a human the model is barely doing anything?"* — and a report and a UI that disagree about
that is worse than either alone, because the disagreement is invisible.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PANEL = REPO_ROOT / "apps/desktop/src/components/settings/LearningPanel.tsx"
LABEL_STATUS = REPO_ROOT / "tools/label_status.py"

_TS = re.compile(r"MIN_MEANINGFUL_LIFT\s*=\s*([0-9.]+)")
_PY = re.compile(r"^MIN_MEANINGFUL_LIFT\s*=\s*([0-9.]+)", re.M)


def _one(pattern: re.Pattern[str], path: Path, label: str) -> float:
    matches = pattern.findall(path.read_text(encoding="utf-8"))
    assert matches, f"MIN_MEANINGFUL_LIFT not found in {label} — did it get renamed?"
    assert len(matches) == 1, f"{len(matches)} definitions in {label}; there must be exactly one"
    return float(matches[0])


def test_the_lift_threshold_is_the_same_on_both_sides():
    assert _one(_PY, LABEL_STATUS, "tools/label_status.py") == _one(_TS, PANEL, "LearningPanel.tsx")


def test_the_backend_records_a_majority_baseline_for_the_panel_to_read():
    """The panel renders a baseline it never computes. If the trainer stops recording it, the
    comparison silently disappears from the UI rather than breaking — so assert it is produced."""
    from services.backend.infrastructure.learning.trainer import majority_class_baseline

    # 71 class-0 against 41 class-1 is the live corpus on 2026-08-17.
    assert majority_class_baseline({"0": 71, "1": 41}) == 0.6339
    assert majority_class_baseline({"0": 5, "1": 5}) == 0.5
    assert majority_class_baseline({}) is None, "no labels means no floor, not a floor of zero"


def test_a_single_class_corpus_reports_a_baseline_of_one():
    """Worth pinning because it is the most misleading case there is: with one class present, a
    model that always guesses it is 100% accurate and has learned nothing."""
    from services.backend.infrastructure.learning.trainer import majority_class_baseline

    assert majority_class_baseline({"0": 40}) == 1.0
