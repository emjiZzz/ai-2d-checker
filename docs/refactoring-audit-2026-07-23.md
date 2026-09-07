# Senior Codebase Audit — Refactoring Changeset (2026-07-23)

**Scope**: the currently uncommitted working-tree diff on branch `3D` (14 modified files) plus the untracked `REFACTORING_SUMMARY.md`, `services/backend/domain/services/drawing_ingestion_service.py`, `services/backend/infrastructure/ai/vectorstore/standards_indexer.py`, and `services/backend/infrastructure/audit/comparison/full_ai/` subpackage. This is the SRP/SOC modularization + bugfix pass described in `REFACTORING_SUMMARY.md`, not a whole-repo audit (that was descoped by request — see Executive Summary).

No files were modified as part of this audit; it is report-only.

**Remediation status (2026-07-23): all 7 findings RESOLVED.** See `docs/refactoring-audit-remediation-implementation-plan.md` for the phase-by-phase implementation log (Phases A–G). Summary:

| # | Status | Resolution |
|---|---|---|
| 1 | ✅ Resolved | `drawing_ingestion_service.py:104-113` — removed the invalid `id=f"dummy-..."` kwarg; regression test in `tests/test_drawing_ingestion_service.py`. |
| 2 | ✅ Resolved | `standards_loader.py:132-142` — wrapped `index_standard_chunks` in `asyncio.to_thread`; regression test in `tests/test_standards_loader_async.py`. |
| 3 | ✅ Resolved (test coverage) | 4 boundary tests added to `tests/test_hybrid_pipeline.py`; empirical-basis comment added above `MATCH_RADIUS_MM` in `reconciler.py`. Thresholds themselves unchanged (out of scope). |
| 4 | ✅ Resolved (test coverage) | 3 tests added in `apps/desktop/src/components/review/ChecklistPanel.test.tsx`. |
| 5 | ✅ Resolved (test coverage) | Smoke test added in `apps/desktop/src/pages/workspace/RoomsView.test.tsx`. |
| 6 | ✅ Resolved | Relocated to `docs/refactoring-summary-2026-07-23.md`. |
| 7 | ✅ Resolved | `drawings.py:36-46` — `upload_drawing` now wraps the service call in try/except with correlation-ID-wrapped 500 fallback; 2 tests in `tests/test_drawings_router_error_handling.py`. |

Full suite after remediation: **160 backend pytest cases passed**, **37 desktop vitest cases passed** (up from 152/33 at the time of the original audit).

---

## Executive Summary

The changeset does what it claims: it extracts a 1,039-line `full_ai_orchestrator.py` into a `full_ai/` subpackage (216 lines left in the facade), extracts upload handling out of `drawings.py` into `DrawingIngestionService`, offloads blocking I/O (file hashing, PDF parsing, report compiling) onto worker threads in `standards_loader.py` and `report_generator.py`, and lands several targeted bug fixes (camera fly-away guard, reconciler false-CONFLICT guard, naive-datetime deprecation). All 152 backend pytest cases and 33 desktop vitest cases pass.

However, the extraction introduced **one reproducible crash bug** and **one regression of the exact blocking-I/O problem this pass was meant to fix**, both undetected by the green test suite because neither has test coverage. Both are in code paths that only run on secondary/error branches (a stale-job duplicate-upload edge case, and standards ingestion's vector-indexing tail), which is exactly why they weren't caught by manual testing either — this is a textbook argument for adding regression tests before merging an extraction, not after.

---

## Architecture Overview

The backend is a FastAPI service (`services/backend`) using Beanie/MongoDB documents, with three architectural layers now visible in this diff: **API routers** (thin HTTP handlers), a new **domain/services** layer (`DrawingIngestionService`, business logic previously embedded in routers), and **infrastructure** (`audit/comparison/*` for the CAD comparison pipeline, `ai/vectorstore/*` for embeddings/LanceDB). The comparison pipeline runs two independent "generators" — a deterministic vector-extraction path and an AI Vision (Gemini) path — whose outputs are reconciled by `reconciler.py` into confirmed/disputed findings, with disputed findings resolved by `hybrid_orchestrator.py`'s `_resolve_disputed` (optionally consulting a third Gemini "crop verifier" call for genuinely ambiguous cases). The desktop app (`apps/desktop`, React) renders results on a canvas (`DrawingCanvas.tsx`) and lets the user jump to a violation location (`useCanvasInteraction.ts`), now with bounds-checking so bad coordinates can't fly the camera off-canvas.

The extraction pattern used throughout — pull a fat function/class into a smaller facade plus 2-4 focused modules, with the original file left as a thin orchestrating shell — is consistent and well-executed structurally (naming, docstrings referencing the design docs, no behavior described as changing). The weak point is that the extractions were done by hand without adding characterization tests for the newly-isolated modules first, so the refactor's correctness rests entirely on the pre-existing test suite's coverage, which — as shown below — has real gaps in exactly the areas touched.

---

## Dependency Map (new/touched modules only)

```
api/routers/drawings.py
  → domain/services/drawing_ingestion_service.py (NEW)
      → infrastructure/cad/processing_queue.py
      → domain/models/{drawing_document,extracted_entity,extraction_job}.py

infrastructure/audit/standards_loader.py
  → infrastructure/ai/vectorstore/standards_indexer.py (NEW)
      → infrastructure/ai/vectorstore/{embedding_provider,lancedb_manager}.py

infrastructure/audit/comparison/full_ai_orchestrator.py (216 lines, was 1039)
  → comparison/full_ai/prompt_builder.py (NEW)
  → comparison/full_ai/result_parser.py (NEW)
  → comparison/full_ai/persistence_handler.py (NEW)
  → comparison/{candidate,cache_manager}.py
  → comparison/gemini_client.py, revision_resolver.py (unchanged)

comparison/hybrid_orchestrator.py → comparison/{candidate,reconciler,crop_verifier}.py
comparison/reconciler.py → comparison/candidate.py (added `re` for text normalization)
comparison/candidate.py → adds ComparisonCandidate.from_canvas_marking() factory,
  now called from both full_ai_orchestrator.py and (implicitly) hybrid_orchestrator.py's candidate generation
```

No circular imports observed. `full_ai/` submodules are imported only by `full_ai_orchestrator.py`, keeping the new subpackage's blast radius contained.

---

## Findings

### Finding 1 — `ExtractionJob(id="dummy-...")` crashes with a Pydantic ValidationError (reproduced)

- **File**: [drawing_ingestion_service.py:104-111](services/backend/domain/services/drawing_ingestion_service.py#L104-L111)
- **Evidence**: When a drawing is re-uploaded whose hash matches an existing `status == "completed"` `DrawingDocument`, but no `ExtractionJob` document exists for it (e.g. jobs were pruned, migrated, or never created for legacy data), the fallback constructs `ExtractionJob(id=f"dummy-{existing_drawing.id}", ...)`. Beanie's `Document.id` is typed `PydanticObjectId`, which rejects non-ObjectId strings. Reproduced directly:
  ```
  ValidationError: Value error, Id must be of type PydanticObjectId
  ```
- **Root cause**: This code is new in the refactor. The pre-refactor version (see `git diff`) built a `JobResponse` **Pydantic schema** (plain `id: str`) for this fallback, not an actual `ExtractionJob` **Beanie Document**. The extraction silently changed the fallback from "construct a response DTO" to "construct a domain document," picking up the DTO's original `id=f"dummy-..."` value without noticing the target type's stricter validation.
- **Severity**: High. Not reachable on the common path (most completed drawings do have a job record), but it's a real crash on the specific re-upload-of-completed-but-orphaned-job path, and it throws an *unhandled* `ValidationError` — the router (`drawings.py`) has no try/except around `DrawingIngestionService.process_ingestion()`, so this surfaces as a raw 500 with a full stack trace and no correlation-ID-wrapped `HTTPException`, unlike every other error path in this router.
- **Business impact**: A user re-uploading a drawing whose extraction-job history was cleaned up (log retention, manual DB cleanup, or a future migration that only touches `extraction_jobs`) gets an opaque 500 instead of a duplicate-detected response — appears as a broken "upload" feature with no diagnostic info surfaced to support.
- **Recommended fix**: Don't construct a real `ExtractionJob` for this synthetic fallback — either (a) revert to returning a plain dict/DTO from `process_ingestion()` for this branch and adjust the router to handle a `job: ExtractionJob | dict`, or (b) simplest: drop the `id=` kwarg entirely and let Beanie assign a fresh ObjectId (the returned job is synthetic/display-only anyway, so its `id` value doesn't need to encode the drawing id).
  ```python
  existing_job = ExtractionJob(
      drawing_id=str(existing_drawing.id),
      status="completed",
      diagnostics={},
      created_at=existing_drawing.created_at,
  )  # let Beanie assign id
  ```
- **Migration strategy**: One-line fix, no schema/data migration needed. Add a regression test that deletes/omits the `ExtractionJob` for a completed drawing and re-uploads it (see Testing Gaps).
- **Risk of the fix**: Negligible — the `id` field was never read by callers of this synthetic object in the success path (the router only reads `job.status`, `job.diagnostics`, etc. into `JobResponse`).

### Finding 2 — Standards vector indexing reintroduces the event-loop-blocking pattern this same refactor pass fixed elsewhere

- **Files**: [standards_loader.py:157-163](services/backend/infrastructure/audit/standards_loader.py#L157-L163), [standards_indexer.py:14-21](services/backend/infrastructure/ai/vectorstore/standards_indexer.py#L14-L21)
- **Evidence**: `StandardsLoader.ingest_standard()` is an `async def` FastAPI-reachable method. Section 2 of `REFACTORING_SUMMARY.md` explicitly offloaded `calculate_file_hash`, `shutil.copy2`, and `StandardsParser.parse_file` in this exact function to `asyncio.to_thread(...)` "to prevent event loop stalls." Three lines later, the new call is:
  ```python
  from ..ai.vectorstore.standards_indexer import StandardsVectorIndexer
  StandardsVectorIndexer.index_standard_chunks(doc_id=..., standard_hash=..., name=name, chunks=chunks)
  ```
  `index_standard_chunks` is a plain (non-async) `@staticmethod` that calls `EmbeddingProvider.embed_texts()` (model inference, CPU/GPU-bound) and `LanceDBManager.write_embeddings()` (disk I/O) — called directly, not via `asyncio.to_thread`, and not awaited (it isn't a coroutine, so `await` wouldn't apply anyway).
- **Root cause**: The pre-refactor code had this same block inside a `try/except` directly in `ingest_standard`, also unoffloaded — so this isn't a new bug, but the refactor was billed as fixing "CPU-bound blocking I/O calls inside FastAPI async def handlers that previously stalled concurrent request processing" for this exact function, and this call was left out of that fix while sibling calls in the same function were addressed. It now reads as intentionally fixed when it isn't.
- **Severity**: Medium. Embedding a batch of standard-document chunks (potentially dozens to hundreds of chunks for a large PDF standard) will block the single-threaded async event loop for the duration of `embed_texts()` + `write_embeddings()`, stalling every other concurrent request (including unrelated drawing uploads, comparison polling, etc.) on the same worker process.
- **Business impact**: Intermittent latency spikes / apparent freezes for other users whenever someone uploads a new standards document — the exact class of bug this refactor pass says it eliminated, undermining the stated purpose of Section 2.
- **Recommended fix**:
  ```python
  await asyncio.to_thread(
      StandardsVectorIndexer.index_standard_chunks,
      doc_id=str(doc.id), standard_hash=standard_hash, name=name, chunks=chunks,
  )
  ```
  (`ingest_standard` already imports `asyncio` per this same diff.)
- **Migration strategy**: One-line change, no data migration. Since the original code already treated indexing failures as non-fatal (try/except swallowing errors), wrapping in `asyncio.to_thread` doesn't change error-handling semantics.
- **Risk of the fix**: Negligible — `asyncio.to_thread` requires only that the target function be side-effect-safe to run off the main thread, which it already must be to be safely called at all (LanceDB/embedding clients are typically used from thread pools elsewhere in this codebase, e.g. `execute_gemini_cascade` above).

### Finding 3 — Reconciler's new fuzzy cross-generator matching triples the match radius and adds a text-similarity bypass with no dedicated tests

- **File**: [reconciler.py:11-19, 96-118](services/backend/infrastructure/audit/comparison/reconciler.py#L11-L19)
- **Evidence**: `MATCH_RADIUS_MM` went from `5.0` to `35.0`, and a text-similarity path allows matching AI-vision candidates to deterministic candidates up to `65.0mm` apart (`max_allowed = 65.0 if is_text_match`), with `effective_dist = dist * 0.3` when text matches — a 7x radius increase over the original value, justified only by an inline comment change (no accompanying test in `test_hybrid_pipeline.py` was added for the new radius/text-bypass behavior, based on the diff — `tests/` changes weren't part of this file's diff).
- **Root cause**: Likely a legitimate empirical tuning (AI Vision coordinates are probably less spatially precise than deterministic vector coordinates, so tighter radius was causing false "disputed" splits for genuinely-the-same finding). But the change is a magic-number tuning with no test asserting the new threshold's boundary behavior, and no comment explaining *why* 35.0/65.0/0.3 were chosen over other values.
- **Severity**: Low-Medium. Not a bug per se, but a silent precision/recall tradeoff shift in production matching logic that's invisible to code review without domain knowledge, and has no regression test pinning the new behavior — a future "helpful" revert of the magic numbers would silently reintroduce the false-CONFLICT problem this was presumably fixing.
- **Business impact**: Risk of either false-merges (two genuinely-different nearby findings on a dense drawing collapsed into one) if too loose, or continued false-disputes if reverted — both directly affect audit accuracy, which is the product's core value proposition.
- **Recommended fix**: Add a test in `test_hybrid_pipeline.py` (or a new `test_reconciler.py`) asserting: two candidates 40mm apart with matching text are reconciled as confirmed; two candidates 40mm apart with different text and different category are not; a comment above `MATCH_RADIUS_MM` stating the empirical basis for 35.0/65.0/0.3 (e.g. "derived from observed AI Vision coordinate error on drawing set X").
- **Migration strategy**: N/A — test-only addition.
- **Risk of the fix**: None; adding tests is purely additive.

### Finding 4 — `ChecklistPanel.tsx` text-match heuristic changes matching semantics for short/symbolic strings without a test

- **File**: [ChecklistPanel.tsx:303-314](apps/desktop/src/components/review/ChecklistPanel.tsx#L303-L314)
- **Evidence**: The new `isMatch` helper special-cases strings of length ≤2 or matching `/^[-_./\\]+$/` to require exact equality instead of substring containment, to avoid short/symbolic tokens (e.g. `"-"`, `"C5"` truncated to `"C"`) spuriously substring-matching unrelated descriptions.
- **Root cause / assessment**: Reasonable defensive fix for a real false-positive-matching risk. No related test exists in the repo for `ChecklistPanel`'s matching logic (no `ChecklistPanel.test.tsx` was found in scope).
- **Severity**: Low (testing gap, not a bug).
- **Recommended fix**: Add a small unit test table exercising: two-char match, symbolic-token match, and the normal substring-containment case, to lock in the intended semantics.

### Finding 5 — `RoomsView.tsx` merge (per `REFACTORING_SUMMARY.md` §1) has no follow-up UI test

- **Evidence**: `REFACTORING_SUMMARY.md` §1 describes a manual merge combining two divergent commits' UI for `RoomsView.tsx` (form layout + 4-engine selector grid). No `RoomsView.test.tsx` exists in the repo (`Glob` for `RoomsView.test.*` returned nothing).
- **Severity**: Low-Medium — manual merges of UI logic are exactly where duplicate state, dropped handlers, or dead props tend to hide, and this one has zero automated coverage. This audit did not re-diff `RoomsView.tsx` against both parent commits to verify the merge's completeness (out of scope for the current uncommitted-changeset diff, since the merge was already committed as `27672e1` before this audit began), so no specific defect is claimed here — only the coverage gap.
- **Recommended fix**: A smoke test rendering `RoomsView` and asserting the 4 engine options (`RAG`, `RAG + AI`, `AI Vision`, `HYBRID`) render and are selectable would catch regressions in future merges/refactors of this file.

---

## Testing Gaps Summary

- No test covers the "completed drawing, missing `ExtractionJob`" duplicate-upload branch → would have caught Finding 1.
- No test asserts `ingest_standard()` doesn't block the event loop (e.g. a test that runs a slow embedding call concurrently with another request and asserts the second isn't stalled) → would have caught Finding 2. This is a harder test to write meaningfully; at minimum, a static/lint check that flags un-awaited-and-not-to-thread calls to known-blocking functions from `async def` would help.
- No test pins the new `MATCH_RADIUS_MM`/text-bypass boundary behavior in `reconciler.py` → Finding 3.
- No `ChecklistPanel` or `RoomsView` component tests exist at all, despite both having non-trivial logic touched in this changeset.
- The existing 152 backend / 33 desktop tests are real and passing, but they characterize the *pre-existing* surface area, not the newly-added/newly-changed branches in this diff — a common blind spot for "the tests are green" confidence after a refactor.

---

## Prioritized Backlog

1. **[Critical-effort:trivial]** Fix Finding 1 (`ExtractionJob(id="dummy-...")` crash) — one-line fix, add regression test.
2. **[High-effort:trivial]** Fix Finding 2 (unoffloaded `index_standard_chunks` call) — one-line fix.
3. **[Medium]** Wrap `drawings.py`'s call to `DrawingIngestionService.process_ingestion()` in the router with the same correlation-ID-wrapped exception handling used elsewhere in that file, so any future exception in the service layer degrades to a structured 500 instead of a raw traceback leak.
4. **[Medium]** Add reconciler boundary tests for the new match-radius/text-bypass logic (Finding 3).
5. **[Low-Medium]** Add `RoomsView.tsx` smoke test covering the 4-engine selector post-merge (Finding 5).
6. **[Low]** Add `ChecklistPanel` matching-heuristic unit tests (Finding 4).
7. **[Low, housekeeping]** `REFACTORING_SUMMARY.md` is currently untracked (`??` in git status) despite being described as "an authoritative reference for future AI agents and human contributors" — commit it or move it into `docs/` alongside the other implementation-plan docs, otherwise it'll be lost/gitignored accidentally.

---

## Regression Risks If This Diff Is Merged As-Is

- Finding 1 is a live crash bug on a real (if secondary) path — recommend fixing before merge, not after.
- Finding 2 is a latent performance regression, not a correctness bug — safe to merge but should be fixed promptly given it directly contradicts this same diff's stated goal.
- Findings 3-5 are coverage gaps, not known defects — safe to merge, but increase the cost of the *next* refactor touching these files.

## Testing Strategy Recommendation

Before merging: add the two regression tests for Findings 1 and 2 (both are cheap — one is a duplicate-upload fixture test, the other can at minimum assert `asyncio.to_thread` is used via a mock/patch on `StandardsVectorIndexer.index_standard_chunks`). Findings 3-5 can be tracked as fast-follow backlog items rather than merge blockers.

---

## Scorecard

| Dimension | Score (1-5) | Justification |
|---|---|---|
| Architecture | 4 | Clean layer separation (router → domain service → infrastructure) newly introduced; consistent extraction pattern; no circular imports. |
| Maintainability | 4 | Large files meaningfully shrunk (1039→216 lines); one inconsistency (Finding 2) undermines the stated goal in the same file it was applied to. |
| Security | 4 | No new injection/traversal/secrets issues found in this diff; existing sandboxed-path validation (`validate_sandboxed_path`) preserved. Not a full security review — scope was this diff only. |
| Performance | 3 | Net positive (offloaded 3 blocking calls) but one call still blocks the event loop (Finding 2), directly contradicting the stated intent. |
| Scalability | 3 | Unaffected by this diff either way at the architecture level; the event-loop-blocking issue is the main scalability-relevant item. |
| Documentation | 4 | `REFACTORING_SUMMARY.md` is unusually thorough and specific (file:line references, root causes) for a self-authored changelog, but is itself untracked in git. |

**Overall**: solid, well-intentioned refactor with good bones, held back by one reproducible crash bug and one performance regression that inverts this pass's own stated purpose — both cheap to fix, both currently untested.
