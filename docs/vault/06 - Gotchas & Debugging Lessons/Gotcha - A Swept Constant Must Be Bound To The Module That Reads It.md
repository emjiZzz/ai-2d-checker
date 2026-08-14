---
tags: [gotcha, comparison, measurement, refactoring]
date: 2026-08-14
status: fixed-and-pinned
---

# Gotcha — A Swept Constant Must Be Bound To The Module That *Reads* It

`params.sweep_override()` retunes the engine by rebinding a **module global**. It only reaches
the engine if the module it rebinds is the module whose code actually performs the read.

That sounds tautological. It stops being tautological the moment anyone extracts a function
to a new module — because extraction carries the **read** out and leaves the **declaration**
behind.

## Why this cannot be caught by anything that was already there

`current_params()` reads back through the *same* `_BINDINGS` entry it writes through. So a
binding pointing at a module that merely declares the constant agrees with itself perfectly:

```python
# orchestrator.py  — declares it, no longer reads it
MIN_STRUCTURED_VALUE_LENGTH = DEFAULT_PARAMS.min_structured_value_length

# candidate_generator.py — reads its own copy, which the sweep never touches
```

- `sweep_override()` sets `orchestrator.MIN_STRUCTURED_VALUE_LENGTH` — nothing reads it.
- `current_params()` reads `orchestrator.MIN_STRUCTURED_VALUE_LENGTH` — reports the override.
- The engine reads the *other* copy and never moves.
- `test_modules_read_exactly_the_default_params` compares **values**, and both copies hold
  `3`, so it **passes**.

The sweep therefore reports "this parameter was swept across its range and F1 did not move."
That is a very convincing wrong answer, and it is indistinguishable from a real negative
result — which is the output this project exists to produce.

This is the same shape as the `sweep.py` / `runner.py` duplication: **F1 0.68 against the
eval's 0.92 on the same corpus at the same commit, for four days.** Two copies of one rule
disagreeing quietly while both keep working.

## Where it nearly landed

A refactoring plan proposed moving `generate_deterministic_candidates` (1334 lines) into a
new `candidate_generator.py`. `MIN_STRUCTURED_VALUE_LENGTH` is declared at
`orchestrator.py:35` and read in exactly one place — inside that function. The plan's own
risk register named the hazard and then mitigated it backwards, proposing that the new module
import `orchestrator` and read the attribute through it. That reverses the only edge its own
dependency DAG forbade, and works solely via a deferred in-function import — the same evasion
`tests/test_layer_boundaries.py` exists to catch.

## The rule

**Move the binding in the same commit as the reader.** A `_BINDINGS` entry names the module
that reads the constant, never the module that happens to declare it.

Corollary, for helpers promoted out of a closure: read the global **inside the body, on every
call**. Never as a default argument.

```python
def _collect_structured_text_values(*sources) -> set:
    min_structured_len = MIN_STRUCTURED_VALUE_LENGTH   # per call — sweepable
    ...

def _collect_structured_text_values(*sources, _min=MIN_STRUCTURED_VALUE_LENGTH) -> set:
    ...                                                # frozen at import — NOT sweepable
```

A default argument is evaluated once, at definition time, i.e. at import. `sweep_override`
rebinding the global afterwards has no effect, and the failure is silent in exactly the way
described above.

## Pinned by

`tests/test_comparison_params.py`:

- `test_the_bound_module_is_the_one_that_reads_the_constant` — parametrized over all 20
  bindings. AST-parses each bound module and requires both a `Store` and a `Load` of the
  attribute. It walks nested function bodies deliberately: the only read of
  `MIN_STRUCTURED_VALUE_LENGTH` was ~250 lines inside a 1334-line function, and a module-scope
  check would have missed it — and would have kept passing once that function moved out,
  which is the entire case the test exists for.
- `test_no_second_module_declares_a_bound_constant` — the other half. Two modules both
  assigning the name means the sweep rebinds one and the engine may read the other, and every
  value-equality assertion still passes because both hold the same literal.

Both were written and confirmed passing on the *unmodified* code first, then confirmed to
**fail** on a simulated defect (a binding pointed at a module that declares but never reads).
A guard that has never been seen to fail is not a guard — see the three verification commands
this plan originally shipped with, none of which could detect a regression.

## Where the code went (2026-08-14)

The split this note came out of, for anyone following an older reference:

| Was | Is now |
| :--- | :--- |
| `orchestrator.py` (2049 lines) | `orchestrator.py` (**252**) — `perform_drawing_comparison` only |
| `generate_deterministic_candidates` + its helpers | `candidate_generator.py` (1542) |
| the `_ul_*` / title-block pairing family | `title_matcher.py` (457) |
| `is_in_bbox` | `bom/zone_geometry.py`, beside `point_in_shape` |

`orchestrator.py` re-exports all of it — 10 test modules, `api/routers/audits.py`,
`eval/{runner,sweep}.py` and `learning/inference.py` import from the old site.

**Any note or ADR citing `orchestrator.py:<line>` from before this date means
`candidate_generator.py`.** Those line numbers were largely stale already (ADR-003 cites
`orchestrator.py:290` for a function that had moved to 547), so read them as "somewhere in the
engine". They are deliberately not rewritten — an ADR is a point-in-time record, and editing
one to match today's tree destroys the thing it exists to preserve.

## Related

- [[Gotcha - A Short Structured Value Suppresses Its Own Zone]] — what this constant is for.
- [[Gotcha - Comparison Cache Invalidation]] — the other way a fix gets silently bypassed.
- `CLAUDE.md`, "DRY — the failure mode here is *drift*, not typing".
- `CLAUDE.md`, "A refactor must be proven inert before anything is attributed to it."
