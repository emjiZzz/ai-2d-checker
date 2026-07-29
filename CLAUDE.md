# AI-2D-Checker — Agent Instructions

## Read the vault before architectural work

`docs/vault/` is an Obsidian knowledge base and the canonical record of *why* this system is
built the way it is. It is not optional background — it contains defects and constraints that
are expensive to rediscover.

**Start here:**
- `docs/vault/00 - Map of Content (MOC).md` — index of everything
- `docs/vault/00 - AI Agent Navigation & System Gap Analysis.md` — current state, the four V2 gaps
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

Note: PowerShell 5.1 is the default shell here and **does not support `&&`**. Use `;`, or run
the command in bash.

## Known pre-existing test failures

Not caused by current work; do not chase them unless that is the task:
- `tests/test_vision_ocr_grounding.py` — 2 failures, `MockEntity` lacks a `layer` attribute
- `apps/desktop/src/pages/workspace/RoomsView.test.tsx` — 1 failure, asserts a literal
  background colour that is now a CSS variable

## Local environment

The backend runs on **port 8080**, not 8000 (`connectionStore.ts` defaults to
`http://127.0.0.1:8080`). The desktop dev server is on 1420. The local API bearer token is
generated and stored encrypted under `storage/secure/`; retrieve it with
`core.security.initialize_local_api_token()` rather than expecting it in `.env`.
