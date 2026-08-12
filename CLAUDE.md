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
> ⛔ **`notes` / `iso` placement is the agreed next item and must wait.** Both zones move between
> drawings and the template pins one position; measured, neither pinning nor detection wins
> consistently. Landing it mid-annotation changes what the engine scopes and means re-labelling.
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

On that drawing the census must stay at **497/518** (518 minus 6 `layer` + 12 `block` containers
minus 3 clipped model-space entities — nothing is missing at that number), and the text oracle's
`|dx|` max must stay near 1 drawing unit. It was 33.3 before the placement fixes.

This harness is now the **only** way to tell whether a sheet's extraction is complete. There is no
raster fallback in the app to eyeball against — `renderMode` was deleted and the PNG display path
with it (`ADR-011 Vector as the Only Render Path`). The backend still generates the PNG, but only
as the source of `render_bounds` and as an input to title-block OCR and the PDF report; do not
reinstate it as a display source, and do not delete the generator — `render_bounds` is what every
zone template's fractions and identity are stored against.

⚠ `render_paths` (dimensions), MTEXT rotation and the elliptical-arc fix are computed at
**extraction** time. A drawing ingested before those will render wrong, and there is no re-extract
endpoint — only `upload_drawing`.

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
- `pytest` — **987 passed, 3 skipped, 0 failed.** The 3 skips are deliberate rung gates in
  `tests/test_maturity_ledger.py`, not failures.
- `npx vitest run` — **333 passed across 30 files.**
- `npx tsc --noEmit` — **0 errors** (now also gated in CI; it previously ran only over the shared
  types package, so `apps/desktop` was unenforced on merge).

## Local environment

The backend runs on **port 8080**, not 8000 (`connectionStore.ts` defaults to
`http://127.0.0.1:8080`). The desktop dev server is on 1420. The local API bearer token is
generated and stored encrypted under `storage/secure/`; retrieve it with
`core.security.initialize_local_api_token()` rather than expecting it in `.env`.
