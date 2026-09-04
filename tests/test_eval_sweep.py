"""Stage 0.5b — the sensitivity sweep.

The sweep's job is to say which tuning constants are connected to anything. Its most dangerous
failure is not crashing — it is reporting *"nothing matters"*, which is extremely believable
and would retire twenty real knobs on a false reading.

That failure already happened once, on the first run: `changed_similarity_floor` came back with
a spread of 0.000 across its entire range, while `test_an_override_changes_what_the_engine_reports`
had independently shown the same override changing real engine output. Both were correct — the
scorer matches a finding to its label *before* comparing status, so a constant that flips
CHANGED into ADDED+REMOVED moves the status-confusion matrix without moving detection F1 at all.
`Measurement` now carries exactness alongside F1 for exactly that reason, and
`test_a_status_only_change_is_not_reported_as_flat` pins it.
"""

import pytest

from services.backend.infrastructure.audit.comparison.params import (
    DEFAULT_PARAMS,
    ZONE_PARAMS,
    ComparisonParams,
)
from services.backend.infrastructure.eval.sweep import (
    FLAT_THRESHOLD,
    SWEEP_RANGES,
    Measurement,
    ParamSensitivity,
    SweepResult,
    format_sweep,
)


def _sensitivity(name, default, values, measurements):
    item = ParamSensitivity(name=name, default=default, values=list(values))
    item.scores = list(measurements)
    return item


# ─── the metric has to see more than detection ────────────────────────────────────────


def test_a_status_only_change_is_not_reported_as_flat():
    """The bug that shipped in the first version. Identical F1, wholly different verdicts."""
    item = _sensitivity(
        "changed_similarity_floor",
        0.40,
        [0.0, 0.40, 1.0],
        [
            Measurement(f1=0.71, exactness=0.90, findings=46),
            Measurement(f1=0.71, exactness=0.55, findings=46),
            Measurement(f1=0.71, exactness=0.20, findings=46),
        ],
    )
    assert item.f1_spread == pytest.approx(0.0)
    assert item.exactness_spread == pytest.approx(0.70)
    assert not item.is_flat, (
        "A constant that reshapes every verdict while leaving detection untouched must not be "
        "reported as having no effect — that retires a real knob on a false reading."
    )


def test_distance_takes_the_max_not_the_mean():
    """Averaging would let a large move in one metric hide behind a flat one."""
    a = Measurement(f1=0.70, exactness=0.90, findings=10)
    b = Measurement(f1=0.70, exactness=0.40, findings=10)
    assert a.distance(b) == pytest.approx(0.50)


def test_a_genuinely_inert_parameter_is_flat():
    item = _sensitivity(
        "strict_radius_abs",
        5.0,
        [1.0, 5.0, 20.0],
        [Measurement(0.71, 0.9, 46)] * 3,
    )
    assert item.is_flat and item.spread == pytest.approx(0.0)


def test_flat_threshold_is_above_one_finding_of_noise():
    """At ~55 expected findings, one finding flipping is worth roughly 0.018 F1. A threshold
    below that would report noise as signal on every parameter."""
    assert FLAT_THRESHOLD >= 0.01


# ─── ranges ───────────────────────────────────────────────────────────────────────────


def test_every_parameter_has_a_declared_range():
    from dataclasses import fields

    missing = [f.name for f in fields(ComparisonParams) if f.name not in SWEEP_RANGES]
    assert not missing, f"No sweep range declared for {missing}; the sweep would skip them."


def test_every_range_contains_the_current_default():
    """Without the default in the range there is no baseline column to compare against, and
    'best' becomes meaningless — every parameter would look like an improvement."""
    for name, values in SWEEP_RANGES.items():
        assert getattr(DEFAULT_PARAMS, name) in values, (
            f"{name}'s range {values} omits its default {getattr(DEFAULT_PARAMS, name)!r}"
        )


def test_zone_parameters_have_ranges_but_are_not_in_the_default_pass():
    """They feed `safe_filter` and hand-pinned zone templates; sweeping them needs a
    'pinned templates still resolve' assertion the sweep does not perform."""
    for name in ZONE_PARAMS:
        assert name in SWEEP_RANGES
    default_pass = [n for n in SWEEP_RANGES if n not in ZONE_PARAMS]
    assert len(default_pass) == len(SWEEP_RANGES) - len(ZONE_PARAMS)
    assert "bbox_padding" not in default_pass


# ─── the report must not read as a recommendation ─────────────────────────────────────


def test_report_refuses_to_present_itself_as_a_calibration():
    result = SweepResult(
        baseline=Measurement(0.71, 0.9, 46),
        sensitivities=[
            _sensitivity("min_fuzzy_length", 4, [1, 4], [Measurement(0.71, 0.9, 46)] * 2)
        ],
        seconds=12.0,
        pairs=36,
    )
    report = format_sweep(result)
    assert "NOT a calibration" in report
    # Wrapped across lines in the report, so matched on the phrase rather than the sentence.
    assert "written into DEFAULT_PARAMS" in report
    assert "drawing family" in report
    assert "not an optimum" in report


def test_there_is_no_apply_best_function():
    """Deliberate absence. A one-click 'apply the best values' on a corpus of synthetic edits
    from a single sheet would fit the engine to the mutator, and would be the single easiest
    way to undo everything Stage 0 exists to establish."""
    from services.backend.infrastructure.eval import sweep

    assert not hasattr(sweep, "apply_best")
    assert not hasattr(sweep, "apply_sweep")


def test_the_sweep_passes_zone_templates_like_the_runner():
    """The sweep and the eval runner must reproduce the engine the SAME way.

    They did not for two days: `runner.py` passed `zone_templates=` (the 2026-08-06 seam that
    moved precision 0.78 -> 1.00) and `sweep.py`, which landed a day earlier, called
    `generate_deterministic_candidates` with four positional arguments and no templates. The
    engine fell back to a Mongo lookup that does not exist offline and degraded to plain
    detection, so the sweep's baseline read F1 0.68 against the eval's 0.92 on the same corpus
    and the same commit.

    Asserted on the source rather than by running a sweep, because the failure is an *omitted
    keyword argument* -- there is no return value to check, and a behavioural test would need a
    full corpus run to show a difference. See
    docs/vault/06 - .../Gotcha - The Sweep Never Got the Zone Template Seam.
    """
    import inspect

    from services.backend.infrastructure.eval import runner, sweep

    runner_src = inspect.getsource(runner)
    sweep_src = inspect.getsource(sweep)

    assert "zone_templates=" in runner_src, (
        "the runner stopped passing zone_templates -- if that is deliberate, this whole "
        "assertion is obsolete and the gotcha needs rewriting, not deleting"
    )
    assert "zone_templates=" in sweep_src, (
        "sweep.py calls generate_deterministic_candidates without zone_templates, so it scores "
        "against detector boxes while tools/eval.py scores against the hand-aligned ones. Every "
        "spread it reports would describe a zone regime the product does not use."
    )
