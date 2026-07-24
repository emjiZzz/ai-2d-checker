# Project Refactoring & Architecture Summary (07-23-2026)

This document logs all architectural refactoring, Single Responsibility Principle (SRP) / Separation of Concerns (SOC) structural splits, async event loop unblocking fixes, UI merge conflict resolutions, and bug fixes completed across the **AI 2D Checker** repository. It serves as an authoritative reference for future AI agents and human contributors.

---

## 1. UI Merge Conflict Resolution & Feature Extension

- **Target File**: [RoomsView.tsx](file:///d:/RAYSAN/ai-2d-checker/apps/desktop/src/pages/workspace/RoomsView.tsx)
- **Summary**: Merged incoming commit `e8c1bd7` (light-theme modal forms & structured layout) with local commit `e8b758b` (hybrid comparison mode).
- **Key Changes**:
  - Combined form inputs for Room Name, Client, Standard, and Comparison Engine.
  - Expanded engine selector grid to 4 columns: `RAG`, `RAG + AI`, `AI Vision`, and `HYBRID`.

---

## 2. Event-Loop Safety & Sync I/O Offloading

- **Target Files**:
  - [standards_loader.py](file:///d:/RAYSAN/ai-2d-checker/services/backend/infrastructure/audit/standards_loader.py)
  - [report_generator.py](file:///d:/RAYSAN/ai-2d-checker/services/backend/infrastructure/audit/report_generator.py)
- **Summary**: Resolved CPU-bound blocking I/O calls inside FastAPI `async def` handlers that previously stalled concurrent request processing.
- **Key Changes**:
  - Offloaded file hashing (`calculate_file_hash`), PDF parsing (`StandardsParser.parse_file`), PDF export compiling (`PDFComplianceExporter.generate_pdf`), and Excel report compiling (`XLSXComplianceExporter.generate_xlsx`) to worker threads using `asyncio.to_thread(...)`.

---

## 3. SRP & SOC Backend Modularization (Phase 1)

### A. Vector Indexer Service

- **New File**: [standards_indexer.py](file:///d:/RAYSAN/ai-2d-checker/services/backend/infrastructure/ai/vectorstore/standards_indexer.py)
- **Summary**: Extracted LanceDB table writing and `EmbeddingProvider` vector generation out of `standards_loader.py` into a dedicated `StandardsVectorIndexer` class.

### B. Drawing Ingestion Service

- **New File**: [drawing_ingestion_service.py](file:///d:/RAYSAN/ai-2d-checker/services/backend/domain/services/drawing_ingestion_service.py)
- **Summary**: Extracted chunked upload file streaming, SHA-256 hash calculation, duplicate document detection, database persistence, and CAD processing queue dispatching out of the router.
- **Router Cleanup**: Refactored [drawings.py](file:///d:/RAYSAN/ai-2d-checker/services/backend/api/routers/drawings.py) handler from ~250 lines down to a concise 30-line HTTP endpoint delegating to `DrawingIngestionService`.

---

## 4. Full-AI Orchestrator Modularization (Phase 2)

- **Target File**: [full_ai_orchestrator.py](file:///d:/RAYSAN/ai-2d-checker/services/backend/infrastructure/audit/comparison/full_ai_orchestrator.py)
- **Summary**: Decomposed the repository's largest file (**1,039 lines / 56.9 KB**) into specialized sub-modules under `services/backend/infrastructure/audit/comparison/full_ai/`.

### New Subpackage: `services/backend/infrastructure/audit/comparison/full_ai/`

1. **[prompt_builder.py](file:///d:/RAYSAN/ai-2d-checker/services/backend/infrastructure/audit/comparison/full_ai/prompt_builder.py)**: System instruction generation and Gemini multimodal payload formatting.
2. **[result_parser.py](file:///d:/RAYSAN/ai-2d-checker/services/backend/infrastructure/audit/comparison/full_ai/result_parser.py)**: Gemini response JSON parsing, coordinate resolution, visual bbox fallbacks, and deterministic BOM/Title Block status overrides.
3. **[persistence_handler.py](file:///d:/RAYSAN/ai-2d-checker/services/backend/infrastructure/audit/comparison/full_ai/persistence_handler.py)**: MongoDB `AuditSession` creation, `AuditViolation` batch insertion, and disk cache writing via `ComparisonCacheManager`.

**Result**: Reduced `full_ai_orchestrator.py` from **1,039 lines to 216 lines (79% reduction)**.

---

## 5. Runtime Bug Fixes & Signature Tolerances

### A. Flexible `build_structured_context` Signature

- **Target File**: [context_builder.py](file:///d:/RAYSAN/ai-2d-checker/services/backend/infrastructure/audit/context_builder.py)
- **Issue**: Raised `AttributeError` when positional arguments were passed as `(drawing, entities)` instead of `(entities, drawing)`.
- **Fix**: Updated `build_structured_context` to dynamically detect `DrawingDocument` and `list` instances regardless of parameter order.

### B. Un-truncated Error Diagnostics

- **Target File**: [audits.py](file:///d:/RAYSAN/ai-2d-checker/services/backend/api/routers/audits.py)
- **Fix**: Added `exc_info=True` to `logger.error` inside `perform_physical_comparison` so any runtime error outputs full un-truncated stack traces to the log stream.

### C. Zustand Store Mocks in Desktop Unit Tests

- **Target File**: [DrawingCanvas.test.tsx](file:///d:/RAYSAN/ai-2d-checker/apps/desktop/src/components/review/DrawingCanvas.test.tsx)
- **Fix**: Added static `getState` and `subscribe` methods to `useReviewStore` and `useWorkspaceStore` Vitest mocks.

### D. Engineering Standard Symbol Upgrade Classification (`CHANGED`)

- **Target Files**: 
  - [crop_verifier.py](file:///d:/RAYSAN/ai-2d-checker/services/backend/infrastructure/audit/comparison/crop_verifier.py)
  - [reconciler.py](file:///d:/RAYSAN/ai-2d-checker/services/backend/infrastructure/audit/comparison/reconciler.py)
- **Rule & Logic**: Adding, removing, or updating engineering standard symbols (such as diameter `Ø`/`⌀`/`ø`, radius `R`, chamfer `C`, degree `°`, surface finish, or welding symbols) between reference (old standard) and revision (copy-traced new standard) drawings is **always classified as `CHANGED`** (orange badge), never `MATCHED` or `CONFLICT`.
- **System Instruction Update**: Instructed Gemini Crop Verifier to enforce `differs=True` and `status=CHANGED` for standard symbol additions.

### E. Shim Table (`シム表` / Shim Schedule) Exclusion Rule (Ignored / Out of Scope)

- **Target Files**:
  - [prompt_builder.py](file:///d:/RAYSAN/ai-2d-checker/services/backend/infrastructure/audit/comparison/full_ai/prompt_builder.py)
  - [crop_verifier.py](file:///d:/RAYSAN/ai-2d-checker/services/backend/infrastructure/audit/comparison/crop_verifier.py)
  - [result_parser.py](file:///d:/RAYSAN/ai-2d-checker/services/backend/infrastructure/audit/comparison/full_ai/result_parser.py)
- **Rule & Logic**: **Shim Tables (`シム表` / Shim Schedule)** listing thickness `t` (0.1, 0.3, 0.5, 1.0, 2.0), material (`C2801P`/`SPCC`), quantity, `設計組厚サ` (designed set thickness), and `総厚サ` (total thickness) are auxiliary reference tables that are **explicitly IGNORED and EXCLUDED** from comparison results.
- **System Behavior**: No `canvas_markings` or summary rows are generated for Shim Tables. All Shim Table items are filtered out, leaving main view dimensions, tolerances, and title block data focused for audit.

### F. Smart Navigation Coordinate Bounds Guard (Preventing Viewport Fly-Away)

- **Target File**: [useCanvasInteraction.ts](file:///d:/RAYSAN/ai-2d-checker/apps/desktop/src/components/review/useCanvasInteraction.ts#L147-L175)
- **Root Cause**: When a selected item card in [ChecklistPanel.tsx](file:///d:/RAYSAN/ai-2d-checker/apps/desktop/src/components/review/ChecklistPanel.tsx) mapped to unanchored coordinates (`[0, 0]`, `NaN`, or coordinates outside drawing render bounds), the viewport center calculation (`targetX`, `targetY`) computed negative or multi-thousand pixel offsets, panning the canvas far outside the drawing boundaries.
- **Fix & Guard**: Added twin safety guards in `useCanvasInteraction.ts`:
  1. **Zero & Non-Finite Check**: Instantly skips camera auto-focus if coordinates are `[0, 0]` or non-finite.
  2. **Render Bounds Proximity Guard**: Verifies coordinates lie within the active drawing render bounds ($\pm 20\%$ margin). If outside, auto-focus is safely bypassed, keeping the canvas stable and centered on the drawing sheet.

### G. Identical Value Reconciliation Guard (Eliminating Contradictory `CONFLICT` Badges)

- **Target Files**:
  - [reconciler.py](file:///d:/RAYSAN/ai-2d-checker/services/backend/infrastructure/audit/comparison/reconciler.py#L123-L135)
  - [hybrid_orchestrator.py](file:///d:/RAYSAN/ai-2d-checker/services/backend/infrastructure/audit/comparison/hybrid_orchestrator.py#L140-L149)
- **Root Cause**: When deterministic vector extraction proved `ORIGINAL == REVISION` (e.g. `C5` vs `C5` or `R2` vs `R2`), but AI vision hallucinated/misclassified a difference, `reconciler.py` flagged a status mismatch and `_resolve_disputed` defaulted to `status_override="CONFLICT"`. This created a visual contradiction in the UI (`ORIGINAL: C5`, `REVISION: C5`, `Status: CONFLICT`).
- **Fix & Guard**:
  1. **Deterministic Vector Trust**: When deterministic vector parsing confirms identical text at a location (`det.status == "MATCHED"` and `det_orig == det_txt`), deterministic proof overrides AI misclassification, directly confirming **`MATCHED`** (green badge).
  2. **Identical String Guard in Disputed Resolution**: In `_resolve_disputed`, if `original_value == text_content` (e.g. `"C5"` == `"C5"` or `"R2"` == `"R2"`), the pipeline automatically resolves the finding as **`MATCHED`** instead of `CONFLICT`.

### H. Checkmark Marker Anchor Alignment & MTEXT Stripping

- **Target File**: [coordinate_resolver.py](file:///d:/RAYSAN/ai-2d-checker/services/backend/infrastructure/audit/comparison/coordinate_resolver.py#L18-L30)
- **Root Cause**: `calc_anchor` previously calculated horizontal offset using raw unstripped text strings (`e.properties.get("text")`). When MTEXT entities contained raw formatting block syntax (such as `{\fArial|b0|i0;R5}`, length = 30 chars), `text_len * height * 0.6` shifted the checkmark marker **50–80mm far to the right** away from the actual text entity.
- **Fix**:
  1. **MTEXT Syntax Stripping**: Added `_clean_text_for_anchor(raw_text)` to strip formatting blocks (`{\f...}`, `\P`, etc.) down to visible characters (`R5`).
  2. **Tightly-Coupled Offset**: Capped visible text length multiplier and reduced offset factor (`1.5mm` right of bounding box or clean text edge), ensuring checkmarks align tightly right next to the text on both drawings.

---

## 6. Verification Status & Test Suite Compliance

- **Backend (`pytest`)**: **152 Passed** / 0 Failed (`15.66s`).
  ```powershell
  services/backend/.venv/Scripts/python.exe -m pytest --ignore=services/backend/scratch
  ```
- **Desktop App (`vitest`)**: **5 Test Files Passed**, **33 Tests Passed** / 0 Failed (`5.84s`).
  ```powershell
  pnpm test
  ```
