# AI-2D-Checker — Agent Instructions

> [!IMPORTANT] 🔴 Current priority, re-measured 2026-08-20 — **label. Next is `M7452A1N01`.**
>
> This is the next session's task. Read the **"🧭 What's next"** section of
> `docs/vault/00 - AI Maturity Status.md` for it in full — that file is the authority and this is
> only a pointer to it, deliberately. Do not act on the summary below without reading it; a
> restatement that drifts from the ledger is the phantom constraint 5 exists to prevent.
>
> ⚠ **Measure the count, do not quote it — this block has already carried a stale one.**
> `tools/eval_corpus.py status` at **2026-08-20** reports **5 / 8 labelled, 8 / 8 registered, 1 of
> 3 held out**. `M745230A01` (21 findings) and `M745203N01` (16) landed after this block was first
> written — which is why its header named an already-labelled pair until 2026-08-20 — then
> `M745204N01` (5), the first pair labelled from an app Manual Check session via
> `tools/eval_corpus.py from-manual-check` rather than by hand. The queue is **`M7452A1N01`**, then
> `M7452A2N01`. The engine measurement below still stands as the figure over the first two pairs.
>
> ⚠ **Registration is no longer the binding constraint — held-out is.** 0b needs **3 held out** and
> has **1**, and no amount of labelling closes that: a held-out pair must be exported before any
> comparison has run on it.
>
> In one line: the corpus is measuring the engine — **R 0.60 templated / 0.65 detection-only**
> over the 20 findings in `M7452A0N01` + `M745227N01`, attribution 0.92. Being short of eight
> pairs is still the only thing keeping the system at rung 0. `current_rung` and `rung_evidence`
> are unchanged and must stay that way until there are eight.
>
> ⚠ **Recall fell 0.75 → 0.60 when the second pair landed, with no engine change.** At this corpus
> size the number describes *which sheets are labelled*, not the engine. Do not treat movement here
> as a regression unless the mutation invariant moves with it.
>
> 🔴 **The corpus is now returning false negatives, which is what it exists for.** Largest: **added
> notes go entirely unreported** — a revision adding three instructions to a reference with no notes
> block at all produced zero findings (`notes_section` recall 0.25). Then an **added DIMENSION**
> unreported, then the **isometric view missed on both pairs** (zero text/dimension in the `iso`
> box, so unreachable by tuning). See the ledger before touching any of these.
>
> ⚠ **The queue is `M7452A1N01` → `M7452A2N01`.** `M745230A01` is labelled (21 findings). Do not
> re-litigate the ordering.
>
> ⚠ **This block recorded `M745203N01` as parked** until a 1.361-aspect template is hand-aligned
> (owner's call, 2026-08-10), *"so Stage 0b tops out at 5 / 8 until that changes"*. At 2026-08-20
> `tools/eval_corpus.py status` reports it **labelled, 16 findings**. Measurement over restatement:
> the park either lifted or was labelled through, and **this file is not the place that would
> record which** — check the ledger's work log before relying on either reading.
>
> ✅ **The corpus has now closed its first defect, not just found one.** A fabricated title-block
> field (`ME17227N24`, present on neither drawing) was published and diffed into a finding;
> `resolve_field` trusted an OCR string in the one case where nothing corroborated it. **Fixed,
> cache v49 → v50** — [[Gotcha - A Fixed OCR Misread Came Back Through the Title Zone]], which is
> also worth reading for *how* it was found: the obvious cause was measured and refuted first.
>
> ⚠ **Two defects found while labelling remain open**, both in `06 - Gotchas`: the `aspect-1.414`
> template has **no `shim` zone** (so the シム表 is compared, against the guideline), and
> `eval_corpus.py worksheet` **cannot place a DIMENSION** (reads `insert`, dimensions carry
> `def_point`), displaying a comparable entity with the two marks the guideline treats as *ignore*.
>
> ✅ **`pytest` is green again — 1180 passed, 3 skipped, 0 failed (2026-08-17).** The 5 failures
> this block previously called "pre-existing" were **not**: `git log -L` puts all five in
> `9336601`, one commit old, and the test catching one of them predates it. Two regressions, both
> fixed — `trainer.VERDICT_ZERO` had swallowed the two `mispaired_*` verbs in contradiction of the
> `MATCHER_FEEDBACK` block 16 lines below it (32 rows into the suppression class; inert only
> because `MIN_MINORITY_SHARE` abstained), and `review_violation`'s new feedback bridge re-opened
> a swallow a test already pinned. See
> [[Gotcha - A Verdict Mapping That Contradicted Its Own Comment]].
> ⚠ **The lesson is about this block, not the bug**: an inherited "pre-existing" label is a claim,
> and it went unchecked for the one commit in which it was false. Verify before inheriting it.
>
> ⚠ **A full `tools/eval.py` run no longer reproduces the committed baselines, and that is the
> corpus growing, not a regression.** Use `--provenance mutation` for the invariant.
>
> ⚠ **Re-measured 2026-08-20: it no longer reproduces `baseline-v48.json` either.** That run now
> reports **P 0.96 / R 0.8727 / F1 0.9143** (tp 48, fp 2, fn 7, duplicates 1) against the
> committed v48's P 0.9796 / F1 0.9231 — the engine has moved v48 → v53. Recall is unchanged.
> Verified as pre-existing by running it with and without that day's scorer change: byte-identical
> counts, so the drift is the engine's, not the harness's.
>
> ⚠ **`--baseline <path>` WRITES that file, it does not compare against it.** Passing the
> committed fixture overwrites it. Use `--json <scratch>` to inspect a run.
>
> 🔴 **`line_attribute_differ` got its first measurement from that pair and it is negative** — it
> produced 2 of the 4 templated false positives (`CONTINUOUS 1mm x1`, `CENTER 0.5mm x1` reported
> ADDED, because a revision is a re-trace). Its own work-log entry said the eval could not measure
> it; a human pair is what broke that blind spot. Unresolved — see the ledger.
>
> ✅ **`notes` / `iso` placement was raised, measured and closed on 2026-08-12 — do not reopen it
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
   ADR-007 definition, because `rung_evidence: none` and the corpus is short of eight
   human-labelled pairs — **5 of 8**, re-measured 2026-08-20 with `tools/eval_corpus.py status`.
   Re-run that command rather than quoting this line: it read "0 of 8" while four pairs were
   already labelled, which is the drift this very constraint warns about below. Rung 0 means
   *pre-measurement*, not "safely deterministic"; do not report it as a feature. Read the ledger
   before touching the comparison engines, retrieval, the learned model or the AI pipeline. After
   landing anything: append a work-log entry, tick the stage board, rewrite
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

The cull is swept across `storage/uploads` before landing. **That sweep now has a producer** —
until 2026-08-20 this paragraph quoted figures no command could reproduce, because `main()` took a
single DXF:

```bash
services/backend/.venv/Scripts/python.exe tools/render_audit.py --sweep storage/uploads
```

Re-measured 2026-08-25: **38 of 57 drawings cull nothing, 19 cull 1–8 entities, and the maximum
on any sheet is 8.** Re-run it if you touch the rule — it does not show up as a test failure.

⚠ **Only the maximum is an invariant; the other two are a census and move when the corpus does.**
`storage/uploads` was 55 drawings on 2026-08-20 and is 57 now, which is why the first two numbers
changed here without anything being wrong. The tool no longer compares them — it prints them as
context and gates on `MAX_CULL_PER_SHEET` alone. A sheet culling MORE than 8 means the
section-callout rule started eating geometry.

⚠ **The tool was pinned to figures this file had already retired.** `DOCUMENTED_CULL` held
`23 / 32 / 10` — corrected here on 2026-08-20, never corrected there — so every run printed three
`DIFFERS` lines against numbers no document claimed any more. A checker that cries wolf is how a
real jump gets waved through. Fixed 2026-08-25.

⚠ The figures before 2026-08-20 read **23 of 32 … maximum 10**, and the denominator alone showed
why they were quoted rather than measured. The sweep skips the text oracle, so it is fast enough
to actually run.

Address resolution has the same kind of harness, for the pipeline that turns a click into
ground truth. Run it after touching `address_resolver.py`, `manual_check_bridge.py` or
`useEntityPicking.ts`:

```bash
services/backend/.venv/Scripts/python.exe tools/address_audit.py
```

Healthy at 2026-08-20 over the 7 non-held-out human pairs: **97.2% correct, 0 wrong, 88
unresolved**, and a **3029 / 3029** round trip through `build_labels`. The WRONG column is the
one that matters and its expected value is **0** — a non-zero entry means the resolver handed
back an entity the engineer did not pick, with no error anywhere.

⚠ **Read it per row, not on the total.** The defect it was built for sat at `line` 19% while
`text` was at 100%, and the aggregate looked fine. ⚠ It probes with a **simulated click**
(segment midpoint, point on a curve), never the entity's own anchor — anchoring is the best case
and hides the entire defect class. Reverting `_entity_distance` must drop this to ~62% with 28
wrong; if it does not, the harness has stopped working.

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
with a `# vN:` note saying what a stale row is missing and how it degrades. Currently **7**.

**That gap is closed as of 2026-08-20** — this line read *"nothing reads it yet"* for weeks, and
it was accurate: the field was written, copied into an `EntityAddress` and named in a docstring,
but never queried.

```bash
services/backend/.venv/Scripts/python.exe tools/extraction_status.py
```

It groups every stored drawing by the version it was extracted at and prints what each stale one
is missing, parsing the `# vN:` notes **out of `extracted_entity.py` itself** rather than
restating them — a second copy would be correct until v8 and silently wrong after. Report only;
it never re-extracts.

**The cure now has a producer too** — until 2026-08-27 the only one was calling the route 38 times
by hand, which is done once, half-finished, and never repeated:

```bash
services/backend/.venv/Scripts/python.exe tools/reextract_stale_drawings.py --apply
```

It drives `POST /drawings/{id}/reextract` **one drawing at a time** (the route answers 409 while an
extraction is running, and `ExtractionPipeline.run` replaces entities), reports only without
`--apply`, and **reuses `extraction_status.collect`** rather than restating the staleness rule —
two copies of "which rows are behind" would disagree silently, one tool reporting clean while the
other re-extracts nothing. Needs the backend up; a row whose source file is gone answers 422 and is
skipped rather than failing the run. **Re-run it after every `EXTRACTION_SCHEMA_VERSION` bump**,
since a bump is the act that makes rows stale.

⚠ Re-measured 2026-08-25 it read **38 of 65 stale, 20 of them at v2** — five versions behind, with
dimension text anchors, leader hooklines, arrowheads and angular-dimension degrees all absent. They
had been rendering wrong for weeks. **Cleared 2026-08-27: 36 re-extracted, 0 failed, 63 of 65 now
current.** Measure rather than quoting this — the estate moves.

⚠ **The floor is 2, not 0, and it is permanent.** `MD511367B01_WABC-new.pdf` and
`MD51167B01_WABC-old.pdf` are `DrawingDocument` rows whose stored source file no longer exists, so
`/reextract` answers 422 and no tool can bring them current. They are also **PDFs, not DXF** —
legacy rows from before the vector path. A run reporting `skipped 2 (source file gone)` is healthy;
treat a *rising* skip count as the signal, not a non-zero one.

🔴 **Why this stopped being a background annoyance:** the only warning in the app,
`StaleExtractionBadge`, was mounted solely in `TwoDRightPanel`, which renders only once
`isPhysicalComparisonEnabled` is set — and that is written in exactly one place, after the
comparison engine runs. Prototype mode forces every room to `manual_check`, so the engine never
runs and **the badge was structurally unreachable in the build used to collect ground truth**. It
is now also mounted in `ManualMarkingList`. See
[[Gotcha - The Prototype Build Was Prototype By Accident]] §6.

⚠ **"Stored drawings" is not "files in `storage/uploads`", and this line used to mix them.** It
read *36 of 55*, where 55 was the upload FILE count of the day — `extraction_status.py` counts
`DrawingDocument` rows, which is 65. Two different denominators for two different questions: the
sweep above asks about files on disk, this asks about rows in the database.

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

**None. Both suites are green as of 2026-08-25 — treat any failure you see as yours.**
One `xfail`, named and scoped, is recorded below.

That sentence is the point of this section now, so keep it accurate: a standing allowlist is a
place for new breakage to hide, which is exactly what happened below.

⚠ **It was false between `f89cf0d` and 2026-08-25, and the failures were nine days old, not
inherited.** `pytest` reported **13 failed**, all traceable by `git log -L` to that one commit, and
this line told the next agent to take the blame for them. Verified as *not* the current session's
by running them with the working tree's only touched module made unimportable (same failures) and
again at clean `HEAD` in a throwaway worktree (same failures). **Do that before believing this
line in either direction** — the section's whole argument is that a claim about test state is a
claim, not a fact.

The thirteen, and what each turned out to be:

- **10 × `tests/test_ground_truth_submission.py`** — the tests patched `ManualCheckSession.find_one`
  while `_resume` had moved to `find(...).sort(...).to_list()` in `3b90d1e`. **A patch on a method
  nobody calls does not fail loudly**: the real `find` was reached, beanie was never initialised,
  and they died at `CollectionWasNotInitialized`. In the window before that surfaced the resume was
  effectively unguarded, and `f89cf0d` changed its behaviour underneath it — `_require_open` went
  from refusing a submitted session with 409 to silently reopening it. Fixed by patching `find`,
  and by making the reopen RECORD itself (`reopened_at`, `reopen_count` on `ManualCheckSession`
  and on `SessionResponse`), which is what makes a soft submit acceptable: `submit` is the moment a
  pass becomes what `from-manual-check` converts, and an amendment nobody can see is a corpus label
  whose source silently changed. Owner's call 2026-08-25.
  ⚠ `_require_open` also used Beanie **class-attribute expressions** (`Model.field == value`), which
  resolve through descriptors that only exist after `init_beanie` — so a mocked router test cannot
  construct them (`AttributeError: room_id`) and that branch had no coverage at all. It and
  `_resume` now share `_pair_query`, a raw mapping. The comment explaining exactly this was in the
  file until `3b90d1e` deleted it along with the protection.
- **`tests/test_phase2_infrastructure.py::test_database_retry_handling`** — environment-dependent.
  It pointed `MONGO_URI` at a dead port, but `connect()` falls back to `MONGO_FALLBACK_URI`
  (default `mongodb://127.0.0.1:27017`), so on a machine running `mongod` the connection succeeded
  and the test asserted it had failed. Both URIs are now dead ports, and the counters are asserted
  as `max_retries × candidates` — they accumulate across candidates rather than resetting.
- **`tests/test_database_failover_and_sync.py::test_database_sync_manager_status_and_execution`** —
  🔴 **it ran a real `sync_manager.sync_all()` on every `pytest`**, upserting into the cloud
  database as a side effect of running the suite. Split: the diagnostics contract still runs, the
  live sync is now behind `RUN_LIVE_DB_SYNC=1`. It was failing on genuine data — the live
  collections hold more than one `in_progress` session per (room, ref, rev, annotator), which the
  partial unique index refuses (`E11000`). `tools/merge_duplicate_check_sessions.py` is the cure and
  has to be run against **every** environment including Atlas.
  ⚠ **This is also why the suite took 11 minutes.** Without the live sync it is **~2 minutes**.
- **`tests/test_eval_corpus.py::test_committed_corpus_has_every_ocr_reading_captured`** — the only
  one still open, and **`xfail(strict=True)`** rather than fixed. `M745204N01` has no captured
  title-block reading and none is recoverable from `storage/cache/` by id or by file hash; making
  one is a **live Gemini call per side**, so it is an owner's decision. Owner's call 2026-08-25:
  leave it, capture by hand later. 🔴 The exposure is real — an eval run over that pair breaks the
  "zero network calls" criterion. `strict=True` so the suite fails the day it starts passing, and
  `test_no_pair_beyond_the_known_one_is_missing_its_ocr_reading` keeps the other pairs guarded,
  because **an `xfail` on a test that checks every pair excuses every pair.**

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
- `pytest` — **1478 passed, 4 skipped, 1 xfailed, 0 failed** (measured 2026-08-25, with
  `--ignore=tests/test_phase4_audit_pipeline.py`). The skips are the deliberate rung gates in
  `tests/test_maturity_ledger.py` plus the opt-in live cloud sync; the xfail is `M745204N01`'s
  OCR reading, above.
  ⚠ `tests/test_phase4_audit_pipeline.py` alone takes **~3 minutes** and its runtime swings
  between runs — it appears to make a real network call. Pre-existing (verified by timing it
  against a stashed working tree), and worth `--ignore`-ing for a fast inner loop.
  ⚠ **The rest of the suite is ~2 minutes, not 11.** It was 11 until 2026-08-25 because
  `test_database_sync_manager_status_and_execution` performed a real cloud sync on every run.
- `npx vitest run` — **684 passed across 63 files** (measured 2026-08-28; it read 653 across 56 on
  2026-08-27, 633 across 52 on 2026-08-25, and 408 across 35 before that). The four files added on
  2026-08-27 are prototype-mode coverage,
  which had **none at all** until 2026-08-27: vitest runs with `VITE_PROTOTYPE_MODE` unset, so
  every prior test exercised the non-prototype branch of all 8 gates and the configuration that
  actually ships to engineers was the untested one.
- `npx eslint .` (from `apps/desktop`) — **28 errors**, all `no-restricted-syntax` on direct
  `useWorkspaceStore.setState` calls. Standing backlog, not a gate; it was 30 until the two
  prototype-mode hydration sites were moved onto the `setHasHydrated` action that had been sitting
  in `createNavSlice` with no callers. ⚠ Five test files trip it unsuppressed — arranging store
  state is the fixture — so a *new* error here is worth reading, a non-zero total is not.
- `npx tsc --noEmit` — **0 errors** (now also gated in CI; it previously ran only over the shared
  types package, so `apps/desktop` was unenforced on merge).

## Local environment

The backend runs on **port 8080**, not 8000 (`connectionStore.DEFAULT_BACKEND_URL`). The desktop
dev server is on 1420. The local API bearer token is generated and stored encrypted under
`storage/secure/`; retrieve it with `core.security.initialize_local_api_token()` rather than
expecting it in `.env`.

### The backend is localhost-only, on purpose and in four places

Do not treat any one of these as the whole rule — changing one alone produces a build that fails
in a layer you are not looking at:

| Layer | What it enforces |
| :--- | :--- |
| `services/backend/start.ps1` | binds `--host 127.0.0.1` |
| `main.py` `ALLOWED_HOST_NAMES` | Host must be **exactly** `localhost` / `127.0.0.1` / `::1` |
| `main.py` CORS `allow_origins` | only `localhost:1420`, `tauri://localhost`, `http://tauri.localhost` |
| `src-tauri/tauri.conf.json` `connect-src` | what the webview may reach at all |

⚠ **The CSP layer fails differently from the other three, which is why it hid.** It is enforced by
the *webview*, so a blocked address never leaves the app: no network error, no backend log, nothing
in the network tab worth reading — just a UI stuck on "Connection Lost" against an address that
looks right.

⚠ **The port is not fixed and the CSP must not pin it.** `.env` documents `SIDECAR_PORT=0` for
dynamic allocation and `config.py` honours it, so the backend can answer on a port nothing knows at
build time; `tests/test_host_header_guard.py` already asserts the host guard passes a non-default
port. Until 2026-08-27 the CSP pinned `:8080` exactly — so the documented dynamic-port mode was
permanently unreachable, and the offline overlay's address field could not fix the mismatch it
exists for, because the corrected port was blocked by the same CSP. `connect-src` now allows any
port on the two loopback hosts. **The host axis was deliberately NOT widened**, and
`connectionStore.csp.test.ts` pins both halves — that the default is permitted, and that
non-loopback hosts still are not.

✅ **There IS a bundled backend now — this paragraph read "There is no sidecar" until 2026-08-28,
and had been false since `27fb0ab`.** The FastAPI backend is frozen with PyInstaller
(`tools/kmti_2dchecker_server.spec`), shipped as a Tauri **resource** rather than an
`externalBin`, and installed to `$INSTDIR\server\` with its own Python runtime; NSIS hooks
register a per-user logon Scheduled Task. `lib.rs::start_backend` also spawns it directly when the
task has not fired. Measured on an installed 0.1.8 build: `KMTI_2DChecker_Server.exe` running from
`%LOCALAPPDATA%\KMTI Checker\server\`, answering on 8080.

⚠ **NSIS only, so there is no working `.msi`.** `installerHooks` apply to NSIS alone — an `.msi`
would install the app and the server files and never register the task, which is an install that
looks fine and has no backend.

⚠ `tools/scripts/build-sidecar.ps1` is still the scaffold it always was: it announces *"Building
single-file Python executable with PyInstaller..."* and writes a **text file** containing
`"Scaffold mock executable binary"`, reporting success. It is not what packages the backend
(`package-server.ps1` is). Do not read its success as evidence of anything.

🔴 **An installed build's storage root is `%LOCALAPPDATA%\kmti-2d-checker`, and the search that
finds it used to escape to the drive root.** `security::find_storage_root()` (Rust) ascends six
parents from the working directory and from the executable looking for any directory named
`storage`. An app installed to `%LOCALAPPDATA%\KMTI Checker\` is five parents below `C:\`, so a
stray `C:\storage` — which the frozen backend creates if it is ever launched from `C:\` — was found
first, and the app read a token from it that the running backend had never issued. Every
authenticated request 401'd with *"Access Denied: Invalid security API Token"* while `/health`,
which needs no token, kept the app showing CONNECTED. Fixed 2026-08-28 by `looks_like_checkout()`:
a `storage` directory is this project's only with `pyproject.toml`, or `services/backend` **and**
`apps/desktop`, beside it. Guarded by `tests/test_storage_root_resolution.py` (parses the Rust,
because CI runs pytest and **not** `cargo test`) and by `cargo test --lib` in
`apps/desktop/src-tauri`. See
[[Gotcha - The Installed App Bound to a Storage Directory at the Drive Root]].

⚠ **A stale token decrypts perfectly.** The key is derived from machine and user, not provenance,
so there is no such thing as a token file that is obviously wrong — only one the backend rejects.
The frontend's 401 self-heal (`parseOrThrow` clears `apiToken`, `checkHealth` re-reads it) recovers
from a *rotated* token and cannot recover from the wrong *file*; it will re-read it every five
seconds indefinitely.

⚠ **Going centralized is not a config change either.** It means the four rows above *plus* the auth
model: the token is written to local disk by the backend and read off the local filesystem by
Tauri's `get_api_token`, so a remote client has no way to obtain one. And `storage/uploads` is not
in `sync_manager.SYNC_COLLECTIONS` while `drawing_documents` is — so drawing **metadata** syncs
across machines and the **files do not**. Every engineer would see every drawing row and be able to
open only the ones on their own disk. That failure is already visible at n=1: the two rows
`reextract_stale_drawings.py` reports as `source file gone`.
