# Refactoring Audit Remediation — Implementation Plan

**Project:** ai-2d-checker
**Source:** `docs/refactoring-audit-2026-07-23.md` — audit of the in-flight SRP/SOC refactor described in `REFACTORING_SUMMARY.md`.
**Scope:** Fix the findings from that audit, in priority order. This is a remediation plan, not new feature work — every phase below maps to an existing finding, not new scope. Don't add anything not listed in a phase without updating this doc first.
**Constraint carried over from the audit:** do not change observable functionality beyond what each finding requires — these are bug fixes and test additions, not redesigns.
**Estimated effort:** ~0.5–1 dev day total. Phases A and B are each a one-line production fix plus a regression test (an hour or two each, most of it in the test). Phases C–E are small, additive test/hygiene work.

---

## 0. Audit findings this plan addresses

| # | Severity | Location | Finding |
|---|---|---|---|
| 1 | High | `domain/services/drawing_ingestion_service.py:104-111` | Re-uploading a `completed` drawing whose `ExtractionJob` record is missing constructs `ExtractionJob(id=f"dummy-{existing_drawing.id}", ...)`. Beanie's `id` field requires a real `PydanticObjectId`; this raises an unhandled `ValidationError` (reproduced), surfaced as a raw 500 with no correlation ID. |
| 2 | Medium | `infrastructure/audit/standards_loader.py:157-163`, `infrastructure/ai/vectorstore/standards_indexer.py:14-21` | `StandardsVectorIndexer.index_standard_chunks()` (embedding generation + LanceDB write) is called synchronously from inside `async def ingest_standard()`, blocking the event loop — the exact pattern this same refactor pass offloaded via `asyncio.to_thread` three lines earlier in the same function. |
| 3 | Low-Medium | `infrastructure/audit/comparison/reconciler.py:11-19, 96-118` | `MATCH_RADIUS_MM` widened 5.0→35.0mm, plus a new text-similarity bypass allowing matches up to 65.0mm with a `×0.3` distance discount — an untested magic-number tuning with no comment explaining the empirical basis. |
| 4 | Low | `apps/desktop/src/components/review/ChecklistPanel.tsx:303-314` | New `isMatch` helper changes matching semantics for short (≤2 char) and symbolic strings. No test locks in the intended behavior. |
| 5 | Low-Medium | `apps/desktop/src/pages/workspace/RoomsView.tsx` | Manually-merged UI (commit `27672e1`) has zero automated coverage — no defect found, but no regression net either. |
| 6 | Low (hygiene) | `REFACTORING_SUMMARY.md` (repo root) | Untracked (`??` in git status) despite being described as an authoritative reference doc — will be lost to `.gitignore`/cleanup if not committed or relocated. |
| 7 | Process | `api/routers/drawings.py::upload_drawing` | No try/except around `DrawingIngestionService.process_ingestion(file)` — any exception raised inside the service layer (including Finding 1, once fixed, and any future one) bypasses this router's otherwise-consistent correlation-ID-wrapped `HTTPException` pattern. |

Findings 1 and 7 are related (7 is what let 1 surface as a raw 500 instead of a structured error) but are separate phases: 1 fixes the specific crash, 7 hardens the router so *any* future service-layer exception degrades gracefully.

---

## 1. Build order

1. **Phase A — Fix Finding 1 (crash bug).** In `drawing_ingestion_service.py`, stop passing `id=` to the synthetic `ExtractionJob` constructed when a completed drawing has no matching job record; let Beanie assign a real ObjectId. Add a test that deletes/omits the `ExtractionJob` for a `completed` `DrawingDocument` and re-uploads the same file, asserting a `200` with `is_duplicate=True` instead of a `ValidationError`.
2. **Phase B — Fix Finding 2 (event-loop block).** In `standards_loader.py`, wrap the `StandardsVectorIndexer.index_standard_chunks(...)` call in `await asyncio.to_thread(...)` (module already imports `asyncio` per the current diff). Add a test that patches/mocks `StandardsVectorIndexer.index_standard_chunks` and asserts it's invoked via a thread-offload path (e.g. assert the call happens off the main event-loop thread, or at minimum assert `ingest_standard` doesn't block by mocking the indexer to sleep and confirming a concurrent coroutine still progresses).
3. **Phase C — Harden the router (Finding 7).** Wrap `DrawingIngestionService.process_ingestion(file)` in `drawings.py`'s `upload_drawing` with the same try/except + correlation-ID + `HTTPException(500, ...)` pattern already used elsewhere in that file, so this endpoint fails the same way its siblings do. Do this *after* Phase A so the phase isn't accidentally masking Finding 1's real bug during testing.
4. **Phase D — Reconciler regression tests (Finding 3).** Add boundary tests to `tests/test_hybrid_pipeline.py` (or a new `tests/test_reconciler.py`): two candidates 40mm apart with matching normalized text → confirmed match; two candidates 40mm apart with different text/category → not matched. Add a one-line comment above `MATCH_RADIUS_MM` recording the empirical basis for 35.0 / 65.0 / 0.3 (ask whoever tuned these values, or mark as "needs empirical justification" if unknown — don't invent a rationale).
5. **Phase E — Component test gaps (Findings 4, 5).**
   - `ChecklistPanel`: add a small test table exercising two-char exact-match, symbolic-token exact-match, and normal substring-containment cases for the `isMatch` helper.
   - `RoomsView`: add a smoke test rendering the component and asserting all 4 engine options (`RAG`, `RAG + AI`, `AI Vision`, `HYBRID`) render and are selectable.
6. **Phase F — Repo hygiene (Finding 6).** Move `REFACTORING_SUMMARY.md` into `docs/` (alongside the other `*-implementation-plan.md` / summary docs) or commit it at its current path — confirm with the user which location, then `git add` it in the same commit as the phase that touches it, so it isn't dropped.
7. **Phase G — Re-audit.** Re-run the full test suite (`pytest --ignore=services/backend/scratch` and `pnpm test`), confirm all new tests pass and the two production fixes (A, B) are present in the actual diff, and update `docs/refactoring-audit-2026-07-23.md`'s findings table to mark 1–7 as resolved with a one-line pointer to the commit/PR.

Phases are independent except: C should follow A (see above), and G depends on all prior phases. B, D, E, F have no ordering constraints relative to each other and can be done in parallel by different people/sessions.

---

## 2. Explicitly out of scope for this plan

- Re-tuning `MATCH_RADIUS_MM`'s actual values (35.0 / 65.0 / 0.3) — Phase D adds tests *pinning current behavior*, it does not judge whether the values themselves are correct. Changing them is a product/accuracy decision, not a bug fix.
- Auditing `RoomsView.tsx`'s merge (commit `27672e1`) against its two parent commits for dropped logic — the audit found no specific defect, only a coverage gap; Phase E's smoke test is a safety net for *future* changes, not a forensic re-review of the merge itself.
- Any change to `full_ai_orchestrator.py` / `full_ai/` subpackage structure, `drawing_ingestion_service.py`'s non-buggy logic, or any other file in the refactor not named in the findings table — this plan fixes what was found, not a second pass over the whole diff.
- A static-analysis rule for "un-awaited blocking calls in async def" (mentioned as an idea in the audit's Testing Gaps section) — worth doing, but it's tooling investment, not a fix for a specific finding; raise separately if wanted.

---

## 3. Testing strategy

- Phases A and B each ship a production fix + a test that would have caught the bug before the fix (regression-test-first is preferred: write the failing test against the current code, confirm it fails for the reason described in the finding, then apply the fix and confirm it passes).
- Phases D and E are test-only additions with no production code change — no regression risk.
- After all phases: full suite (`pytest --ignore=services/backend/scratch -p no:warnings` and `pnpm test` in `apps/desktop`) must stay green, and the new test count should increase by at least one test per phase A/B/D/E.

---

## 4. Completion log

*(Fill in as each phase lands — file(s) touched, commit/PR reference, one-line result.)*

- [x] Phase A — Removed `id=f"dummy-{existing_drawing.id}"` from the synthetic `ExtractionJob` in `drawing_ingestion_service.py:104-113` (Beanie now assigns a real ObjectId). Added `tests/test_drawing_ingestion_service.py`, verified it reproduces the original `ValidationError` against the pre-fix code and passes against the fix. Full suite: 153 passed (152 pre-existing + 1 new).
- [x] Phase B — Wrapped `StandardsVectorIndexer.index_standard_chunks(...)` in `await asyncio.to_thread(...)` in `standards_loader.py:132-142`. Added `tests/test_standards_loader_async.py`, which records which OS thread the call actually ran on; verified it fails against the pre-fix (unoffloaded) code with `4792 != 4792` (same thread) and passes against the fix. Full suite: 154 passed (153 + 1 new).
- [x] Phase C — Wrapped `DrawingIngestionService.process_ingestion(file)` in `drawings.py`'s `upload_drawing` (`drawings.py:36-46`) in a try/except: `HTTPException`s from the service pass through unchanged, anything else is logged with `exc_info=True` and re-raised as a correlation-ID-referencing `HTTPException(500)`, matching `audits.py`'s pattern. Added `tests/test_drawings_router_error_handling.py` (2 tests): one confirms an unexpected exception is now caught and returns a structured 500 without leaking the raw message (verified it fails against the pre-fix router with the raw `RuntimeError` escaping); the other confirms deliberate `HTTPException`s from the service still pass through unchanged. Full suite: 156 passed (154 + 2 new).
- [x] Phase D — Added 4 boundary tests to `tests/test_hybrid_pipeline.py` (`test_reconcile_matches_beyond_old_5mm_radius_without_text_similarity`, `test_reconcile_does_not_match_beyond_35mm_without_text_similarity`, `test_reconcile_matches_up_to_65mm_when_text_content_matches`, `test_reconcile_does_not_match_beyond_65mm_even_with_text_similarity`), pinning the current 35.0/65.0/0.3 thresholds. Verified 2 of the 4 fail against the pre-widening behavior (old 5.0mm radius, no text bypass). Added a comment above `MATCH_RADIUS_MM` in `reconciler.py` flagging the three magic numbers as needing empirical justification, not inventing a rationale. Full suite: 160 passed (156 + 4 new).
- [x] Phase E — Added `apps/desktop/src/components/review/ChecklistPanel.test.tsx` (3 tests: short-token exact-match guard, symbolic-token exact-match guard, normal substring-containment still works), verified 2 of 3 fail against the pre-fix substring-only `isMatch` logic. Added `apps/desktop/src/pages/workspace/RoomsView.test.tsx` (1 smoke test) confirming all 4 engine options (RAG/RAG+AI/AI Vision/HYBRID) render, default to "rag", and selection switches the active one. Full desktop suite: 37 passed (33 + 4 new). Backend suite unaffected: 160 passed.
- [x] Phase F — Moved `REFACTORING_SUMMARY.md` (repo root, untracked) to `docs/refactoring-summary-2026-07-23.md`, alongside the other implementation-plan/audit docs. Content unchanged.
- [x] Phase G — Re-ran full suites: backend 160 passed, desktop 37 passed. Verified all 7 findings closed against the actual current code (grepped for the specific fix markers, not just this log). Updated `docs/refactoring-audit-2026-07-23.md`'s findings table with a resolution-status summary pointing back to this plan. All phases complete.
