---
title: Gotcha - The Layer Rule Was Reviewed, Never Enforced
type: gotcha
tags: [gotcha, architecture, clean-architecture, domain-layer, dead-code, enforcement]
status: fixed
date: 2026-08-14
---

# 🔥 Gotcha — the layer rule was reviewed, never enforced

`.claude/agents/architect-reviewer.md` has listed two violations to flag since it was written:

> **Layer inversion** — `domain/` importing from `infrastructure/` …
> **Schema leakage** — Pydantic models in `api/schemas.py` used as internal domain objects

Both were live in the codebase, and had been for months. Nothing checked. CI's ruff and mypy
gates are `continue-on-error`, so the entire enforcement mechanism was *whether a reviewer
happened to look at the right file*.

---

## 🎯 The two violations

**1. `domain/services/drawing_ingestion_service.py`** imported
`infrastructure.cad.processing_queue`, `infrastructure.storage.path_resolver` and
`infrastructure.audit.comparison.cache_manager` — the last two as **deferred imports inside
method bodies**, where reading the module header does not reveal them. It also imported
`fastapi`.

**2. `domain/contracts.py`** re-exported seven Pydantic models from `api/schemas.py` under the
docstring *"Canonical domain data contracts"*. It had **zero importers anywhere in the repo.**
Dead code whose only live effect was the `domain -> api` edge it created. Deleted.

> [!NOTE] A dead file can still be a real violation.
> There was nothing to migrate and no behaviour to preserve — the cost was entirely structural,
> and it had survived precisely *because* nothing imported it. Nothing broke, so nothing
> complained. Check whether an offending module is even used before designing its replacement;
> this one took a `git rm`.

---

## ⛔ Why moving beat inverting — the fix that looks complete

The obvious fix for #1 is dependency inversion: declare Protocol ports in `domain/`, inject
infrastructure implementations at startup. **It would have been the wrong fix, and worse than
that, a convincing one.**

`DrawingIngestionService` takes a `fastapi.UploadFile` and raises `fastapi.HTTPException` with
HTTP status codes. Ports for the three infrastructure imports would make the
domain→infrastructure grep come back clean **while leaving a web framework imported in the
domain layer.** The rule would read as satisfied and the layer would still be wrong.

The class is an application service over infrastructure, and its own docstring always said so —
*"Decouples storage and CAD pipeline interactions from the HTTP API router layer"* is the
definition of one. So it moved to `infrastructure/ingestion/`, which also matches the existing
precedent: `infrastructure/audit/comparison/orchestrator.py` is the same shape of router-called
orchestrator and already lives there.

Direction is now `api/` → `infrastructure/` → `domain/` throughout. **Behaviour is unchanged** —
import paths only, across 4 source and 4 test sites — and the suite is identical at 1115 passed
either side of the move, which is the evidence that nothing was lost rather than a claim that
nothing was.

> [!IMPORTANT] The rule.
> **When a module violates a layer rule, ask whether it is in the wrong layer before you invert
> its dependencies.** Inversion is the right tool when domain logic genuinely needs an
> infrastructure capability. It is the wrong tool when the module was never domain logic — there
> it buys ceremony and hides the residue.

---

## ✅ Enforced now, and the checker is pinned too

`tests/test_layer_boundaries.py` parses every module under `domain/` with `ast` and fails on any
import resolving into `services.backend.infrastructure`, `services.backend.api`, or a web
framework.

Three things make it a real check rather than a decorative one:

- **It resolves relative imports.** The violations were written `from ...infrastructure.cad…`,
  which a substring search for `"infrastructure"` finds by accident and a naive absolute-import
  checker misses entirely. Level arithmetic is pinned by its own test — level 1 is the
  containing package, so from `domain/models/x.py` three dots is `services.backend`.
- **It walks nested imports** via `ast.walk`, catching the deferred in-method ones.
- **It asserts the domain package is non-empty**, because a checker that silently walks an empty
  tree passes forever.

⚠ **Beanie and Pydantic are deliberately NOT forbidden.** This codebase's domain models *are*
Beanie `Document` subclasses. That is a settled trade-off, not an oversight, and a checker that
banned it would fail on every file in `domain/models/` on day one.

**Verified non-vacuous the only way that counts:** a probe module importing
`...infrastructure.cad.processing_queue` was dropped into `domain/models/`, the test failed with
the right message, and the probe was removed.

---

## Guarded by

`tests/test_layer_boundaries.py` — 30 cases (one parametrized per `domain/` module, plus the
checker's own resolution tests and `test_the_deleted_contracts_shim_has_not_come_back`).

## 🔗 Related Notes
- See [[Gotcha - A Checklist Item With No Producer Reported Clean]] — the same shape one layer up: a rule that was documented, believed, and enforced by nothing
- See [[Gotcha - A Tested Endpoint That Nothing Ever Called]] — dead code that reads as coverage
- Return to [[00 - Map of Content (MOC)]]
