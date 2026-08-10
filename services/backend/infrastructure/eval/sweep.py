"""Move one tuning constant at a time and measure what happens — Stage 0.5b.

> [!WARNING] This is a **sensitivity analysis, not a calibration.**
> Since the 2026-08-05 rebuild the corpus is 36 mutation pairs from **one drawing family**,
> and mutation pairs are drawn from the engine's own comparison pool. A best F1 found here is
> the best value *for this sheet, against synthetic edits* — fitting `DEFAULT_PARAMS` to it
> would be fitting the engine to the mutator. `sweep.py` therefore reports spreads and refuses
> to recommend values; `apply_best()` does not exist, deliberately.

## What it *can* answer

Three questions that do not need a representative corpus, only a working one:

1. **Which constants move nothing?** A parameter flat across its whole declared range — on
   detection F1 *and* on status/category exactness — is not a tuning knob on this corpus. It
   is either dead code, dominated by another constant, or guarding a case these pairs never
   hit. Every one of those is a finding worth recording, and per `CLAUDE.md` constraint 4 a
   measured-and-rejected idea is worth as much as one that worked.
2. **Which sit on a cliff?** A constant where one step changes F1 sharply is fragile — worth
   knowing before someone "tidies" it, and worth prioritising when a real corpus arrives.
3. **Is the current value even near the middle of its useful range?** The plan notes several
   were *"calibrated against one observed case"*; a default sitting at the edge of a plateau is
   a different risk from one sitting in the middle.

## Why coordinate descent and not a grid

Sixteen-plus dimensions of grid is nonsense at any corpus size this project will have. One
parameter at a time, from the same baseline, is also what makes the output readable: each row
is "this constant, alone, moved the engine by this much".
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from ..audit.comparison.params import DEFAULT_PARAMS, ZONE_PARAMS, ComparisonParams, sweep_override
from .corpus import CorpusPair, EvalCorpus
from .scorer import CorpusScore, Prediction, score_pair

# Declared ranges, per parameter. Deliberately hand-written rather than generated as
# `default * [0.5, 0.75, 1.5, 2]`: several of these are probabilities or counts where a
# multiplicative range is meaningless, and a range that wanders outside a constant's valid
# domain produces a crash or a meaningless number rather than a data point.
SWEEP_RANGES: dict[str, list[Any]] = {
    # Normalized radii — fractions of the sheet diagonal.
    "strict_radius_norm": [0.001, 0.0025, 0.005, 0.01, 0.02],
    "twin_threshold_norm": [0.005, 0.0075, 0.010, 0.02, 0.04],
    "fuzzy_threshold_norm": [0.05, 0.10, 0.150, 0.25, 0.40],
    # Absolute fallbacks — only reachable on a drawing with no usable render_bounds, so these
    # are expected to be flat on a corpus where every pair has one. That expectation is itself
    # worth confirming rather than assuming.
    "strict_radius_abs": [1.0, 2.5, 5.0, 10.0, 20.0],
    "twin_threshold_abs": [5.0, 7.5, 10.0, 20.0, 40.0],
    "fuzzy_threshold_abs": [50.0, 100.0, 150.0, 250.0, 400.0],
    # The CHANGED gate. 1.0 admits only identical text; 0.0 admits any pairing at all.
    "changed_similarity_floor": [0.0, 0.2, 0.40, 0.6, 0.8, 1.0],
    # REMOVED (ADR-006): `match_radius_mm`. It was the cross-generator radius, and it was in
    # this table so the sweep could *show* it inert rather than assume it. `hybrid` is now
    # gone, and the constant survives only as the eval scorer's own
    # `SPATIAL_MATCH_RADIUS_MM` — which must never be swept, because it moves the scorer's
    # prediction↔label pairing and would register as an F1 change with the engine untouched.
    # This takes the default pass from 14 constants to 13.
    # Marking reconciliation — "calibrated against one observed case".
    "similarity_threshold": [0.6, 0.7, 0.82, 0.9, 0.98],
    "ambiguity_margin": [0.0, 0.04, 0.08, 0.16, 0.32],
    "min_fuzzy_length": [1, 2, 3, 4, 6, 10],
    "max_normalized_move": [0.05, 0.15, 0.25, 0.5, 1.0],
    # Structured-value suppression. 1 restores the pre-v43 behaviour, where a BOM row numbered
    # `1` deleted a standalone `１` from the notes pool on both sides and made its removal
    # unreportable. Swept upward too, because the ceiling is a real trade: raise it far enough
    # and a genuine title-block value (`8.65`) stops being suppressed and gets double-reported.
    "min_structured_value_length": [1, 2, 3, 4, 6],
    # Resolution / anchors.
    "label_proximity_tolerance_mm": [0.5, 1.5, 3.0, 6.0, 12.0],
    "char_width_ratio": [0.4, 0.5, 0.6, 0.7, 0.85],
    # --- zone tier: swept only on explicit request, never in the default pass -------------
    "cluster_radius": [50.0, 100.0, 200.0, 400.0, 800.0],
    "min_iso_ellipses": [1, 2, 3, 5, 8],
    "iso_block_dominance": [0.3, 0.45, 0.6, 0.75, 0.9],
    "iso_cluster_radius_fraction": [0.05, 0.10, 0.15, 0.25, 0.40],
    "bbox_padding": [0.0, 15.0, 30.0, 60.0, 120.0],
    "grid_label_margin_fraction": [0.03, 0.06, 0.09, 0.15, 0.25],
}

# Below this, a spread is noise rather than signal at this corpus size — 36 pairs and 55
# expected findings means one finding flipping is worth roughly 0.01 F1.
FLAT_THRESHOLD = 0.01


@dataclass(frozen=True)
class Measurement:
    """What one parameter value scored.

    **F1 alone is too coarse to sweep on**, and the first run of this sweep proved it:
    `changed_similarity_floor` reported a spread of 0.000 across its entire range, while
    `test_an_override_changes_what_the_engine_reports` had already shown the same override
    changing real engine output. Both were right. The scorer matches a finding to its label
    *before* comparing status, so a constant that flips CHANGED to ADDED+REMOVED moves the
    status-confusion matrix without moving detection at all.

    Reporting F1 only would have produced the most believable possible wrong conclusion —
    "none of these constants matter" — from a corpus that simply was not being asked.
    """

    f1: float
    exactness: float  # fraction of matched findings agreeing on BOTH status and category
    findings: int  # predictions the engine emitted, a coarse volume signal

    def distance(self, other: Measurement) -> float:
        """How far apart two settings are. Max of the two rates, not a sum: they measure
        different failures and averaging would let a large move in one hide behind the other."""
        return max(abs(self.f1 - other.f1), abs(self.exactness - other.exactness))


@dataclass
class ParamSensitivity:
    name: str
    default: Any
    values: list[Any]
    scores: list[Measurement | None] = field(default_factory=list)

    @property
    def measured(self) -> list[Measurement]:
        return [s for s in self.scores if s is not None]

    @property
    def spread(self) -> float:
        """The widest distance between any two settings, over F1 *and* exactness."""
        seen = self.measured
        if len(seen) < 2:
            return 0.0
        return max(a.distance(b) for a in seen for b in seen)

    @property
    def f1_spread(self) -> float:
        seen = [m.f1 for m in self.measured]
        return max(seen) - min(seen) if seen else 0.0

    @property
    def exactness_spread(self) -> float:
        seen = [m.exactness for m in self.measured]
        return max(seen) - min(seen) if seen else 0.0

    @property
    def is_flat(self) -> bool:
        """Moved nothing across its whole declared range — on this corpus."""
        return self.spread < FLAT_THRESHOLD

    @property
    def best(self) -> tuple[Any, Measurement] | None:
        """The highest-F1 value. **Reported, never applied.** See the module docstring."""
        pairs = [(v, s) for v, s in zip(self.values, self.scores, strict=True) if s is not None]
        return max(pairs, key=lambda item: item[1].f1) if pairs else None

    @property
    def default_score(self) -> Measurement | None:
        for value, score in zip(self.values, self.scores, strict=True):
            if value == self.default:
                return score
        return None


@dataclass
class SweepResult:
    baseline: Measurement
    sensitivities: list[ParamSensitivity]
    seconds: float
    pairs: int

    @property
    def flat(self) -> list[ParamSensitivity]:
        return [s for s in self.sensitivities if s.is_flat]

    @property
    def live(self) -> list[ParamSensitivity]:
        return sorted(
            (s for s in self.sensitivities if not s.is_flat),
            key=lambda s: s.spread,
            reverse=True,
        )


def _preload(corpus: EvalCorpus) -> list[tuple[CorpusPair, tuple]]:
    """Load and verify every payload once.

    A sweep runs the engine ~70 times over the same pairs; re-reading and re-hashing ~1 MB of
    JSONL per pair per run would dominate the wall clock and measure disk, not thresholds.
    """
    loaded = []
    for pair in corpus.pairs:
        if pair.labels is None:
            continue
        pair.restore_ocr_cache()
        loaded.append((pair, pair.load()))
    return loaded


async def _score(loaded: list[tuple[CorpusPair, tuple]]) -> Measurement | None:
    from ..audit.comparison.orchestrator import generate_deterministic_candidates

    score = CorpusScore()
    emitted = 0
    for pair, (ref_drawing, rev_drawing, ref_entities, rev_entities) in loaded:
        # The corpus's own hand-aligned zone boxes, exactly as `runner.py` passes them.
        # Omitting this was a real defect for two days: the sweep predates the `zone_template`
        # seam by one day, so it kept sending the engine back to a Mongo lookup that does not
        # exist offline and silently degraded to plain detection. Every Stage 0.5b conclusion
        # — including "13 of 14 constants are flat" — was therefore measured against detector
        # boxes while `tools/eval.py` measured against the boxes users see. Symptom to
        # recognise: a sweep baseline far below the published eval baseline, plus
        # `[zone_template] Template lookup failed for '<signature>'` in the log.
        # See [[Gotcha - Zone Templates Vanish in Offline Eval]].
        candidates, _rollups, _warnings = await generate_deterministic_candidates(
            ref_drawing,
            rev_drawing,
            ref_entities,
            rev_entities,
            zone_templates=(pair.ref.zone_template, pair.rev.zone_template),
        )
        predictions = [
            Prediction.from_candidate(c)
            for c in candidates
            if str(getattr(c, "status", "")) != "MATCHED"
        ]
        emitted += len(predictions)
        score.pair_scores.append(score_pair(pair, predictions, ref_entities, rev_entities))

    matches = [m for p in score.scored for m in p.matches]
    exact = sum(1 for m in matches if m.status_agrees and m.category_agrees)
    return Measurement(
        f1=score.metrics()["f1"] or 0.0,
        exactness=exact / len(matches) if matches else 0.0,
        findings=emitted,
    )


async def run_sweep(
    corpus: EvalCorpus,
    *,
    names: list[str] | None = None,
    include_zone: bool = False,
    baseline: ComparisonParams = DEFAULT_PARAMS,
    progress: Any = None,
) -> SweepResult:
    """Coordinate descent from `baseline`, one parameter at a time.

    Zone constants are excluded unless asked for: they feed `safe_filter`, zone templates and
    `views_exclusions()`, and users have hand-pinned templates whose stored fractions moving
    them can silently invalidate. The plan requires a separate pass with a "pinned templates
    still resolve" assertion, which this does not perform.
    """
    started = time.time()
    loaded = _preload(corpus)
    if not loaded:
        raise ValueError("No labelled pairs in the corpus — nothing to sweep against.")

    selected = names or [n for n in SWEEP_RANGES if include_zone or n not in ZONE_PARAMS]
    unknown = [n for n in selected if n not in SWEEP_RANGES]
    if unknown:
        raise KeyError(f"No declared sweep range for {unknown}. Add one to SWEEP_RANGES.")

    with sweep_override(baseline):
        baseline_measurement = await _score(loaded) or Measurement(0.0, 0.0, 0)

    sensitivities: list[ParamSensitivity] = []
    for name in selected:
        values = SWEEP_RANGES[name]
        sensitivity = ParamSensitivity(name, getattr(baseline, name), list(values))
        for value in values:
            try:
                with sweep_override(baseline.with_value(name, value)):
                    sensitivity.scores.append(await _score(loaded))
            except Exception as exc:  # a value outside the constant's valid domain
                if progress:
                    progress(f"  {name}={value!r} raised {type(exc).__name__}: {exc}")
                sensitivity.scores.append(None)
        sensitivities.append(sensitivity)
        if progress:
            progress(
                f"{name}: spread {sensitivity.spread:.3f} "
                f"(F1 {sensitivity.f1_spread:.3f}, exactness {sensitivity.exactness_spread:.3f})"
            )

    return SweepResult(
        baseline=baseline_measurement,
        sensitivities=sensitivities,
        seconds=time.time() - started,
        pairs=len(loaded),
    )


def format_sweep(result: SweepResult) -> str:
    lines = [
        "=" * 78,
        "Tuning-constant sensitivity — NOT a calibration",
        "=" * 78,
        "",
        f"  baseline F1 {result.baseline.f1:.3f}, exactness {result.baseline.exactness:.3f}, "
        f"{result.baseline.findings} findings over {result.pairs} pair(s), {result.seconds:.0f}s",
        "",
        "  'exactness' = of the findings matched to a label, the fraction agreeing on BOTH",
        "  status and category. Swept alongside F1 because the scorer matches before it",
        "  compares status, so a constant can reshape every verdict without moving detection.",
        "",
        "  These are spreads on ONE drawing family of synthetic edits. A best value here is",
        "  the best value for that sheet against the mutator, not an optimum. Nothing in this",
        "  report may be written into DEFAULT_PARAMS.",
        "",
    ]

    if result.live:
        lines += [
            "  MOVES SOMETHING (sorted by F1 spread across the declared range)",
            f"    {'parameter':30} {'default':>9} {'spread':>7} {'ΔF1':>7} {'Δexact':>7}",
        ]
        for item in result.live:
            lines.append(
                f"    {item.name:30} {str(item.default):>9} {item.spread:7.3f} "
                f"{item.f1_spread:7.3f} {item.exactness_spread:7.3f}"
            )
        lines.append("")

    if result.flat:
        lines += [
            "  MOVED NOTHING across its whole declared range",
            "    Each of these is a finding: dead on this corpus, dominated by another",
            "    constant, or guarding a case these 36 pairs never reach.",
            "",
        ]
        for s in result.flat:
            lines.append(f"    {s.name:30} default {s.default!r}, range {s.values}")
        lines.append("")

    lines += [
        "-" * 78,
        "  Read as: which knobs are connected to anything. NOT as which values to ship.",
        "  A real calibration needs human-labelled pairs across multiple sheet layouts,",
        "  leave-one-pair-out CV, and a held-out set touched exactly once.",
        "-" * 78,
    ]
    return "\n".join(lines)
