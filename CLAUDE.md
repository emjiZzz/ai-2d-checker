# AI-2D-Checker — Agent Instructions

> [!IMPORTANT] 🔴 Current priority, set 2026-08-12 — **label. Start with `M7452A0N01`.**
>
> This is the next session's task. Read the **"🧭 What's next"** section of
> `docs/vault/00 - AI Maturity Status.md` for it in full — that file is the authority and this is
> only a pointer to it, deliberately. Do not act on the summary below without reading it; a
> restatement that drifts from the ledger is the phantom constraint 5 exists to prevent.
>
> In one line: **the zone-template blocker is cleared** — rows in no zone fell 9 → 1 and
> `baseline-v45.json` is metric-for-metric identical to v43, so the repair cost nothing measurable
> — and **nothing now stands between this project and its first human labels.** The corpus is
> still **0 of 8**, which is the only thing keeping the system at rung 0.
>
> ✅ **`notes` / `iso` placement was raised, measured and closed the same day — do not reopen it
> on the original reasoning.** The defect was a false detection anchor (`仕上げ` matching
> `仕上げ記号` in the tolerance block), not the pinning. *Unpinning* `notes` was measured and
> **rejected**: detection scores F1 0.87 against the pinned box's 0.92. See the ledger's ⛔
> Negative results for that and for why `ロール` is not the anchor to add.
>
> Delete this block when the priority changes, and move the new one here. If it is stale, the
> ledger wins.

## Read the vault before architectural work

`docs/vault/` is an Obsidian knowledge base and the canonical record of *why* this system is
built the way it is. It is not optional background — it contains defects and constraints that
are expensive to rediscover.

**Start here:**
- `docs/vault/00 - Map of Content (MOC).md` — index of everything
- `docs/vault/00 - AI Maturity Status.md` — **which rung the AI is actually on, what's done, what's
  next.** Read before AI/comparison work; update after. See constraint 5.
- `docs/vault/00 - AI Agent Navigation & System Gap Analysis.md` — current state, and the gap that
  matters most: **false negatives have never been measured**
- `docs/vault/07 - Architecture Decision Records (ADRs)/` — decisions already made; do not re-litigate
- `docs/vault/06 - Gotchas & Debugging Lessons/` — bugs already paid for once

This file exists because the vault previously had no inbound reference from the repo, so its
own "read this first" directive was unreachable. An agent rediscovered ADR-002's Gemini schema
defect from scratch as a result.

## Hard constraints

1. **Never add open-ended shapes to `PhysicalComparisonResponse` or anything nested in it.**
   `gemini_client.py` passes it directly as Gemini's `response_schema`. A bare `dict` field
   emits open-ended `additionalProperties`, which Gemini rejects with `400 INVALID_ARGUMENT`
   on *every* request, not just when populated. Use fixed fields.
   See `docs/vault/07 - .../ADR-002 Decoupled Zone Bounding Box Endpoint.md`.
   Guarded by `tests/test_zone_overlay_endpoint.py::test_llm_response_schema_has_no_open_ended_objects`.

2. **Bump `COMPARISON_CACHE_VERSION` (`cache_manager.py`) when spatial matching or zone
   extraction changes.** Cached audits live in `storage/cache/` and are served in ~0.14s,
   silently bypassing your fix. Add a one-line `# vN:` note saying what invalidates.
   See `docs/vault/06 - .../Gotcha - Comparison Cache Invalidation.md`.

3. **Zone geometry spans two coordinate spaces with opposite Y directions.** Detected boxes
   are CAD Y-up; `customRegions`/template fractions are Y-down. The only conversion lives in
   `apps/desktop/src/utils/zoneFractions.ts`. Getting it backwards produces a mirrored
   overlay that looks plausible.
   See `docs/vault/06 - .../Gotcha - Zone Detection Accuracy & Stability.md`.

4. **Document new gotchas in the vault** under `06 - Gotchas & Debugging Lessons/`, and link
   them from the MOC. Record negative results too — an idea that was measured and rejected is
   worth as much as one that worked, because otherwise it gets re-implemented.

5. **Keep `docs/vault/00 - AI Maturity Status.md` current, and read it rather than this summary.**
   It is the single canonical answer to "which rung is this system on" — currently **0**, under the
   ADR-007 definition, because `rung_evidence: none` and the corpus is **0 of 8 human-labelled
   pairs**. Rung 0 means *pre-measurement*, not "safely deterministic"; do not report it as a
   feature. Read the ledger before touching the comparison engines, retrieval, the learned model or
   the AI pipeline. After landing anything: append a work-log entry, tick the stage board, rewrite
   "What's Next", and if a rung boundary was crossed update `current_rung` **and** `rung_evidence`
   together.
   **A rung claim with no evidence link is a defect** — this file previously advertised "the four V2
   gaps", a phrase the gap analysis had to record as having *no source in the vault*. Don't create a
   second phantom.
   ⚠ **This clause was itself a phantom until 2026-08-11**, which is the point of the warning above.
   It read *"the default `rag` method has no retrieval and no LLM, the embeddings are SHA-256
   noise"*. Both halves were stale: `rag` was renamed to `deterministic` in `f87684a`, and the
   SHA-256 embeddings were **deleted** on 2026-08-07 by ADR-008's R0. `tests/test_maturity_ledger.py`
   only asserts the fake model is gone once `current_rung >= 1`, so nothing catches drift here at
   rung 0. Prefer the ledger over any restatement of it, including this one.
   Plan: `docs/vault/01 - Architecture/AI Maturity Ladder — Staged Plan.md`.
   Decisions: `docs/vault/07 - .../ADR-003 AI Maturity Ladder.md`, and
   `ADR-007 Re-scoping the Maturity Ladder.md` — which retired the old
   *Basic RAG → Fine-Tuned RAG → Trainable → Agentic* rung names. Do not cite those; they are
   ADR-003's, and ADR-007 replaced them.
   Guarded by `tests/test_maturity_ledger.py`.

## Design principles — SOLID and DRY, as this codebase has actually paid for them

These are **judgement, not hard constraints**: nothing mechanically enforces them, and
`architect-reviewer` is the only thing that reviews for them (CI's ruff/mypy gates are
`continue-on-error`). Every example below is a real defect or a real decision in this repo —
they are cited so the principle is checkable rather than quotable. If an example goes stale,
fix it or delete it; a principle illustrated by a lie is worse than one with no example.

### DRY — the failure mode here is *drift*, not typing

Duplication in this codebase does not announce itself by breaking. Two copies of one rule keep
working while they slowly disagree, and the output stays plausible. That is the expensive
shape, and it has landed four times:

- **`is_margin_grid_text` was implemented twice** and the copies drifted — only one normalised
  NFKC, so full-width grid labels were dropped in one path and kept in the other, where they
  bridged clusters across the sheet. `candidate_generator.is_in_margin` now delegates.
- **`sweep.py` and `runner.py` each reproduced the engine call** with no shared call site.
  `sweep.py` landed one day before the zone-template seam and never got it, so it measured
  **F1 0.68 against the eval's 0.92 on the same corpus at the same commit** — for four days.
- **`mutator.py` shares `apply_zone_overrides`** with the engine rather than re-deriving zones.
  A mutator applying *nearly* the engine's rules is the same defect one layer down.
- **`is_component_of_dwg_no` lives in `infrastructure/utils/text.py`** and is imported by
  `marking_builder` rather than restated, so the cards and the checklist table cannot disagree
  about what was dropped.

**Reach across a module boundary before you reimplement a rule.** `line_attribute_differ`
calls `GeometrySerializer._resolve_lineweight` — a private method in the *rendering* layer —
because the alternative is the checklist holding a second opinion about how thick a line is.
Crossing that boundary is the cheaper mistake.

⚠ **When you genuinely cannot share, pin the duplication with a test.** The taxonomy is
hand-mirrored in `taxonomy.py` and `comparisonTaxonomy.ts` because no runtime type-sharing
exists between the two languages; `tests/test_taxonomy_consistency.py` parses both and fails if
either side moves alone. `sectionCallouts.ts` deliberately mirrors `refine_view_labels` for the
same reason, and says so in its docstring. **Unpinned deliberate duplication is just
duplication.**

### SRP — one rule, one place, especially for rules enforced in several places

- **`zone_ownership.py` exists because zone precedence was being decided four ways** in four
  ad-hoc exclusion lists. It was reported violated from live reviews twice in one day. One
  arbitration now answers "which zone owns this entity", and the safe-zone net keyed on it is a
  **net, not a fix** — anything it drops is a bug upstream, and it logs each drop so that bug
  stays findable.
- **`params.py` collects all 20 tuning constants** out of six modules. The point is not tidiness:
  a sweep that compares runs against each other cannot attribute a change if a constant is
  declared where it is used.
- A function that both *decides* and *acts* cannot be measured. `extract_title_ul_kv` returning
  its claimed entity ids — instead of quietly subtracting them — is what made "only take content
  out of the shared pool if you will compare it" checkable.

### Open/Closed — extend at a declared seam, and make the seam earn itself

- **`retrieval/encoder.py` is a pluggable seam so a dense encoder must win a bake-off** against
  lexical rather than being assumed better.
- **`extract_dynamic_regions_async(zone_template=…)` has three states** — `None` resolves from
  Mongo (the app), `{}` asserts no pinned zones, `{...}` applies exactly those with no database
  access. It takes **fractions, not resolved boxes**, so an offline run still exercises the
  conversion whose failure mode is a plausible mirrored zone. A seam that bypasses the code
  under test is worse than no seam.
- ⛔ **Do not add a seam "for flexibility".** `apply_best()` on the sweep deliberately does not
  exist, pinned by a test: one click applying optima found on synthetic edits to a single sheet
  would undo what Stage 0 exists to establish.

### Liskov & Interface Segregation — where they actually bite here

- **Substitutability is about the sentinels, not the class hierarchy.** DXF `BYLAYER` (-1),
  `BYBLOCK` (-2) and `DEFAULT` (-3) are *instructions to look elsewhere*, not widths. Flattening
  them to a number is how every inheriting entity once rendered at 0.01mm. A subtype that
  silently answers a different question than its contract promises is the same bug in another
  costume — see `_dxf_get` (effective value) vs `_dxf_is_set` (did the file say it).
- **Interfaces here are schemas, and narrowing them is a hard constraint, not a preference.**
  Constraint 1 above: a bare `dict` field on anything nested in `PhysicalComparisonResponse`
  emits open-ended `additionalProperties` and Gemini rejects the request. Fixed fields, always.

### Dependency Inversion — depend on the seam, not on the environment

**`domain/` must not import `infrastructure/`, `api/`, or a web framework. This is now
enforced, not reviewed** — `tests/test_layer_boundaries.py` parses every module under `domain/`
with `ast`, resolves relative imports to their real targets, and fails on any outward edge. It
checks imports nested inside function bodies too, because two of the three original violations
were deferred imports that a module-header review does not see.

It became true on 2026-08-14, having been false for months in two places:

- **`domain/services/drawing_ingestion_service.py`** imported the processing queue, the storage
  path resolver, the comparison cache manager — and `fastapi`. Moved to
  `infrastructure/ingestion/`. ⚠ **The instructive part is why moving beat inverting**: ports
  for the three infrastructure imports would have made the grep clean while leaving a web
  framework in the domain layer, i.e. a fix that looks complete. A class taking `UploadFile` and
  raising `HTTPException` is an application service over infrastructure — its own docstring said
  so — and `infrastructure/audit/comparison/orchestrator.py` is the existing precedent for
  where a router-called orchestrator lives.
- **`domain/contracts.py`** re-exported seven `api/schemas.py` Pydantic models as "canonical
  domain data contracts" — the *schema leakage* `architect-reviewer` also flags. It had **zero
  importers**: dead code whose only live effect was the edge itself. Deleted.

Where the principle does hold elsewhere, it holds because someone needed to *test* the thing:

Where the principle does hold, it holds because someone needed to *test* the thing:

- The learned bundle resolves `LEARNED_MODEL_DIR` → repo path → deprecated vault, so an install
  that trained earlier keeps working and migrates itself on its next retrain — no script, no
  window where the model is missing.
- `runner.no_network()` patches `socket.connect` to raise on any non-local address, so "zero
  network calls" is **enforced rather than claimed**.
- Two of the three relocated Stage 0g tests were *environment-dependent*, not broken: they
  asserted against the real, gitignored vault, so they would have failed in CI for a reason
  unrelated to the code. Both now take an injected path.

**Prefer the version of a dependency you can assert against.**

> [!IMPORTANT] The rule that outranks all of the above.
> **A refactor must be proven inert before anything is attributed to it.** `params.py` was
> landed and measured byte-identical to the committed baseline *first*; the zone-template seam
> likewise. Land a structural change and a behavioural change together and neither is
> attributable — which in this repo means the measurement is worthless, and the measurement is
> the product.

## Where the deterministic comparison engine lives

Split on **2026-08-14**; before that it was one 2049-line `orchestrator.py` built around a
1334-line function with 21 nested closures. Measured byte-identical against
`tools/eval.py --baseline` at every step of the split — it bought testability, nothing else.

| File | Holds |
| :--- | :--- |
| `comparison/orchestrator.py` (252) | `perform_drawing_comparison` only — cache check, AuditSession/AuditViolation writes, post-cache learned pass. Plus the compatibility façade below. |
| `comparison/candidate_generator.py` (1542) | The engine: `generate_deterministic_candidates` and every helper that filters its candidates. |
| `comparison/title_matcher.py` (457) | Upper-left / bottom title-block key↔value pairing. |
| `bom/zone_geometry.py` | `is_in_bbox` moved here beside `point_in_shape`, so the comparison layer and `title_matcher` share one answer to "is this entity in this zone". |

Dependencies run one way: `zone_geometry → title_matcher → candidate_generator → orchestrator`.

⚠ **`orchestrator.py` re-exports the whole surface**, because it is the historical import site
for **10 test modules** plus `api/routers/audits.py` (`perform_drawing_comparison`),
`infrastructure/eval/{runner,sweep}.py` (`generate_deterministic_candidates`) and
`infrastructure/learning/inference.py` (`build_marking_table`). Import from it or from the real
module — both work. **Do not "clean up" those re-exports**; ruff flags them F401 and they carry
a per-line `# noqa` saying why.

⚠ **`perform_drawing_comparison` calls `generate_deterministic_candidates` by its bare
module-global name on purpose.** Python resolves that in `orchestrator`'s namespace at call
time, which is what lets `tests/test_comparison_architecture.py` intercept the engine with
`monkeypatch.setattr(orchestrator, "generate_deterministic_candidates", …)`. Writing it as
`candidate_generator.generate_deterministic_candidates(...)` silently bypasses that patch.

⚠ **A vault note or ADR citing `orchestrator.py:<line>` from before 2026-08-14 almost certainly
means `candidate_generator.py`.** Those line numbers were mostly stale already — ADR-003 cites
`orchestrator.py:290` for a function that had moved to 547 — so treat them as "somewhere in the
engine", not as coordinates. They are deliberately not rewritten: an ADR is a point-in-time
record.

⚠ **`MIN_STRUCTURED_VALUE_LENGTH` lives in `candidate_generator.py`, not `orchestrator.py`,**
because that is the module that *reads* it, and `params._BINDINGS` must name the reading module
or the sweep silently measures nothing. See
`docs/vault/06 - .../Gotcha - A Swept Constant Must Be Bound To The Module That Reads It.md`.
Guarded by `tests/test_comparison_params.py::test_the_bound_module_is_the_one_that_reads_the_constant`.

## Verified commands

Backend tests — run from the repo root. **No `PYTHONPATH` prefix is needed**; `pyproject.toml`
sets `pythonpath = ["."]`:

```bash
services/backend/.venv/Scripts/python.exe -m pytest tests/ -q
```

Frontend, from `apps/desktop`:

```bash
npx tsc --noEmit
```

```bash
npx vitest run
```

Vector render fidelity — from the repo root. Reports the canvas HUD's `drawn/total` and a
per-string placement delta against ezdxf's own rendering. Run it after touching
`renderEntities.ts`, `entity_mapper.py` or `geometry_serializer.py`:

```bash
services/backend/.venv/Scripts/python.exe tools/render_audit.py storage/uploads/0029fc8cdf974f5e92fa7148a679255d.dxf
```

On that drawing the census must stay at **490/518** (518 minus 6 `layer` + 12 `block` containers
minus 3 clipped model-space entities minus **7 section-callout entities** — nothing is missing at
that number), and the text oracle's `|dx|` max must stay near 1 drawing unit. It was 33.3 before
the placement fixes.

⚠ It read **497/518** until 2026-08-14, when the canvas stopped painting the section-view callout
— the `Ａ－Ａ` designation and lone `Ａ` labels, the cut-plane line, and the arrow ticks and label
tails on its ends (see `sectionCallouts.ts`). Those 7 are their own census bucket rather than a
smaller `drawn`, deliberately: folding a deliberate cull into the denominator's shortfall is how a
harness that exists to detect **missing geometry** stops being able to. If you add another cull,
give it a bucket and update this number with its breakdown.

The cull is swept across `storage/uploads` before landing: **23 of 32 drawings cull nothing, 9
cull 8–10 entities each, and the maximum on any sheet is 10.** Re-run that sweep if you touch the
rule — a jump in those numbers is the failure mode, and it does not show up as a test failure.

This harness is now the **only** way to tell whether a sheet's extraction is complete. There is no
raster fallback in the app to eyeball against — `renderMode` was deleted and the PNG display path
with it (`ADR-011 Vector as the Only Render Path`). The backend still generates the PNG, but only
as the source of `render_bounds` and as an input to title-block OCR and the PDF report; do not
reinstate it as a display source, and do not delete the generator — `render_bounds` is what every
zone template's fractions and identity are stored against.

⚠ `render_paths` (dimensions), `render_text_point` (dimension text anchors), leader hooklines,
MTEXT rotation and the elliptical-arc fix are computed at **extraction** time. A drawing ingested
before those will render wrong until it is re-extracted.

Since 2026-08-14 there is a re-extract route, so this is no longer "re-upload or live with it":

```bash
curl -X POST -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8080/api/v1/drawings/<id>/reextract
```

It re-parses from the stored file and keeps the drawing's id, room slot and audit history —
delete-and-re-upload loses all three. Returns the queued job; poll `GET /jobs/{id}`. Refuses with
409 while an extraction is already running and 422 if the source file is gone. Cached comparisons
for that drawing are cleared first, because a hit returns in ~0.14s and would otherwise bypass the
whole re-extraction.

`EXTRACTION_SCHEMA_VERSION` (`extracted_entity.py`) says which drawings need it: it is stamped
onto each `DrawingDocument` as `extraction_schema_version`, so a drawing predating a fix is
identifiable without re-reading its entities. **Bump it when you add an extraction-time field**,
with a `# vN:` note saying what a stale row is missing and how it degrades. Currently **6**.
Nothing reads it yet — that is a gap, not permission to leave it stale.

⚠ **`_dxf_get` tells you the effective value, `_dxf_is_set` tells you whether the file said it.**
ezdxf returns the DXF-spec default for an unset optional, so a LEADER that declares neither reads
back `has_hookline = 1` and `text_width = 1` — both truthy, neither written. Anything that
branches on *presence* must use `_dxf_is_set`; branching on the read value silently applies a
default the CAD never asked for.

⚠ `ExtractionPipeline.run` **replaces** a drawing's entities, deleting the previous set
immediately before its own insert. Keep that ordering: earlier, and a failed parse leaves the
drawing blank; absent, and a second run silently doubles every entity — which renders and compares
as a plausible drawing rather than as an error. Pinned by `tests/test_extraction_replacement.py`.

Note: PowerShell 5.1 is the default shell here and **does not support `&&`**. Use `;`, or run
the command in bash.

## Known pre-existing test failures

**None. Both suites are green as of 2026-08-11 — treat any failure you see as yours.**

That sentence is the point of this section now, so keep it accurate: a standing allowlist is a
place for new breakage to hide, which is exactly what happened below.

- ~~`tests/test_vision_ocr_grounding.py` — 2 failures~~ — **fixed 2026-08-11.** Both were
  documented here for months as pre-existing, and **the note recorded two different causes as if
  the older had been superseded. Both were real, stacked**: the tests patched
  `orchestrator.execute_gemini_cascade`, deleted by ADR-006, so they died at mock setup — and
  removing that obsolete patch revealed the *older* `MockEntity` lacks `layer` failure underneath,
  still live. Fixed by deleting the patch (the orchestrator makes no cascade call; the mocked
  call is gone from the design, so retargeting was wrong) and aligning `MockEntity` with
  `domain/models/extracted_entity.py`. Both tests also gained the assertion they were only ever
  making in a comment.
- ~~`apps/desktop/src/pages/workspace/RoomsView.test.tsx`~~ — **fixed.** ADR-006's rewrite around
  the removed method picker retired the stale colour assertion.

Current numbers, measured rather than quoted — **and the counts below are a floor, not a
contract; the suites grow.** (Until 2026-08-11 `pyproject.toml`'s `addopts` carried `-q`, so the
documented `pytest tests/ -q` resolved to `-qq` and printed **no totals line at all** — the one
command the docs recommended was the one that could not report a result. `-q` has been removed
from `addopts`; the command below now prints a count.)
- `pytest` — **994 passed, 3 skipped, 0 failed.** The 3 skips are deliberate rung gates in
  `tests/test_maturity_ledger.py`, not failures.
- `npx vitest run` — **333 passed across 30 files.**
- `npx tsc --noEmit` — **0 errors** (now also gated in CI; it previously ran only over the shared
  types package, so `apps/desktop` was unenforced on merge).

## Local environment

The backend runs on **port 8080**, not 8000 (`connectionStore.ts` defaults to
`http://127.0.0.1:8080`). The desktop dev server is on 1420. The local API bearer token is
generated and stored encrypted under `storage/secure/`; retrieve it with
`core.security.initialize_local_api_token()` rather than expecting it in `.env`.
