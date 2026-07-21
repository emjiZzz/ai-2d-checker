# Refactoring Implementation Plan — Frontend God Component Decomposition

**Target repo:** `D:\RAYSAN\ai-2d-checker\apps\desktop`
**Snapshot verified:** 2026-07-07, via direct file read + line-count/grep verification (not estimated)
**Companion to:** `implementation_plan(AI-2D-Checker).md` (backend). Same execution philosophy: one phase at a time, test gate before proceeding, shim instead of rewrite, `.bak` rollback, no behavior changes.
**Executor-agnostic:** Written to be followed by Claude, a human, or another agent picking this up cold. Re-verify line numbers before editing if time has passed — this file only reflects the state as of the date above.

## User Review Required

> [!IMPORTANT]
> - There are currently no tests for the desktop app. We will introduce `vitest` into `apps/desktop` as the test runner.
> - Refactoring will proceed sequentially: Phase 0 and Phase 1 will be done first, and we will not proceed to Phase 2/3 until preceding phases are complete and verified.
> - Phase 4 (auth fix) MUST be developed, reviewed, and committed separately from the refactoring phases to avoid bundling behavioral/security changes with structural updates.
> - We will use `.bak` backup files for safety during transitions.
> - At every phase gate, re-run **all** prior phases' automated tests, not just the new ones added this phase — cheap insurance against unexpected cross-phase breakage.

---

## 0. Ground Truth (verified, not estimated)

| File | Lines | Status |
|---|---|---|
| `pages/workspace/AuditWorkspace.tsx` | **4,738** | 🔴 Critical — one component, 3,125-line JSX return, 958-line inline handler |
| `components/review/DrawingCanvas.tsx` | **1,956** | 🔴 Critical — 611-line render function, 6x duplicated coordinate-math |
| `components/StandardsManager.tsx` | 44.7 KB (not yet line-mapped) | 🟡 Flagged, out of scope for this plan — verify before assuming it's clean |
| `pages/admin/UserManagement.tsx` | 43.9 KB (not yet line-mapped) | 🟡 Flagged, out of scope |
| `pages/admin/AuditHistory.tsx` | 28.6 KB (not yet line-mapped) | 🟡 Flagged, out of scope |

**Existing test coverage:** none. Confirmed by `search_files` for `*.test.*` and `*.spec.*` across `apps/desktop` — zero matches. Worse than the backend's situation (which has `test_phase3`/`test_phase4` covering adjacent pipelines). **Phase 0 is not optional** — refactoring UI logic with zero tests is a rewrite wearing a refactor's clothes.

**Verified internal structure of `AuditWorkspace.tsx`:**

```
Line 44        parseUtcDate() helper
Line 50-220    UploadZone component (defined outside main component — correctly done, avoids remount)
Line 222       export const AuditWorkspace: React.FC = () => {  ← everything below is ONE component
Line 386-1343  runPhysicalComparisonAI()   — 958 lines, hand-rolled fetch, duplicates apiClient.ts's job
Line 1613      return (                     ← main JSX starts here
Line 1615-2140 LEFT SIDEBAR / checklist deck   (currentNav === "workspace" gated)
Line 2163-2168 STANDARDS tab                   → thin wrapper, just renders <StandardsManager/>
Line 2169-2600 HISTORY tab                     — 431-line IIFE inline in JSX, its own filtering/sorting logic
Line 2601-2622 SETTINGS tab                    — static form, no state wiring yet (dead/unfinished UI)
Line 2623-4738 WORKSPACE tab (dual-canvas view) — 2,115 lines, the actual audit workspace
```

Four unrelated "pages" living in one component, switched by `useNavStore().currentNav` string matching, not a router. Confirmed: zero `react-router` (or equivalent) imports anywhere in `App.tsx` or `AuditWorkspace.tsx`.

**Verified internal structure of `DrawingCanvas.tsx`:**

```
Line 97        export const DrawingCanvas = React.forwardRef(...)
Line 128-216   9x useState (drag state, marker drag state, ROI edit state, HUD toggle state)
Line 335-945   renderContent()  — 611 lines, one useCallback: grid + entity batching + text +
                                  violation reticles + crosshair + laser-sync, all inline
Line 946-970   drawCanvas()
Line 971-1000  useImperativeHandle (exportImage)
Line 1104-1136 handleWheel()
Line 1137-1263 handleMouseDown()   — 127 lines, includes marker hit-testing + ROI handle hit-testing
Line 1264-1492 handleMouseMove()   — 229 lines, includes marker drag, ROI drag, laser-sync, hover-hit-testing
Line 1493-1542 handleMouseUp()
Line 1543-1555 handleMouseLeave()
Line 1556-1615 handleContextMenu()
Line 1616-1956 JSX return           — canvas + custom context menu markup + 3 floating HUD panels + inline <style>
```

**Confirmed duplication:** the block deriving `normScale`/`xmin`/`ymin`/`effectiveScale` from `drawing.metadata.render_bounds` appears **6 times**, near-verbatim, at lines 1005, 1055, 1152, 1222, 1274, 1568 — plus a 7th slightly-different variant inside `renderContent` (~line 340). Highest-value extraction in the frontend: one bug fixed in 1 of 7 places and not the others is a silent, non-throwing visual regression (markers drift).

**Confirmed coupling requiring explicit design attention (not just math duplication):** `renderContent` (inside its violation-reticle block, ~line 555-870) *writes* to `markerPositionsRef.current[v.id] = { x: screenX, y: screenY }` during render. `handleMouseMove`'s hover hit-testing then *reads* that same ref to check distance-to-marker. This is a write-then-read dependency between the render pass and the interaction pass — not shared math, shared mutable state across what will become two separate modules in Phase 2. Also: `ctx.filter` gets explicitly reset to `'none'` immediately before violation reticles are drawn, specifically to cancel the Neon-CAD filter applied earlier in the same render pass — another piece of context state that must survive the split intact.

**Verified auth risk (flagging, not refactoring):** `stores/authStore.ts::initialize()` — on ANY `fetch('/api/v1/auth/me')` failure (not just genuine offline), the `catch` block reconstructs a full authenticated session, including admin `permissions: ["all"]`, purely from `localStorage` with zero server validation. Session token also stored in plaintext `localStorage`. This is Phase 4 — a fix, not a refactor.

---

## 1. Non-Negotiable Execution Rules

1. **One phase at a time.** Do not start Phase N+1 until Phase N's test gate passes. Check the Phase Completion Log before starting.
2. **No behavior changes during this refactor.** Pixel-for-pixel, interaction-for-interaction identical. Bugs found mid-move get a `// REFACTOR-NOTE:` comment, fixed in a separate pass — never fixed inline.
3. **Extract, don't rewrite.** Copy verbatim first, get it passing, clean up after. The moment logic changes mid-move, a failing test stops meaning "the move broke something."
4. **Rename originals to `*.tsx.bak` during transition; delete only after the gate passes.**
5. **Commit after each phase.** Format: `refactor(frontend): extract <module> from <original file> [phase N/4]`.
6. **If a moved function's behavior differs and you can't see why immediately, diff it byte-for-byte against the original.**
7. **Re-run all prior phases' automated tests at every gate**, not just the current phase's new tests.

---

## Phase 0 — Test Setup & Coordinate Transforms

**Why this exists:** Zero test files exist. `DrawingCanvas.tsx` does hand-rolled hit-testing math and coordinate transforms with no coverage. Lock in current behavior with pure-function characterization tests — skip visual/pixel snapshot testing, it's expensive and brittle for this pass.

### 0.1 — Stand up a test runner
No `vitest`/`jest` currently configured for `apps/desktop`.
1. Add `vitest` to `devDependencies` (pairs natively with Vite 7, near-zero config).
2. Add `"test": "vitest run"` to `scripts`.
3. Confirm `pnpm --filter desktop test` runs and picks up `*.test.ts` files.

**Test gate:** a trivial smoke test (`expect(1+1).toBe(2)`) passes via the new script.

### 0.2 — Extract and test the coordinate transform utilities

Create `apps/desktop/src/utils/coordinateTransform.ts`:
```ts
export interface RenderBounds { xmin: number; ymin: number; xmax: number; ymax: number }
export interface Viewport { x: number; y: number; scale: number }

// Consolidates the 6-7 duplicated inline blocks (DrawingCanvas.tsx lines 1005, 1055,
// 1152, 1222, 1274, 1568, and the renderContent variant ~340) into one function.
export function getNormalization(bounds: RenderBounds | null | undefined) {
  if (!bounds || bounds.xmax - bounds.xmin <= 0) {
    return { normScale: 1, xmin: 0, ymin: 0, ymax: 0, hasBounds: false };
  }
  return {
    normScale: 1000 / (bounds.xmax - bounds.xmin),
    xmin: bounds.xmin,
    ymin: bounds.ymin,
    ymax: bounds.ymax,
    hasBounds: true,
  };
}

export function worldToScreen(wx: number, wy: number, norm: ReturnType<typeof getNormalization>, viewport: Viewport) {
  const effectiveScale = viewport.scale * norm.normScale;
  const flippedY = norm.hasBounds ? norm.ymax + norm.ymin - wy : wy;
  return {
    x: (wx - norm.xmin) * effectiveScale + viewport.x,
    y: (flippedY - norm.ymin) * effectiveScale + viewport.y,
  };
}

export function screenToWorld(sx: number, sy: number, norm: ReturnType<typeof getNormalization>, viewport: Viewport) {
  const effectiveScale = viewport.scale * norm.normScale;
  const rawWy = norm.ymin + (sy - viewport.y) / effectiveScale;
  return {
    x: norm.xmin + (sx - viewport.x) / effectiveScale,
    y: norm.hasBounds ? norm.ymax + norm.ymin - rawWy : rawWy,
  };
}
```

**Execution steps:**
1. Read each of the 6 confirmed call sites (1005, 1055, 1152, 1222, 1274, 1568) plus the `renderContent` variant (~340) side by side. **They are not byte-identical** — some invert Y, some don't, some clamp differently. If there's a genuine behavioral difference between two sites (not just drift), that's a `// REFACTOR-NOTE:` for a later bugfix pass — do not silently "fix" it during extraction.
2. Write `coordinateTransform.test.ts` first, using known input/output pairs derived from *current* (possibly buggy) behavior — characterization, not aspirational.
3. Only once tests pass, replace each of the 7 inline blocks with calls to `getNormalization()` + `worldToScreen()`/`screenToWorld()`, one call site at a time, re-running tests + a manual pan/zoom/click smoke test after each.

**Test gate:** `pnpm --filter desktop test coordinateTransform` — all pass, plus manual smoke test of pan/zoom/marker-click/marker-drag shows no visual regression.

**Do not proceed to Phase 2 or 3 until 0.1 and 0.2 pass.** Phase 1 has no dependency on canvas math and can proceed in parallel.

---

## Phase 1 — Navigation Refactor (`AuditWorkspace.tsx` Decomposition)

**Risk: low-medium.** No canvas math involved, but touches every top-level page component's mount/unmount lifecycle.

> [!IMPORTANT]
> - **Navigation mechanism:** Do NOT introduce `react-router` or equivalent in this phase. Keep `useNavStore().currentNav` string-matching as the mechanism — only split the file structure. Swapping the mechanism is a separate, later, optional phase once views already exist independently.
> - **Settings view constraint:** The Settings view has no state wiring — it's a static mockup. It must remain unwired during this phase. Do not add feature/state logic while moving it; that turns a structural refactor into a feature change.

### Target structure:
```
apps/desktop/src/pages/workspace/
    AuditWorkspace.tsx        # thin shell: layout chrome + currentNav switch
    WorkspaceView.tsx          # lines 2623-4738 body (dual-canvas audit view)
    HistoryView.tsx            # lines 2169-2600 body (session history list/filtering)
    SettingsView.tsx           # lines 2601-2622 body (static — do not wire up)
    StandardsView.tsx          # lines 2163-2168 — trivial, re-exports <StandardsManager/>
```

### Execution steps:
1. Move History tab body (2169-2600) first — most self-contained (own IIFE, own local `useState`s at 1347-1349 for search/status/score filters move with it).
2. Move Workspace tab body (2623-4738) into `WorkspaceView.tsx`. The big one — owns most of the 25 `useState` hooks and `runPhysicalComparisonAI`. Don't shrink that function here — that's Phase 3. Move it wholesale.
3. Settings and Standards tabs are trivial moves.
4. `AuditWorkspace.tsx` becomes the shell: shared layout, the `currentNav` switch, nothing else. Target: under 200 lines.

### Test gate:
No automated navigation test exists — flag it, don't silently skip. Manual gate: click through all four tabs, confirm identical rendering, confirm switching away and back to Workspace doesn't lose in-progress state (should survive regardless since it's Zustand-backed, verify anyway). Re-run Phase 0's `coordinateTransform.test.ts` even though this phase doesn't touch that file.

---

## Phase 2 — `DrawingCanvas.tsx` Decomposition (1,956 → ~5 files)

**Depends on:** Phase 0.2 complete.
**Risk: medium-high.** Canvas rendering core; visual regressions are easy to miss and annoying to debug.

> [!IMPORTANT]
> - **Shared render context:** To avoid recomputing transform math per-function or dropping context-state resets (e.g. the `ctx.filter = 'none'` reset before violation reticles under Neon-CAD mode), extracted render functions must accept a shared context object computed once by the orchestrator:
>   ```ts
>   interface RenderFrame {
>     ctx: CanvasRenderingContext2D;
>     scale: number;
>     transX: number;
>     transY: number;
>     cullBounds: { minX: number; maxX: number; minY: number; maxY: number };
>     norm: ReturnType<typeof getNormalization>;   // from Phase 0.2 — do not recompute inline here
>     markerPositionsRef: React.MutableRefObject<Record<string, { x: number; y: number }>>;
>   }
>   ```
>   `markerPositionsRef` is included deliberately: `renderViolationReticles` **writes** screen positions into it during render, and `canvasInteraction.ts`'s hover hit-testing **reads** from it. Miss this and hover breaks silently — no error, markers just stop being clickable/highlightable, and it reads like a hit-radius bug when it's actually a stale/missing-ref bug.
> - **Hit-testing verification:** Diff the hit-test logic in `handleMouseDown` and `handleMouseMove` first. Only consolidate into a shared `hitTestMarker(mx, my, markers, viewport)` helper if verified identical. If consolidated, write `canvasInteraction.test.ts` for it. If they're intentionally different (e.g. different radius for click vs. hover), document why in a comment and leave them separate.

### Target structure:
```
components/review/canvas/
    DrawingCanvas.tsx           # orchestration only: builds RenderFrame, hooks up ref, mounts <canvas>, wires handlers
    renderEntities.ts            # split from the 611-line renderContent:
        renderGrid(frame)
        renderEntityBatch(frame, layers, activeLayers)
        renderViolationReticles(frame, violations, selectedViolation, ...)
        renderCrosshair(frame, mouseCoords, hoveredCoords, isLaserSyncEnabled)
    canvasInteraction.ts          # handleMouseDown/Move/Up/Leave, handleWheel, handleContextMenu
    canvasInteraction.test.ts     # only if hit-test consolidation happens (see above)
    CanvasHUD.tsx                 # 3 floating overlay panels (nav compass, quality toggle, diagnostics)
    CanvasContextMenu.tsx         # custom right-click menu markup
```

### Execution steps:
1. **HUD and context menu first** — pure presentational JSX, no canvas math, lowest risk.
2. **`canvasInteraction.ts` second** — diff hit-test logic per the note above before consolidating.
3. **`renderEntities.ts` last, in sub-steps, all consuming the shared `RenderFrame`:**
   a. `renderGrid()` — self-contained.
   b. `renderEntityBatch()` — the `Path2D` batching logic is performance-critical (it's why `pathBatches` exists — batched draw calls by stroke color/width). Don't regress to per-entity draw calls while extracting.
   c. `renderViolationReticles()` — largest single piece (~lines 555-870): sheet-isolation filtering, label-card collision avoidance, checkmark-vs-box rendering split by category, and the `markerPositionsRef` write. Extract carefully, diff against original before deleting.
   d. `renderCrosshair()` — smallest, extract last.
4. Wire back through `DrawingCanvas.tsx` as thin orchestrator, building `RenderFrame` once per render pass. Re-verify `useCallback` dependency arrays after the split — a common bug is relying on stale closure instead of passing a value through as an argument.
5. **Background-image loader:** while in this file, consider extracting the `useEffect`-based background-image fetch into its own `useBackgroundImage(drawingId)` hook rather than leaving it inline in the now-thin orchestrator — don't let "thin wrapper" quietly regrow a fetch-and-effect block. (The `apiClient` migration for this fetch itself is Phase 3's job, not this phase's — just don't block the extraction on that migration.)

### Test gate:
- Re-run Phase 0's `coordinateTransform.test.ts` — must still pass unchanged.
- New: `canvasInteraction.test.ts` if hit-test consolidation happened.
- Manual smoke test, explicitly including things easy to silently break: pan, zoom (wheel + keyboard), marker click/select, marker drag, marker delete (Alt+click), **hover a marker after panning/zooming — confirm the label card still appears** (this is the `markerPositionsRef` coupling check), ROI handle drag, laser-sync crosshair between both canvases, right-click context menu (including "Add Marker" submenu), **Neon CAD toggle — confirm no filter bleed onto violation reticles**, image export via `exportImage` on the imperative handle.

---

## Phase 3 — `runPhysicalComparisonAI` Refactor (958-line function)

**Depends on:** Phase 1 complete (function now lives in `WorkspaceView.tsx`).
**Risk: highest in this plan** — mirrors the backend's Phase 4: this drives the whole AI comparison workflow.

> [!IMPORTANT]
> **Mapping pre-work is a required first step, not optional context.** Before any extraction, read the full 958 lines start to finish and write down the actual step boundaries — the same rigor the backend plan applied to `perform_physical_comparison`'s 12 steps. The breakdown below is a rough hypothesis from a partial pass, not a verified map (step 4 in particular — the ~100-line response-parsing/checklist block — needs full re-verification). Do not extract against the hypothesis; extract against the verified map you build first.

### Current structure (rough, needs re-verification per above):
1. Guard clause + progress state setters (~10 lines)
2. Manual `fetch` with hand-built headers — bypasses `apiClient.ts` entirely, despite it existing and handling this exact pattern elsewhere (~40 lines)
3. Error message extraction from multiple response shapes (~20 lines)
4. Response parsing + checklist result population (~100 lines, unverified — map this properly before touching it)
5. Progressive `aiScanProgress` state updates (`scanning_ref` → `extracting` → `scanning_rev` → `comparing` → `completed`)
6. ~800 remaining lines: diff-row construction, category matching (`vCat === pKey || vCat.includes(pKey)`), pen-type-to-status mapping — presentation logic, belongs in a hook/pure function, not welded to the fetch

### Target structure:
```
services/comparisonService.ts
    async function runPhysicalComparison(oldDrawingId, newDrawingId): Promise<ComparisonResult>
        # Migrated onto apiClient.post() — removes ~40 lines of hand-rolled
        # header/timeout/error-shape logic, gains the same normalization every
        # other apiClient consumer already has.

hooks/useComparisonProgress.ts
    # Owns the aiScanProgress state machine as a reusable hook, decoupled from
    # the 25-useState soup in WorkspaceView.tsx.

utils/buildDiffRows.ts
    # Pure diff-row / category-matching / status-normalization logic.
    # No fetch, no React state — testable in isolation. This is where
    # "MATCHED includes MIS but shouldn't count as matched" bugs live.
```

### Execution steps:
1. **Do the mapping pass first** (see callout above) — do not skip this step or approximate it.
2. Extract `buildDiffRows()` first — pure logic, easiest to characterize, lowest risk.
3. Extract `useComparisonProgress()` second — state machine, testable independent of the network call.
4. Migrate the fetch itself onto `apiClient.post()` last, once surrounding logic is already out and the diff is small.
5. **Migrate `DrawingCanvas.tsx`'s background-image loader fetch onto `apiClient` in this same phase** — same bypass pattern, much smaller blast radius, worth doing while `apiClient` migration is already the active concern.

### Test gate:
- Unit tests for `buildDiffRows()` covering `MATCHED`/`CHANGED`/`ADDED`/`REMOVED`/`MISSING` normalization, including the `statusUpper.includes('MATCHED') && !statusUpper.includes('MIS')` edge case — this looks purpose-built to avoid `MISMATCHED` false-matching `MATCHED`, a natural regression target.
- Re-run Phase 0 and Phase 2 test suites.
- Manual smoke test: run an actual comparison against the local backend — automated tests catch logic regressions, not "the real API's response shape drifted."

---

## Phase 4 (Separate Change, Not Gated Into the Refactor) — Auth Offline-Fallback Fix

> [!WARNING]
> **Do not bundle this into any refactor commit.** It's a security-relevant behavior change, not a structural move — the entire point of Phases 0-3 is that behavior doesn't change. This needs its own review pass and its own PR.

`stores/authStore.ts::initialize()` currently trusts `localStorage` for full re-authentication (including admin `permissions: ["all"]`) on ANY `fetch` failure to `/api/v1/auth/me`, not specifically genuine offline.

1. Distinguish `TypeError: Failed to fetch` (genuine network-down, safe to fall back) from any other failure (expired token, 401, 500 — none of which should silently grant access).
2. On the non-network-down path, treat it the same as `logout()` — token presumed invalid until proven otherwise.
3. Consider marking the offline-fallback session as degraded/read-only in the UI (e.g. a banner: "Working offline — some actions unavailable until reconnected") rather than silently granting full admin permissions.

---

## Definition of Done

- [ ] Phase 0.1 (test runner) complete
- [ ] Phase 0.2 (coordinate transform extraction + tests) complete
- [ ] Phase 1 complete — `AuditWorkspace.tsx` is a thin shell (~200 lines), four view components exist independently, Settings remains unwired
- [ ] Phase 2 complete — `DrawingCanvas.tsx` split into orchestrator + render/interaction/HUD/menu modules via shared `RenderFrame`, `markerPositionsRef` coupling verified working, full manual QA checklist passed
- [ ] Phase 3 complete — `runPhysicalComparisonAI` reduced to a thin call into `comparisonService.ts`, `buildDiffRows()` has unit tests, both this and `DrawingCanvas`'s background-image fetch go through `apiClient`
- [ ] Phase 4 — auth fallback bug fixed and reviewed as its own separate change, not bundled into any refactor commit
- [ ] `git log` shows one commit per phase, no stray commits mixing phases
- [ ] No `.bak` files left in the repo
- [ ] `pnpm --filter desktop test` run once at the very end — every test passes, not just the ones this plan explicitly names

## Phase Completion Log

```
Phase 0.1: [ ] not started   [ ] in progress   [ ] complete — test output: ___
Phase 0.2: [ ] not started   [ ] in progress   [ ] complete — test output: ___
Phase 1:   [ ] not started   [ ] in progress   [ ] complete — manual QA notes: ___
Phase 2:   [ ] not started   [ ] in progress   [ ] complete — manual QA checklist: ___
Phase 3:   [ ] not started   [ ] in progress   [ ] complete — test output: ___
Phase 4:   [ ] not started   [ ] in progress   [ ] complete — reviewed separately: ___
```
