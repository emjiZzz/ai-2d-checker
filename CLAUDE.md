# AI-2D-Checker — Agent Instructions

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

5. **Keep `docs/vault/00 - AI Maturity Status.md` current.** It is the single canonical answer to
   "which rung is this system on" (currently **0 — pre-RAG**: the default `rag` method has no
   retrieval and no LLM, the embeddings are SHA-256 noise, and no metric exists). Read it before
   touching the comparison engines, retrieval, the learned model or the AI pipeline. After landing
   anything: append a work-log entry, tick the stage board, rewrite "What's Next", and if a rung
   boundary was crossed update `current_rung` **and** `rung_evidence` together.
   **A rung claim with no evidence link is a defect** — this file previously advertised "the four V2
   gaps", a phrase the gap analysis had to record as having *no source in the vault*. Don't create a
   second phantom.
   Plan: `docs/vault/01 - Architecture/AI Maturity Ladder — Staged Plan.md`.
   Decisions: `docs/vault/07 - .../ADR-003 AI Maturity Ladder.md`.
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

Not caused by current work; do not chase them unless that is the task:
- `tests/test_vision_ocr_grounding.py` — 2 failures. **The cause changed on 2026-08-07**: they
  now fail with `orchestrator does not have the attribute 'execute_gemini_cascade'`, because
  ADR-006 deleted it. The older note here said `MockEntity` lacks a `layer` attribute; that is
  no longer the failure you will see. Verified against a clean tree.
- ~~`apps/desktop/src/pages/workspace/RoomsView.test.tsx`~~ — **fixed.** ADR-006's rewrite around
  the removed method picker retired the stale colour assertion. `npx vitest run` is **304/304** as
  of 2026-08-11 (the suite grows; this number is a floor, not a contract). `pytest` is 922 passed
  / 2 failed, those 2 being the `test_vision_ocr_grounding.py` pair above.

## Local environment

The backend runs on **port 8080**, not 8000 (`connectionStore.ts` defaults to
`http://127.0.0.1:8080`). The desktop dev server is on 1420. The local API bearer token is
generated and stored encrypted under `storage/secure/`; retrieve it with
`core.security.initialize_local_api_token()` rather than expecting it in `.env`.
