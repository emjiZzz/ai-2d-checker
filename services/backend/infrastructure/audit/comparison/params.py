"""Every tuning constant on the deterministic comparison path, in one frozen object.

Stage 0.5a of [[AI Maturity Ladder — Staged Plan]]. Scope per
[[ADR-004 Deterministic-Only Scope]]: this is now the highest-value stage in the plan, because
all of these live on the only method under development.

The gap analysis is blunt about what these are:

> *"Every heuristic constant is a judgement call… None are measured optima."*

and the marking reconciler's fuzzy-pass guards were *"calibrated against one observed case."*
Twenty numbers, each a guess, each currently reachable only by editing the module it happens to
live in. This module makes them addressable so the Stage 0.5 sweep can move them one at a time
and measure the result.

## `DEFAULT_PARAMS` is the source of truth; the modules read from it

Each module now derives its constant from `DEFAULT_PARAMS` rather than declaring a literal:

    STRICT_RADIUS_ABS = DEFAULT_PARAMS.strict_radius_abs

That is provably behaviour-neutral — the values are copied byte-for-byte, and
`tests/test_comparison_params.py` asserts identical engine output across the whole corpus
before and after. **This has to be provable**, because the sweep that follows compares runs
against each other: if the refactor moved anything, the sweep would measure the refactor rather
than the thresholds.

## Why the module constants stayed, instead of threading a params object through

The honest reason is blast radius. These twenty values are read from inside
`spatial_differ`, `reconciler`, `marking_reconciler`, `zone_detector`, `coordinate_resolver`
and `bom/anchors` — deep in a call tree whose signatures would all have to change. That is a
large, regression-prone diff to land in the same breath as the thing it is supposed to make
measurable.

So the sweep uses `sweep_override()` instead, which rebinds the module globals for the duration
of a block and restores them afterwards.

> [!WARNING] `sweep_override()` mutates module-level state and is **not** concurrency-safe.
> It exists for the single-threaded offline sweep runner and nothing else. Two comparisons
> running concurrently under different overrides would read each other's constants. Do not
> call it from request-handling code; if per-client thresholds are ever wanted at runtime,
> thread a params object properly at that point — that is the real fix and this is not it.
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from dataclasses import dataclass, fields, replace
from typing import Any

# Where each parameter is consumed. The sweep needs this to rebind the right module global,
# and it doubles as the map from "a number I want to change" to "the code that reads it".
_BINDINGS: dict[str, tuple[str, str]] = {
    # spatial_differ — matching radii and the CHANGED gate
    "strict_radius_norm": ("..comparison.spatial_differ", "STRICT_RADIUS_NORM"),
    "twin_threshold_norm": ("..comparison.spatial_differ", "TWIN_THRESHOLD_NORM"),
    "fuzzy_threshold_norm": ("..comparison.spatial_differ", "FUZZY_THRESHOLD_NORM"),
    "strict_radius_abs": ("..comparison.spatial_differ", "STRICT_RADIUS_ABS"),
    "twin_threshold_abs": ("..comparison.spatial_differ", "TWIN_THRESHOLD_ABS"),
    "fuzzy_threshold_abs": ("..comparison.spatial_differ", "FUZZY_THRESHOLD_ABS"),
    "changed_similarity_floor": ("..comparison.spatial_differ", "CHANGED_SIMILARITY_FLOOR"),
    # NOTE: `match_radius_mm` used to sit here, bound to `comparison/reconciler.py`. Both are
    # gone — the reconciler was the hybrid method's cross-generator matcher. Its one surviving
    # reader was the eval scorer, so the constant moved to `eval/scorer.py` as
    # `SPATIAL_MATCH_RADIUS_MM` and is deliberately NOT swept: it decides how the scorer pairs
    # a prediction with an expected finding, so changing it moves F1 with no engine behaviour
    # changing at all. Do not add it back.
    # marking_reconciler — the fuzzy pass, calibrated against one observed case
    "similarity_threshold": ("..comparison.marking_reconciler", "SIMILARITY_THRESHOLD"),
    "ambiguity_margin": ("..comparison.marking_reconciler", "AMBIGUITY_MARGIN"),
    "min_fuzzy_length": ("..comparison.marking_reconciler", "MIN_FUZZY_LENGTH"),
    "max_normalized_move": ("..comparison.marking_reconciler", "MAX_NORMALIZED_MOVE"),
    # zone_detector — the tier the plan warns about; see `ZONE_PARAMS`
    "cluster_radius": ("..bom.zone_detector", "CLUSTER_RADIUS"),
    "min_iso_ellipses": ("..bom.zone_detector", "MIN_ISO_ELLIPSES"),
    "iso_block_dominance": ("..bom.zone_detector", "ISO_BLOCK_DOMINANCE"),
    "iso_cluster_radius_fraction": ("..bom.zone_detector", "ISO_CLUSTER_RADIUS_FRACTION"),
    "bbox_padding": ("..bom.zone_detector", "BBOX_PADDING"),
    "grid_label_margin_fraction": ("..bom.zone_detector", "GRID_LABEL_MARGIN_FRACTION"),
    # coordinate_resolver / anchors
    "label_proximity_tolerance_mm": (
        "..comparison.coordinate_resolver",
        "LABEL_PROXIMITY_TOLERANCE_MM",
    ),
    "char_width_ratio": ("..bom.anchors", "_CHAR_WIDTH_RATIO"),
}

# Zone constants are **not** safe to sweep alongside the matching ones. They feed `safe_filter`,
# zone templates and `views_exclusions()`, and users have hand-pinned templates whose stored
# fractions can be silently invalidated by moving `BBOX_PADDING` or `CLUSTER_RADIUS`. The plan
# requires a separate pass with an explicit "pinned templates still resolve" assertion.
# See [[Gotcha - Global Default Zone Template & the Aspect Caveat]].
ZONE_PARAMS: frozenset[str] = frozenset(
    {
        "cluster_radius",
        "min_iso_ellipses",
        "iso_block_dominance",
        "iso_cluster_radius_fraction",
        "bbox_padding",
        "grid_label_margin_fraction",
    }
)


@dataclass(frozen=True)
class ComparisonParams:
    """The deterministic engine's tuning surface.

    Values are today's, byte-for-byte. Each field's comment records what is known about *why*
    it holds that value — which for most of them is "nothing", and saying so is the point.
    """

    # --- spatial matching -------------------------------------------------
    # Normalized against the sheet diagonal; direct conversions of the absolute values below,
    # measured on the corpus reference sheet (1155 x 816.75, diagonal 1414.6).
    strict_radius_norm: float = 0.005
    twin_threshold_norm: float = 0.010
    fuzzy_threshold_norm: float = 0.150
    # Absolute fallbacks in CAD units, used only when a drawing has no usable render_bounds.
    strict_radius_abs: float = 5.0
    twin_threshold_abs: float = 10.0
    fuzzy_threshold_abs: float = 150.0
    # The one constant here with a recorded derivation: unrelated notes scored 0.00–0.14 and a
    # genuine edit scored 0.75 on the KEMCO pair, so 0.40 sits in the gap. Two data points.
    changed_similarity_floor: float = 0.40

    # --- marking reconciliation (calibrated against one observed case) ----
    similarity_threshold: float = 0.82
    ambiguity_margin: float = 0.08
    min_fuzzy_length: int = 4
    max_normalized_move: float = 0.25

    # --- zone detection (sweep separately — see ZONE_PARAMS) --------------
    cluster_radius: float = 200.0
    min_iso_ellipses: int = 3
    iso_block_dominance: float = 0.6
    iso_cluster_radius_fraction: float = 0.15
    # Absolute, deliberately: a fractional version was measured across the 6-drawing corpus and
    # rejected — it moved cross-sheet spread by under half a point and made two zones worse.
    bbox_padding: float = 30.0
    grid_label_margin_fraction: float = 0.09

    # --- resolution / anchors ---------------------------------------------
    label_proximity_tolerance_mm: float = 3.0
    char_width_ratio: float = 0.6

    def with_value(self, name: str, value: Any) -> ComparisonParams:
        """A copy with one parameter changed — the sweep's unit of work."""
        if name not in _BINDINGS:
            raise KeyError(f"Unknown comparison parameter {name!r}. Known: {sorted(_BINDINGS)}")
        return replace(self, **{name: value})

    @property
    def matching_params(self) -> tuple[str, ...]:
        """Parameters safe to sweep together — everything that is not a zone constant."""
        return tuple(f.name for f in fields(self) if f.name not in ZONE_PARAMS)


DEFAULT_PARAMS = ComparisonParams()


def _resolve(module_path: str) -> Any:
    from importlib import import_module

    return import_module(module_path, package=__package__)


def current_params() -> ComparisonParams:
    """Read the values the modules are *actually* using right now.

    Not the same thing as `DEFAULT_PARAMS`: inside `sweep_override()` they differ, and a sweep
    that reported the defaults while running overrides would be worse than useless.
    """
    values = {}
    for name, (module_path, attribute) in _BINDINGS.items():
        values[name] = getattr(_resolve(module_path), attribute)
    return ComparisonParams(**values)


@contextlib.contextmanager
def sweep_override(params: ComparisonParams) -> Iterator[ComparisonParams]:
    """Rebind the module constants for the duration of a block, then restore them.

    **Single-threaded offline use only** — see the module docstring. Restoration is in a
    `finally`, so an exception inside the block cannot leave the engine permanently retuned;
    that failure mode would silently poison every subsequent measurement in the process.
    """
    previous: dict[str, tuple[Any, str, Any]] = {}
    try:
        for name, (module_path, attribute) in _BINDINGS.items():
            module = _resolve(module_path)
            previous[name] = (module, attribute, getattr(module, attribute))
            setattr(module, attribute, getattr(params, name))
        yield params
    finally:
        for module, attribute, value in previous.values():
            setattr(module, attribute, value)
