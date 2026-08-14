"""Stage 0.5a — the tuning surface of the deterministic comparison engine.

Two things have to hold, and the second is the whole reason this stage exists separately from
the sweep it enables:

1. **The extraction moved nothing.** `DEFAULT_PARAMS` reproduces today's twenty constants
   byte-for-byte, and the engine's output over the corpus is identical before and after. If it
   were not, the Stage 0.5 sweep would be measuring the refactor rather than the thresholds,
   and every conclusion drawn from it would be wrong in a way nothing downstream could detect.
2. **The override mechanism works and always restores.** It rebinds module globals; a leak
   would leave the engine permanently retuned inside the process and silently poison every
   later measurement in the same run.

Scope note: per [[ADR-004 Deterministic-Only Scope]] these constants are the entire tuning
surface under development, which is why Stage 0.5 is now the highest-value stage in the plan.
"""

from dataclasses import fields

import pytest

from services.backend.infrastructure.audit.comparison import (
    coordinate_resolver,
    marking_reconciler,
    spatial_differ,
)
from services.backend.infrastructure.eval.scorer import SPATIAL_MATCH_RADIUS_MM
from services.backend.infrastructure.audit.comparison.params import (
    _BINDINGS,
    DEFAULT_PARAMS,
    ZONE_PARAMS,
    ComparisonParams,
    current_params,
    sweep_override,
)

# ─── the extraction is behaviour-neutral ──────────────────────────────────────────────


def test_modules_read_exactly_the_default_params():
    """The load-bearing assertion of this stage. `current_params()` reads what the modules are
    actually using; if it drifts from `DEFAULT_PARAMS`, the extraction changed behaviour."""
    assert current_params() == DEFAULT_PARAMS


@pytest.mark.parametrize(
    ("module", "attribute", "field_name"),
    [
        (spatial_differ, "STRICT_RADIUS_NORM", "strict_radius_norm"),
        (spatial_differ, "TWIN_THRESHOLD_NORM", "twin_threshold_norm"),
        (spatial_differ, "FUZZY_THRESHOLD_NORM", "fuzzy_threshold_norm"),
        (spatial_differ, "STRICT_RADIUS_ABS", "strict_radius_abs"),
        (spatial_differ, "TWIN_THRESHOLD_ABS", "twin_threshold_abs"),
        (spatial_differ, "FUZZY_THRESHOLD_ABS", "fuzzy_threshold_abs"),
        (spatial_differ, "CHANGED_SIMILARITY_FLOOR", "changed_similarity_floor"),
        (marking_reconciler, "SIMILARITY_THRESHOLD", "similarity_threshold"),
        (marking_reconciler, "AMBIGUITY_MARGIN", "ambiguity_margin"),
        (marking_reconciler, "MIN_FUZZY_LENGTH", "min_fuzzy_length"),
        (marking_reconciler, "MAX_NORMALIZED_MOVE", "max_normalized_move"),
        (coordinate_resolver, "LABEL_PROXIMITY_TOLERANCE_MM", "label_proximity_tolerance_mm"),
    ],
)
def test_each_constant_still_holds_its_original_value(module, attribute, field_name):
    assert getattr(module, attribute) == getattr(DEFAULT_PARAMS, field_name)


def test_the_scorer_radius_is_not_a_sweepable_engine_constant():
    """`match_radius_mm` was swept as an engine constant while living in the hybrid method's
    `reconciler.py`. Removing the AI methods left the eval scorer as its only reader, which
    exposed that it tunes the **measurement**: it decides which prediction the scorer pairs
    with which expected finding, so a sweep would move F1 with no engine behaviour changing.
    It keeps its old value, so scores are byte-identical, and it must stay out of the params."""
    assert SPATIAL_MATCH_RADIUS_MM == 35.0
    assert "match_radius_mm" not in {f.name for f in fields(ComparisonParams)}


def test_the_original_literals_are_preserved():
    """Spelled out rather than derived, so a typo in `DEFAULT_PARAMS` cannot pass by agreeing
    with itself. These are the values the v38 baseline was measured against."""
    assert (DEFAULT_PARAMS.strict_radius_norm, DEFAULT_PARAMS.strict_radius_abs) == (0.005, 5.0)
    assert (DEFAULT_PARAMS.twin_threshold_norm, DEFAULT_PARAMS.twin_threshold_abs) == (0.010, 10.0)
    assert (DEFAULT_PARAMS.fuzzy_threshold_norm, DEFAULT_PARAMS.fuzzy_threshold_abs) == (
        0.150,
        150.0,
    )
    assert DEFAULT_PARAMS.changed_similarity_floor == 0.40
    assert DEFAULT_PARAMS.similarity_threshold == 0.82
    assert DEFAULT_PARAMS.ambiguity_margin == 0.08
    assert DEFAULT_PARAMS.min_fuzzy_length == 4
    assert DEFAULT_PARAMS.max_normalized_move == 0.25
    assert DEFAULT_PARAMS.cluster_radius == 200.0
    assert DEFAULT_PARAMS.min_iso_ellipses == 3
    assert DEFAULT_PARAMS.iso_block_dominance == 0.6
    assert DEFAULT_PARAMS.iso_cluster_radius_fraction == 0.15
    assert DEFAULT_PARAMS.bbox_padding == 30.0
    assert DEFAULT_PARAMS.grid_label_margin_fraction == 0.09
    assert DEFAULT_PARAMS.label_proximity_tolerance_mm == 3.0
    assert DEFAULT_PARAMS.char_width_ratio == 0.6


def test_every_field_is_addressable_by_the_sweep():
    """A field with no binding is a constant the sweep silently cannot move — it would appear
    tunable and do nothing."""
    unreachable = [
        f.name for f in fields(ComparisonParams) if f.name not in DEFAULT_PARAMS.__dict__
    ]
    assert not unreachable
    for field in fields(ComparisonParams):
        DEFAULT_PARAMS.with_value(field.name, getattr(DEFAULT_PARAMS, field.name))


# ─── a binding must name the module that READS the constant ───────────────────────────
#
# `sweep_override` rebinds a module global. That only reaches the engine if the module it
# rebinds is the module whose code reads the name. Nothing else in this file checks that:
# `current_params()` reads through the same binding it writes through, so a binding pointing
# at a module that merely *declares* the constant agrees with itself perfectly while the
# engine runs on a copy somewhere else.
#
# The failure is silent and total — the sweep reports a swept parameter and measures a
# frozen one — and this repo has already paid for the same shape once, when `sweep.py` and
# `runner.py` each reproduced the engine call and the sweep measured F1 0.68 against the
# eval's 0.92 on the same corpus at the same commit, for four days.
#
# The move that creates it is ordinary: extracting a function to a new module carries the
# *read* out of the bound module and leaves the declaration behind.


def _module_source_tree(module_path: str):
    import ast
    from pathlib import Path

    from services.backend.infrastructure.audit.comparison.params import _resolve

    module = _resolve(module_path)
    return ast.parse(Path(module.__file__).read_text(encoding="utf-8")), Path(module.__file__)


@pytest.mark.parametrize(("field_name", "binding"), sorted(_BINDINGS.items()))
def test_the_bound_module_is_the_one_that_reads_the_constant(field_name, binding):
    """The bound module must both declare the name and read it back.

    `ast.walk` deliberately descends into nested functions: the only read of
    `MIN_STRUCTURED_VALUE_LENGTH` is ~250 lines inside `generate_deterministic_candidates`,
    and a check that only looked at module scope would miss it — and would keep passing if
    that function moved out, which is the exact case this test exists for.
    """
    import ast

    module_path, attribute = binding
    tree, source = _module_source_tree(module_path)
    names = [n for n in ast.walk(tree) if isinstance(n, ast.Name) and n.id == attribute]

    assert any(isinstance(n.ctx, ast.Store) for n in names), (
        f"{field_name!r} is bound to {module_path}, but {source.name} never assigns "
        f"{attribute}. `sweep_override` would setattr a name that module does not own."
    )
    assert any(isinstance(n.ctx, ast.Load) for n in names), (
        f"{field_name!r} is bound to {module_path}, which declares {attribute} but never "
        f"reads it. Whatever code does read it now lives elsewhere, so `sweep_override` "
        f"rebinds a constant nothing consumes: the sweep would report this parameter as "
        f"having no effect. Move the binding to the module holding the read."
    )


def test_no_second_module_declares_a_bound_constant():
    """A shadow copy is the other half of the same defect.

    If two modules both assign `MIN_STRUCTURED_VALUE_LENGTH`, the sweep rebinds one and the
    engine may read the other — and both hold the same literal today, so every value-equality
    assertion in this file still passes. Attribute access (`orchestrator.MIN_...`) is fine and
    intentionally not flagged; it resolves through the bound module at call time.
    """
    import ast
    from pathlib import Path

    from services.backend.infrastructure.audit.comparison.params import _resolve

    owner = {
        attribute: Path(_resolve(module_path).__file__).resolve()
        for module_path, attribute in _BINDINGS.values()
    }
    backend = Path(__file__).resolve().parent.parent / "services" / "backend"

    shadows = []
    for py in backend.rglob("*.py"):
        if ".venv" in py.parts or "__pycache__" in py.parts:
            continue
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in tree.body:  # module scope only — a local of the same name is harmless
            if not isinstance(node, ast.Assign):
                continue
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in owner:
                    if py.resolve() != owner[target.id]:
                        shadows.append(f"{target.id} declared in {py.relative_to(backend)}")

    assert not shadows, (
        "A swept constant is declared in a module the sweep does not rebind: "
        + "; ".join(shadows)
    )


# ─── the override mechanism ───────────────────────────────────────────────────────────


def test_override_rebinds_the_module_constant_and_restores_it():
    before = spatial_differ.CHANGED_SIMILARITY_FLOOR
    with sweep_override(DEFAULT_PARAMS.with_value("changed_similarity_floor", 0.9)):
        assert spatial_differ.CHANGED_SIMILARITY_FLOOR == 0.9
        assert current_params().changed_similarity_floor == 0.9
    assert spatial_differ.CHANGED_SIMILARITY_FLOOR == before


def test_override_restores_even_when_the_block_raises():
    """A leak here leaves the engine permanently retuned for the rest of the process, and every
    subsequent measurement in that run is quietly wrong."""
    before = current_params()
    with pytest.raises(RuntimeError):
        with sweep_override(DEFAULT_PARAMS.with_value("max_normalized_move", 9.0)):
            raise RuntimeError("sweep blew up mid-pair")
    assert current_params() == before


def test_current_params_reports_the_override_not_the_defaults():
    """A sweep that reported `DEFAULT_PARAMS` while running overrides would label every result
    with the wrong parameter set."""
    with sweep_override(DEFAULT_PARAMS.with_value("min_fuzzy_length", 9)):
        assert current_params().min_fuzzy_length == 9
        assert DEFAULT_PARAMS.min_fuzzy_length == 4  # frozen; unchanged


def test_unknown_parameter_is_rejected():
    with pytest.raises(KeyError):
        DEFAULT_PARAMS.with_value("nonexistent_knob", 1.0)


def test_params_are_frozen():
    with pytest.raises(Exception):
        DEFAULT_PARAMS.changed_similarity_floor = 0.9  # type: ignore[misc]


# ─── the zone tier is separated, deliberately ─────────────────────────────────────────


def test_zone_constants_are_excluded_from_the_matching_sweep():
    """Zone constants feed `safe_filter`, zone templates and `views_exclusions()`, and users
    have hand-pinned templates whose stored fractions moving `BBOX_PADDING` or `CLUSTER_RADIUS`
    can silently invalidate. The plan requires a separate pass with a 'pinned templates still
    resolve' assertion — this keeps them out of the easy one."""
    matching = set(DEFAULT_PARAMS.matching_params)
    assert not (matching & ZONE_PARAMS)
    assert ZONE_PARAMS <= {f.name for f in fields(ComparisonParams)}
    assert "bbox_padding" in ZONE_PARAMS and "cluster_radius" in ZONE_PARAMS
    assert "changed_similarity_floor" in matching


# ─── end to end: an override actually moves engine output ─────────────────────────────


@pytest.mark.asyncio
async def test_an_override_changes_what_the_engine_reports():
    """Proves the mechanism reaches the engine, not just the module global.

    Without this, `sweep_override` could rebind a name nothing reads and the sweep would report
    that every parameter is irrelevant — a very convincing wrong answer.
    """
    from services.backend.infrastructure.eval.corpus import (
        CorpusPayloadMissingError,
        default_fixtures_dir,
        load_corpus,
    )
    from services.backend.infrastructure.eval.runner import run_pair

    corpus = load_corpus(fixtures_dir=default_fixtures_dir())
    candidates = [p for p in corpus.pairs if p.provenance == "mutation"]
    if not candidates:
        pytest.skip("No mutation pairs registered.")
    try:
        candidates[0].load()
    except CorpusPayloadMissingError:
        pytest.skip("Corpus payloads are gitignored and not on this machine.")

    # Scanned rather than asserted on one pair. Many pairs legitimately do not exercise this
    # constant at all — a `translate_entities` probe has no edited text, so there is no CHANGED
    # pairing for a similarity floor to gate, and pinning the claim to whichever pair sorts
    # first makes the test fail for a reason unrelated to the mechanism.
    changed_somewhere = False
    inspected = 0
    for pair in candidates:
        inspected += 1
        baseline, _ = await run_pair(pair)
        # A floor of 1.0 admits only identical text as a CHANGED pairing.
        with sweep_override(DEFAULT_PARAMS.with_value("changed_similarity_floor", 1.0)):
            tightened, _ = await run_pair(pair)
        if [(p.status, p.new_text) for p in baseline] != [
            (p.status, p.new_text) for p in tightened
        ]:
            changed_somewhere = True
            break

    assert changed_somewhere, (
        f"Overriding changed_similarity_floor altered nothing across {inspected} pair(s). "
        f"Either the override reaches no code path the engine executes — which would make the "
        f"whole sweep report that every parameter is irrelevant — or the corpus contains no "
        f"pair with an edited-text finding."
    )
