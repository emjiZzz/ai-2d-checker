# AI-2D-Checker — Agent Instructions

## Current priority

The task queue lives in the "What's next" section of `docs/vault/00 - AI Maturity Status.md`.
That file is the authority and this one deliberately does not restate it: a restatement here
drifts from the ledger, which is the failure constraint 5 exists to prevent.

Measure the corpus rather than quoting a figure from any document, including this one:

```bash
services/backend/.venv/Scripts/python.exe tools/eval_corpus.py status
```

## Read the vault before architectural work

`docs/vault/` is an Obsidian knowledge base and the canonical record of why this system is built
the way it is. It holds defects and constraints that are expensive to rediscover.

- `00 - Map of Content (MOC).md` — index of everything
- `00 - AI Maturity Status.md` — which rung the AI is on, what is done, what is next. Read before
  AI or comparison work; update after. See constraint 5.
- `00 - AI Agent Navigation & System Gap Analysis.md` — current state and the open gaps
- `07 - Architecture Decision Records (ADRs)/` — decisions already made; do not re-litigate
- `06 - Gotchas & Debugging Lessons/` — bugs already paid for once

This file exists because the vault had no inbound reference from the repo, so its own "read this
first" directive was unreachable and an agent rediscovered ADR-002's Gemini schema defect from
scratch.

## Hard constraints

1. **Never add open-ended shapes to `PhysicalComparisonResponse` or anything nested in it.**
   `gemini_client.py` passes it directly as Gemini's `response_schema`. A bare `dict` field emits
   open-ended `additionalProperties`, which Gemini rejects with `400 INVALID_ARGUMENT` on every
   request, not only when the field is populated. Use fixed fields.
   See `07 - .../ADR-002 Decoupled Zone Bounding Box Endpoint.md`. Guarded by
   `tests/test_zone_overlay_endpoint.py::test_llm_response_schema_has_no_open_ended_objects`.

2. **Bump `COMPARISON_CACHE_VERSION` (`cache_manager.py`) when spatial matching or zone extraction
   changes.** Cached audits in `storage/cache/` are served in ~0.14s and will silently bypass your
   fix. Add a one-line `# vN:` note saying what invalidates.
   See `06 - .../Gotcha - Comparison Cache Invalidation.md`.

3. **Zone geometry spans two coordinate spaces with opposite Y directions.** Detected boxes are CAD
   Y-up; `customRegions` and template fractions are Y-down. The only conversion lives in
   `apps/desktop/src/utils/zoneFractions.ts`. Reversing it produces a mirrored overlay that looks
   plausible. See `06 - .../Gotcha - Zone Detection Accuracy & Stability.md`.

4. **Document new gotchas in the vault** under `06 - Gotchas & Debugging Lessons/` and link them
   from the MOC. Record negative results too: an idea that was measured and rejected is worth as
   much as one that worked, because otherwise it gets reimplemented.

5. **Keep `docs/vault/00 - AI Maturity Status.md` current, and read it rather than any summary of
   it.** It is the canonical answer to which rung this system is on. Rung 0 means pre-measurement,
   not "safely deterministic"; do not report it as a feature. Read it before touching the
   comparison engines, retrieval, the learned model or the AI pipeline. After landing anything:
   append a work-log entry, tick the stage board, rewrite "What's next", and if a rung boundary was
   crossed update `current_rung` and `rung_evidence` together. A rung claim with no evidence link
   is a defect. Guarded by `tests/test_maturity_ledger.py`.
   Plan: `01 - Architecture/AI Maturity Ladder — Staged Plan.md`. Decisions: ADR-003 and ADR-007.
   ADR-007 retired ADR-003's rung names; do not cite those.

## Writing style

This file and the code around it are what every session imitates, so the style is
self-propagating. Keep it plain.

- Comments state the constraint in one or two sentences and name what enforces it.
- No emoji markers, no bold for emphasis, no markdown headings inside comments.
- No rhetorical framing. Write "this was measured", not "this is a measurement, not a preference".
- If an explanation needs more than about five lines, it belongs in a vault note or in a test name.
  Link the note; do not inline it.
- Prefer a test to a comment whenever the claim is checkable. A test fails when it stops being
  true; a comment rots silently. `tests/test_layer_boundaries.py` and
  `tests/test_taxonomy_consistency.py` are the pattern to copy.
- Commit messages: short imperative subject, body only where the diff does not speak for itself.

## Design principles

Judgement, not hard constraints. Nothing enforces these mechanically; `architect-reviewer` is the
only thing that reviews for them, and CI's ruff and mypy gates are `continue-on-error`. Every
example below is a real defect in this repo, so each is checkable. Fix or delete one that goes
stale.

### DRY — the failure mode here is drift, not typing

Two copies of one rule keep working while they slowly disagree, and the output stays plausible.
That has landed four times:

- `is_margin_grid_text` was implemented twice and only one copy normalised NFKC, so full-width grid
  labels were dropped in one path and kept in the other. `candidate_generator.is_in_margin` now
  delegates.
- `sweep.py` and `runner.py` each reproduced the engine call. `sweep.py` missed the zone-template
  seam by one day and measured F1 0.68 against the eval's 0.92, on the same corpus at the same
  commit, for four days.
- `mutator.py` shares `apply_zone_overrides` with the engine rather than re-deriving zones.
- `is_component_of_dwg_no` lives in `infrastructure/utils/text.py` and is imported by
  `marking_builder`, so the cards and the checklist table cannot disagree about what was dropped.

Reach across a module boundary before reimplementing a rule. `line_attribute_differ` calls
`GeometrySerializer._resolve_lineweight`, a private method in the rendering layer, because the
alternative is the checklist holding a second opinion about how thick a line is. Crossing that
boundary is the cheaper mistake.

When you genuinely cannot share, pin the duplication with a test. The taxonomy is hand-mirrored in
`taxonomy.py` and `comparisonTaxonomy.ts` because no runtime type-sharing exists across the two
languages; `tests/test_taxonomy_consistency.py` parses both and fails if either side moves alone.
`sectionCallouts.ts` mirrors `refine_view_labels` for the same reason and says so in its docstring.
Unpinned deliberate duplication is just duplication.

### SRP — one rule in one place, especially when enforced in several

`zone_ownership.py` exists because zone precedence was being decided four ways in four ad-hoc
exclusion lists, and was reported violated from live reviews twice in one day. One arbitration now
answers "which zone owns this entity". The safe-zone net keyed on it is a net, not a fix: anything
it drops is a bug upstream, and each drop is logged so that bug stays findable.

`params.py` collects all 20 tuning constants out of six modules. A sweep that compares runs against
each other cannot attribute a change to a constant declared where it is used.

A function that both decides and acts cannot be measured. `extract_title_ul_kv` returns its claimed
entity ids instead of quietly subtracting them, which is what made "only take content out of the
shared pool if you will compare it" checkable.

### Open/Closed — extend at a declared seam, and make the seam earn itself

`retrieval/encoder.py` is a pluggable seam so a dense encoder has to win a bake-off against lexical
rather than being assumed better.

`extract_dynamic_regions_async(zone_template=...)` has three states: `None` resolves from Mongo,
`{}` asserts no pinned zones, `{...}` applies exactly those with no database access. It takes
fractions, not resolved boxes, so an offline run still exercises the conversion whose failure mode
is a plausible mirrored zone. A seam that bypasses the code under test is worse than no seam.

Do not add a seam for flexibility. `apply_best()` on the sweep deliberately does not exist, pinned
by a test: one click applying optima found on synthetic edits to a single sheet would undo what
Stage 0 exists to establish.

### Liskov and Interface Segregation

Substitutability here is about sentinels, not the class hierarchy. DXF `BYLAYER` (-1), `BYBLOCK`
(-2) and `DEFAULT` (-3) are instructions to look elsewhere, not widths. Flattening them to a number
is how every inheriting entity once rendered at 0.01mm. A subtype that silently answers a different
question than its contract promises is the same bug in another costume; see `_dxf_get` (effective
value) against `_dxf_is_set` (did the file say it).

Interfaces here are schemas, and narrowing them is constraint 1, not a preference.

### Dependency Inversion — depend on the seam, not on the environment

`domain/` must not import `infrastructure/`, `api/`, or a web framework. This is enforced rather
than reviewed: `tests/test_layer_boundaries.py` parses every module under `domain/` with `ast`,
resolves relative imports to their real targets, and fails on any outward edge. It checks imports
nested inside function bodies, because two of the three original violations were deferred imports
that a module-header review does not see.

It became true on 2026-08-14, having been false for months in two places:

- `domain/services/drawing_ingestion_service.py` imported the processing queue, the storage path
  resolver, the comparison cache manager and `fastapi`. Moved to `infrastructure/ingestion/`.
  Moving beat inverting: ports for the three infrastructure imports would have made the grep clean
  while leaving a web framework in the domain layer, a fix that looks complete. A class taking
  `UploadFile` and raising `HTTPException` is an application service over infrastructure, and
  `infrastructure/audit/comparison/orchestrator.py` is the precedent for where a router-called
  orchestrator lives.
- `domain/contracts.py` re-exported seven `api/schemas.py` Pydantic models as "canonical domain
  data contracts" and had zero importers: dead code whose only live effect was the edge itself.
  Deleted.

Where the principle holds elsewhere, it holds because someone needed to test the thing. The learned
bundle resolves `LEARNED_MODEL_DIR`, then the repo path, then the deprecated vault, so an install
that trained earlier keeps working and migrates itself on its next retrain. `runner.no_network()`
patches `socket.connect` to raise on any non-local address, so "zero network calls" is enforced
rather than claimed. Prefer the version of a dependency you can assert against.

> The rule that outranks the rest: a refactor must be proven inert before anything is attributed to
> it. `params.py` was landed and measured byte-identical to the committed baseline first; the
> zone-template seam likewise. Land a structural change and a behavioural change together and
> neither is attributable, which in this repo means the measurement is worthless — and the
> measurement is the product.

## Where the deterministic comparison engine lives

Split on 2026-08-14 from one 2049-line `orchestrator.py` built around a 1334-line function with 21
nested closures. Measured byte-identical against `tools/eval.py --baseline` at every step of the
split; it bought testability and nothing else.

| File | Holds |
| :--- | :--- |
| `comparison/orchestrator.py` | `perform_drawing_comparison` only — cache check, AuditSession and AuditViolation writes, post-cache learned pass, plus the compatibility façade below. |
| `comparison/candidate_generator.py` | The engine: `generate_deterministic_candidates` and every helper that filters its candidates. |
| `comparison/title_matcher.py` | Upper-left and bottom title-block key-value pairing. |
| `bom/zone_geometry.py` | `is_in_bbox`, beside `point_in_shape`, so the comparison layer and `title_matcher` share one answer to "is this entity in this zone". |

Dependencies run one way: `zone_geometry -> title_matcher -> candidate_generator -> orchestrator`.

Three things that will bite:

- `orchestrator.py` re-exports the whole surface, because it is the historical import site for 10
  test modules plus `api/routers/audits.py`, `infrastructure/eval/{runner,sweep}.py` and
  `infrastructure/learning/inference.py`. Import from it or from the real module; both work. Do not
  clean up those re-exports — ruff flags them F401 and each carries a per-line `# noqa` saying why.
- `perform_drawing_comparison` calls `generate_deterministic_candidates` by its bare module-global
  name on purpose. Python resolves that in `orchestrator`'s namespace at call time, which is what
  lets `tests/test_comparison_architecture.py` intercept the engine with `monkeypatch.setattr`.
  Writing it as `candidate_generator.generate_deterministic_candidates(...)` bypasses that patch.
- `MIN_STRUCTURED_VALUE_LENGTH` lives in `candidate_generator.py`, not `orchestrator.py`, because
  `params._BINDINGS` must name the module that reads a constant or the sweep measures nothing.
  Guarded by
  `tests/test_comparison_params.py::test_the_bound_module_is_the_one_that_reads_the_constant`.

A vault note or ADR citing `orchestrator.py:<line>` from before 2026-08-14 almost certainly means
`candidate_generator.py`. Those line numbers were mostly stale already, so treat them as "somewhere
in the engine" rather than as coordinates. They are deliberately not rewritten: an ADR is a
point-in-time record.

## Verified commands

Backend tests, from the repo root. No `PYTHONPATH` prefix is needed; `pyproject.toml` sets
`pythonpath = ["."]`.

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

PowerShell 5.1 is the default shell here and does not support `&&`. Use `;`, or run the command in
bash.

### Render fidelity

Reports the canvas HUD's `drawn/total` and a per-string placement delta against ezdxf's own
rendering. Run after touching `renderEntities.ts`, `entity_mapper.py` or `geometry_serializer.py`.

```bash
services/backend/.venv/Scripts/python.exe tools/render_audit.py storage/uploads/0029fc8cdf974f5e92fa7148a679255d.dxf
```

On that drawing the census must stay at 490/518 — 518 minus 6 `layer` and 12 `block` containers,
minus 3 clipped model-space entities, minus 7 section-callout entities. The text oracle's `|dx|`
max must stay near 1 drawing unit; it was 33.3 before the placement fixes.

The section-callout entities are their own census bucket rather than a smaller `drawn`. Folding a
deliberate cull into the denominator's shortfall is how a harness that exists to detect missing
geometry stops being able to. If you add another cull, give it a bucket and update this number with
its breakdown.

Sweep the cull across `storage/uploads` before landing a change to the rule:

```bash
services/backend/.venv/Scripts/python.exe tools/render_audit.py --sweep storage/uploads
```

The invariant is `MAX_CULL_PER_SHEET`, currently 8: a sheet culling more than that means the
section-callout rule started eating geometry. The sweep also prints how many drawings cull nothing,
which is a census of the corpus rather than an invariant and moves when `storage/uploads` does.
The sweep skips the text oracle, so it is fast enough to actually run.

### Address resolution

The pipeline that turns a click into ground truth. Run after touching `address_resolver.py`,
`manual_check_bridge.py` or `useEntityPicking.ts`.

```bash
services/backend/.venv/Scripts/python.exe tools/address_audit.py
```

Read it per row, not on the total: the defect it was built for sat at `line` 19% while `text` was
at 100%, and the aggregate looked fine. The WRONG column is the one that matters and its expected
value is 0 — a non-zero entry means the resolver handed back an entity the engineer did not pick,
with no error anywhere. It probes with a simulated click (segment midpoint, point on a curve),
never the entity's own anchor, because anchoring is the best case and hides the entire defect
class.

This harness is the only way to tell whether a sheet's extraction is complete. There is no raster
fallback to eyeball against: `renderMode` was deleted along with the PNG display path (ADR-011).
The backend still generates the PNG as the source of `render_bounds` and as an input to
title-block OCR and the PDF report. Do not reinstate it as a display source, and do not delete the
generator — `render_bounds` is what every zone template's fractions and identity are stored
against.

### Extraction versions

`render_paths`, `render_text_point`, leader hooklines, MTEXT rotation and the elliptical-arc fix
are computed at extraction time. A drawing ingested before those renders wrong until it is
re-extracted.

```bash
curl -X POST -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8080/api/v1/drawings/<id>/reextract
```

Keeps the drawing's id, room slot and audit history; delete-and-re-upload loses all three. Returns
the queued job; poll `GET /jobs/{id}`. Refuses with 409 while an extraction is already running and
422 if the source file is gone. Cached comparisons for that drawing are cleared first, because a
hit returns in ~0.14s and would otherwise bypass the whole re-extraction.

`EXTRACTION_SCHEMA_VERSION` (`extracted_entity.py`, currently 7) is stamped onto each
`DrawingDocument` as `extraction_schema_version`, so a drawing predating a fix is identifiable
without re-reading its entities. Bump it when you add an extraction-time field, with a `# vN:` note
saying what a stale row is missing and how it degrades.

```bash
services/backend/.venv/Scripts/python.exe tools/extraction_status.py
```

Groups every stored drawing by the version it was extracted at and prints what each stale one is
missing, parsing the `# vN:` notes out of `extracted_entity.py` rather than restating them. Report
only; it never re-extracts.

```bash
services/backend/.venv/Scripts/python.exe tools/reextract_stale_drawings.py --apply
```

Drives the route one drawing at a time, because the route answers 409 while an extraction is
running. Reuses `extraction_status.collect` rather than restating the staleness rule. Reports only
without `--apply`, and needs the backend up. Re-run it after every `EXTRACTION_SCHEMA_VERSION`
bump, since a bump is the act that makes rows stale.

Two rows can never be brought current. `MD511367B01_WABC-new.pdf` and `MD51167B01_WABC-old.pdf` are
`DrawingDocument` rows whose stored source file no longer exists, so `/reextract` answers 422; they
are also PDFs, from before the vector path. A run reporting `skipped 2 (source file gone)` is
healthy — treat a rising skip count as the signal, not a non-zero one.

"Stored drawings" means `DrawingDocument` rows, which is not the same as files in
`storage/uploads`. The sweep above asks about files on disk; this asks about rows in the database.

### Two extraction foot-guns

`_dxf_get` returns the effective value, `_dxf_is_set` whether the file said it. ezdxf returns the
DXF-spec default for an unset optional, so a LEADER that declares neither reads back
`has_hookline = 1` and `text_width = 1` — both truthy, neither written. Anything that branches on
presence must use `_dxf_is_set`; branching on the read value silently applies a default the CAD
never asked for.

`ExtractionPipeline.run` replaces a drawing's entities, deleting the previous set immediately
before its own insert. Keep that ordering: earlier and a failed parse leaves the drawing blank;
absent and a second run doubles every entity, which renders and compares as a plausible drawing
rather than as an error. Pinned by `tests/test_extraction_replacement.py`.

### Eval

`--baseline <path>` writes that file, it does not compare against it: passing the committed fixture
overwrites it. Use `--json <scratch>` to inspect a run. For the invariant use
`--provenance mutation` — a full run no longer reproduces the committed baselines, because the
corpus grows.

## Test suite state

Both suites are green. Treat any failure you see as yours, and verify before inheriting a
"pre-existing" label from any document: that label was wrong once for nine days, with `git log -L`
placing all thirteen failures in a single commit.

One `xfail(strict=True)`: `M745204N01` has no captured title-block OCR reading and producing one
costs a live Gemini call per side. Owner's call, 2026-08-25 — capture by hand later. It is strict
so the suite fails the day it starts passing, and
`test_no_pair_beyond_the_known_one_is_missing_its_ocr_reading` keeps the other pairs guarded,
because an xfail on a test that checks every pair excuses every pair.

Suite counts are deliberately not recorded here. They move every week, a stale count reads as a
regression, and the commands above report the current ones. Two facts about the shape of a run do
not move: `tests/test_phase4_audit_pipeline.py` alone takes about 3 minutes and appears to make a
real network call, so it is worth `--ignore`-ing for a fast inner loop; and `npx eslint .` reports
a standing backlog of `no-restricted-syntax` errors on direct `useWorkspaceStore.setState` calls,
several of them in test files where arranging store state is the fixture. A new eslint error is
worth reading; a non-zero total is not.

## Deployment topologies

Three topologies (ADR-013):

1. **Local sidecar** bound to `127.0.0.1:8080`, or a dynamic port via `SIDECAR_PORT=0`, with a
   machine-bound encrypted bearer token in `storage/secure/`.
2. **On-premises LAN server** at a fixed host such as `192.168.200.105:8080`, configured via
   `ALLOWED_HOSTS` and a shared `API_TOKEN`.
3. **Cloud backend** on Render at `https://*.onrender.com`, fixed `API_TOKEN`, with the desktop
   client persisting the token in `localStorage` (`ai_2d_remote_api_token`).

### Host and network enforcement runs in four layers

| Layer | Enforces |
| :--- | :--- |
| `services/backend/config.py` | Binds `127.0.0.1` locally, `0.0.0.0` on cloud and containers |
| `main.py` `ALLOWED_HOST_NAMES` | Host must exactly match `ALLOWED_HOSTS` plus `RENDER_EXTERNAL_HOSTNAME` |
| `main.py` CORS `allow_origins` | `localhost:1420`, `tauri://localhost`, `http://tauri.localhost`, plus `CORS_ORIGINS` |
| `src-tauri/tauri.conf.json` `connect-src` | loopback on any port, `192.168.200.105:*`, `https://*.onrender.com` |

Changing one alone produces a build that fails in a layer you are not looking at. The CSP is the
one that hides: it is enforced by the webview, so a blocked address never leaves the app. No
network error, no backend log, nothing in the network tab — just a UI stuck on "Connection Lost"
against an address that looks right.

The port is not fixed on loopback. `.env` documents `SIDECAR_PORT=0` and `config.py` honours it, so
the backend can answer on a port nothing knows at build time; `connect-src` therefore allows any
port on loopback and on the LAN server. `tests/test_host_header_guard.py` asserts the backend's own
guard passes a non-default port, and `connectionStore.csp.test.ts` asserts non-allowlisted external
hosts are still rejected.

### Packaging

The FastAPI backend is frozen with PyInstaller (`tools/draftcheck_server.spec`) and shipped as a
Tauri resource, installed to `$INSTDIR\server\` with its own Python runtime. NSIS hooks register a
per-user logon Scheduled Task, and `lib.rs::start_backend` also spawns it directly when the task
has not fired.

NSIS only. `installerHooks` do not apply to an `.msi`, so an `.msi` would install the app and the
server files and never register the task — an install that looks fine and has no backend.

The app was renamed from KMTI Checker to DraftCheck on 2026-09-03, and every name moved with it:
`DraftCheck_Server.exe`, `%LOCALAPPDATA%\DraftCheck\`, the bundle identifier
`com.kmti.draftcheck`, the token directory `%LOCALAPPDATA%\draftcheck\`, and the Scheduled Task
"DraftCheck Backend". Windows treats the new identifier as a different application, so a machine
carrying a pre-rename install has an orphaned app directory, an orphaned token directory and a
still-registered "KMTI 2D Checker Backend" task pointing at an executable the new build does not
install. Uninstall the old build first: the new uninstaller looks up the task and the process by
their new names. "KMTI" elsewhere is the company — layer names, title blocks, the eval corpus, the
LAN box's own services — and did not move.

`tools/scripts/build-sidecar.ps1` is a scaffold. It announces a PyInstaller build and writes a text
file containing "Scaffold mock executable binary", reporting success. `package-server.ps1` is what
actually packages the backend. Do not read the scaffold's success as evidence of anything.

### Tokens

An installed build's storage root is `%LOCALAPPDATA%\draftcheck`.
`security::find_storage_root()` (Rust) ascends six parents from the working directory and from the
executable looking for a directory named `storage`, so a stray `C:\storage` was once found first
and the app read a token the running backend had never issued. Every authenticated request 401'd
while `/health`, which needs no token, kept the app showing CONNECTED. `looks_like_checkout()` now
requires `pyproject.toml`, or `services/backend` and `apps/desktop`, beside the `storage`
directory. Guarded by `tests/test_storage_root_resolution.py`, which parses the Rust because CI
runs pytest and not `cargo test`, and by `cargo test --lib` in `apps/desktop/src-tauri`.
See `06 - .../Gotcha - The Installed App Bound to a Storage Directory at the Drive Root.md`.

A stale token decrypts perfectly. The key is derived from machine and user, not provenance, so
there is no such thing as a token file that is obviously wrong — only one the backend rejects. The
frontend's 401 self-heal recovers from a rotated token and cannot recover from the wrong file; it
will re-read it every five seconds indefinitely.

Going centralized is not a config change. It means the four layers above plus the auth model: the
token is written to local disk by the backend and read off the local filesystem by Tauri's
`get_api_token`, so a remote client has no way to obtain one. And `storage/uploads` is not in
`sync_manager.SYNC_COLLECTIONS` while `drawing_documents` is, so drawing metadata syncs across
machines and the files do not. Every engineer would see every drawing row and be able to open only
the ones on their own disk. That failure is already visible at n=1: the two rows
`reextract_stale_drawings.py` reports as `source file gone`.
