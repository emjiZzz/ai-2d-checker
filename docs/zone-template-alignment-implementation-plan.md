# Hand-Aligned Zone Templates — Implementation Plan

**Project:** ai-2d-checker
**Source:** Follow-on to `docs/zone-bbox-overlay-implementation-plan.md`. That plan made zone detection *visible*; this one makes it *correctable*. Same phase/completion-log conventions.
**Status:** Not started.

## Context

The read-only overlay from the previous plan did its job on the first real drawing pair: `zone_detector.py` produces badly wrong boxes. Measured on `M7452A0N01_reference.dxf` (1155 × 817 units):

| zone | width | height | area | verdict |
| :--- | ---: | ---: | ---: | :--- |
| `views` | 90.3% | 95.2% | **85.9%** | swallows the whole sheet |
| `tolerance` | 91.0% | 34.4% | 31.3% | far too tall |
| `notes` | 46.6% | 59.7% | 27.8% | runaway; real notes are a small block |
| `title` | 58.5% | 39.1% | 22.9% | starts ~40% too high |
| `bom` | 38.9% | 4.3% | 1.7% | header row only |
| `title_upper_left` | 14.0% | 2.3% | 0.3% | header row only |

Rather than iterating on heuristics blind, the user's approach is to hand-align the boxes once and treat that as authoritative. This plan builds that: visible, draggable, resizable zones; alignment saved per sheet template; and the audit pipeline honoring the saved alignment.

A useful side effect: hand-aligned zones become **ground truth**. Any future work on `zone_detector.py` can then be measured (IoU against the template) instead of eyeballed.

## What already exists — and why it has never worked

Most of the editing machinery is already in the repo, and it is unreachable. Verified by grep, not assumed:

| Piece | State |
| :--- | :--- |
| `customRegions` in `reviewStore.ts:146` — boxes as **fractions** (`xMin/xMax/yMin/yMax`) | exists, 5 zones only (`views, notes, bom, title, iso`) |
| `updateCustomRegion` / `loadCustomRegions` / `resetCustomRegions` | exists, persists to **localStorage** keyed by drawing id |
| Drag machinery in `useCanvasInteraction.ts` — `activeDragHandle`, `hoveredHandleInfo`, center-drag to move, edge/corner handles to resize, via `screenToWorldUnflipped` | exists and looks complete |
| `isRoiEditModeEnabled` / `toggleRoiEditMode` | exists; **zero references in any `.tsx`** — no way to switch it on |
| Rendering of the region boxes and their handles | **does not exist.** `renderEntities.ts` has nothing for `customRegions` or handles |
| Any path sending regions to the backend | **does not exist.** localStorage only |

So today there is drag hit-testing against invisible rectangles that nothing can enable and that could not affect an audit even if edited. The previous plan's `renderZoneOverlays` supplies the missing renderer; this plan supplies the rest.

Two consequences worth stating plainly:
- The existing hardcoded `customRegions` defaults are unrelated to what the detector produces. Seeding the editor from them would make the user start from arbitrary numbers. **Seed from the detected boxes instead** (decision 3).
- `tolerance` and `title_upper_left` are absent from `customRegions` and must be added, or two of the seven zones stay uneditable.

## Revision after corpus measurement — the single-class zone model was wrong

This plan originally treated all seven zones as templatable. **Measured across the 6-drawing corpus (3 ref/rev pairs), that is false for three of them**, and the user identified it from the screen before the measurement confirmed it. Positional spread is the max variation of any of the four fractional edges, in percentage points of sheet:

| zone | spread | content_aware | class |
| :--- | ---: | :--- | :--- |
| `iso` | 0.0pp | **0/6** | **never detected** — spread is an artifact |
| `title_upper_left` | 3.8pp | 6/6 | frame furniture |
| `bom` | 4.6pp | 6/6 | frame furniture |
| `title` | 17.7pp | 6/6 | furniture, measurement contaminated |
| `notes` | 39.9pp | 4/6 | floating content |
| `views` | 40.4pp | 6/6 | floating content (complement) |
| `tolerance` | 72.8pp | 4/6 | furniture, measurement contaminated |

**`iso`'s 0.0pp stability is fake and was nearly acted on as if real.** No drawing in the corpus ever resolved it content-aware, so all six carry the identical percentage-grid guess. Zero variance across six identical guesses is absence of detection, not stability. An earlier note in this project read the same 0.0% ref-vs-rev agreement as evidence the zone was reliable; it is evidence the zone has never been found. **Any future stability metric must be read jointly with the detection rate, never alone.**

### The two classes

> [!WARNING] Superseded on 2026-07-29 — `views` moved to class 1.
> The classification below put `views` in "floating content" on the strength of its 33.0pp
> spread. **That reading was wrong.** The figure comes from `_derive_views_zone`, which takes
> the 5–95 percentile of *content* coordinates — it measures where the geometry sits, not
> where the sheet's drawing area is. The area is fixed by the template; the content in it is
> not. `views` is now templatable. Canonical statement:
> [[Gotcha - Zone Detection Accuracy & Stability]] → Practical guidance.
>
> Also superseded: `iso` is no longer "never detected" — the cause was `ELLIPSE`/`SPLINE`
> being dropped at ingestion. See [[Gotcha - Dropped ELLIPSE & SPLINE Geometry]]. It stays
> per-drawing, but for a different reason than this plan gives: roughly half of all sheets
> genuinely do not have one.

1. **Frame furniture** — `title`, `title_upper_left`, `bom`, `tolerance`, and (per the
   revision above) `views`. Printed sheet template, fixed position. Templating works and
   transfers. `title`/`tolerance` spread is very likely inflated by the cap-then-pad and flood-fill runaway defects recorded in the previous plan rather than by real movement — a printed title block does not wander. Re-measure after those are fixed before concluding otherwise.

2. **Floating content** — `notes` and `iso`. These move with the drawing's contents; both can land inside the area the drawing views occupy, and `iso` is frequently absent altogether. For these a pinned template box is **worse than no template**: it would assert a wrong position with full confidence on every subsequent drawing. They must be identified per drawing — deterministic anchors where they exist, AI vision where they do not.

### `views` is a predicate, not a box

`_derive_views_zone` defines it by exclusion, so it is irregular by construction and its bounding box is nearly the whole sheet (85.9% measured). Every consumer use is a containment test, so it needs no shape at all:

```
in_views(p) := inside(sheet, p) AND NOT any(inside(z, p) for z in other_zones)
```

That is exact, cannot be hand-aligned wrongly, and removes the zone whose bbox was the most misleading artifact in the overlay. Rendering shows the leftover region rather than one rectangle. **`views` is removed from the set of hand-alignable zones.**

### Consequences for the phases

- **Phase A** shipped with all seven zones editable. `notes`, `iso`, and `views` should be *shown* but not *savable to a template* — see A.6.
- **Phase B** templates furniture only.
- **Phase C** applies furniture overrides; floating zones keep detecting.
- **New: Phase D** — `iso` has no working detection at all. That is a genuine gap, not a tuning problem, and hand-alignment cannot paper over it because the zone moves.

## Architecture decisions

1. **Alignment is stored as fractions of `render_bounds`, never as absolute CAD units.** This is already the format `customRegions` uses and the only format that can transfer between sheets. Measured: the reference sheet is 1155 × 817 and the revision 462 × 327 — a 2.5× scale difference at *identical* aspect ratio (1.4141 both, A-series). Absolute coordinates transfer between those two not at all; fractions transfer exactly.

2. **Scope is per sheet template, confirmed with the user.** Align once, applies to every drawing sharing the template. The alternative (per drawing) would mean re-aligning on every upload.

3. **The editor seeds from server-detected zones, not from static defaults.** Entering edit mode converts the current detected boxes to fractions so the user starts from what the detector produced and nudges it. Starting from the unrelated hardcoded defaults would throw away the ~3 zones detection already gets roughly right (`bom`, `iso`, `title_upper_left` agreed within 3.2% between the two sheets).

4. **A saved template zone replaces detection for that zone; unpinned zones keep detecting.** Explicit human ground truth should beat a heuristic known to be wrong, but a partially-filled template must not blank out the zones the user has not gotten to yet.

5. **Template identity is the sheet aspect ratio, bucketed — with a known limitation recorded, not hidden.** All A-series sheets share 1.414, so two genuinely different layouts on A3 paper would collide into one template. Acceptable for a single company's drawing standard (which is the actual corpus) and cheap to refine later by adding discriminators to the signature. The template record carries a human-editable `name` so a collision is at least visible. **Do not** silently treat aspect ratio as proof of same layout in any user-facing copy.

6. **Phase C is the phase that changes audit output.** Phases A and B are inert with respect to comparison results. The moment `extract_dynamic_regions` honors overrides, BOM extraction, category assignment in `result_parser.py`, safe-zone exclusion, and crop-verifier tiles all shift. Comparison tests will need re-baselining, and that is a deliberate, separately-reviewable step — not something to slip in with a UI change.

## Build order

- **Phase A — the editor works.** Frontend only, localStorage. Visible boxes, handles, all 7 zones, an entry point. *Delivers the hands-on alignment tool.*
- **Phase B — alignment persists per template.** Backend model + endpoints; save/load by signature. Still inert for audits.
- **Phase C — the audit honors it.** `extract_dynamic_regions` accepts overrides; wire the four orchestrators and the zones endpoint. *Changes comparison results.*

Phase A is independently useful: the user can align and eyeball correctness before any schema exists.

---

## Phase A — Visible, editable zones

**Files:** `renderEntities.ts`, `reviewStore.ts`, `useCanvasInteraction.ts`, `TwoDWorkspace.tsx`, `drawingsApi.ts`

### A.1 Extend `customRegions` to all seven zones
Add `tolerance` and `title_upper_left` to the state shape and to all three default literals (initial, `resetCustomRegions`, `loadCustomRegions`'s two fallbacks — the defaults are currently duplicated four times; collapse them into one exported `DEFAULT_CUSTOM_REGIONS` constant while touching them, or the next zone added will miss one).

### A.2 Seed from detected zones
New action `seedCustomRegionsFromDetected(zones: DrawingZonesResponse, renderBounds: number[])`: converts each detected box to fractions and replaces `customRegions`, unless a saved alignment already exists for that drawing. Called on entering edit mode.

**Seeding must apply the Y-flip on the Y axis. X is a plain ratio.**

```
xMin = (zone.xmin - bx0) / W          xMax = (zone.xmax - bx0) / W
yMin = (by1 - zone.ymax) / H          yMax = (by1 - zone.ymin) / H   # note the swap
```

The reasoning, because this is the single easiest thing in this plan to get backwards — an earlier revision of this document stated the opposite:

- **Detected zones are in CAD space, Y-up.** Verified directly against entity coordinates, not inferred: the two notes lines in `M7452A0N01_reference.dxf` sit at CAD y=599.5 and y=577.9 within bounds y −37.125…779.625. Flipped, that places them 22% from the sheet top, which is where they visibly are. Unflipped would place them at 78%. Higher CAD y is nearer the top.
- **`customRegions` fractions are in Y-down space** — fraction 0 is the top of the sheet. Confirmed by the existing defaults: `title: yMin 0.75, yMax 0.98` is near the *bottom*, which is where a title block belongs, and by the hit-test math at `useCanvasInteraction.ts:558-561`, where `yMin_frac = 0` maps to `viewport.y` (screen top).

So the two spaces have opposite Y directions and the conversion between them must flip and swap min/max. There is **no** contradiction between this and the previous plan's decision 7, and `coordinateTransform.ts`'s note that ROI editing "is not inverted" is accurate for fraction space — the existing hit-test is correct and must not be "fixed."

Rendering editable boxes therefore uses the *unflipped* fraction→screen mapping copied from the hit-test, not `worldToScreen`. Read-only detected boxes keep using `worldToScreen`. Two mappings, two input spaces, both correct; a round-trip test in A.5 pins the pair.

### A.3 Render editable zones with handles

The hit-test is the pre-existing half of this contract and the renderer must match it exactly — it was read before writing this section, and these are its actual terms (`useCanvasInteraction.ts:549-580`):

- **One zone is editable at a time**, keyed by `selectedComparisonRegion` — not all seven simultaneously. The UI therefore needs a way to pick the active zone; without it, edit mode can only ever move whichever zone that field already holds.
- **Four corner handles only** (`top-left`, `top-right`, `bottom-left`, `bottom-right`) — not eight. No edge-midpoint handles.
- **Hit radius is 12px**, via `Math.hypot(mx - hx, my - hy) <= 12`, in screen pixels.
- **Anywhere inside the box is a `center` (move) target.**
- Screen mapping is `(rxMin + w * frac - norm.xmin) * effectiveScale + viewport.x`, unflipped on both axes.

So: draw the active zone's box from `customRegions` using that same unflipped mapping, plus four corner handles at the corners sized to be comfortably grabbable at the documented 12px radius, and highlight the one in `hoveredHandleInfo`. Draw the other six zones read-only (from the detected payload) so the user can see the whole layout while editing one part of it.

Adding edge-midpoint handles is a reasonable later improvement, but it requires extending the hit-test too — do not draw affordances the hit-test does not recognize.

### A.4 Entry point
Add "Edit Zone Boxes" to the same ⋮ View menu as "Show Zone Boxes", calling `toggleRoiEditMode`. Enabling edit mode implies the overlay is shown. While editing, suppress the annotation-pin and violation-reticle click handling so a drag on a handle is never also a pin placement.

### A.5 Zone picker
Because only `selectedComparisonRegion` is editable at a time, edit mode needs a zone selector — a row of seven chips in the canvas header, colored to match the overlay, setting `selectedComparisonRegion`. Clicking a zone's box on canvas should also select it.

### A.6 Separate templatable zones from floating ones in the UI *(added by the revision above)*

The editor must not invite the user to align a zone whose alignment cannot be saved — that is wasted work and, worse, implies a guarantee the system cannot keep.

- **Templatable** (`title`, `title_upper_left`, `bom`, `tolerance`): full editing, saved to the template in Phase B.
- **Floating** (`notes`, `iso`): shown read-only from detection, with the reason stated in the UI — these move per drawing, so a pinned box would be wrong on the next sheet. Editing them may stay available as a *per-drawing* scratch aid, but must not offer "save to template."
- **`views`**: not editable at all. Render as the complement region.

Group the zone-picker chips into "Sheet template" and "Per drawing (detected)" so the distinction is visible rather than something the user has to infer after aligning and finding it did not stick.

### Phase A verification
Manual, and it is the real gate: enter edit mode, select each of the seven zones in turn, drag and resize onto its true feature, confirm boxes persist across a reload (localStorage), and confirm exiting edit mode leaves the aligned boxes rendered.

Automated:
- **Seeding round-trip**: detected CAD box → fractions → back to CAD returns the original within float tolerance.
- **Seeding orientation**: a zone in the CAD *upper* half (y near `ymax`) must seed to fractions in the *lower* numeric range (`yMin` near 0). This is the assertion that catches the flip being dropped or doubled — the failure it guards is a vertically mirrored set of seeded boxes, which looks plausible because most zones sit near the sheet's vertical centre.
- **Handle positions match the hit-test**: for a known box, viewport, and bounds, the rendered corner positions equal the coordinates the hit-test computes, so a visible handle is always a grabbable one.

---

## Phase B — Per-template persistence

**Files:** new `domain/models/zone_template.py`, `api/routers/zone_templates.py`, `api/schemas.py`, `drawingsApi.ts`, `reviewStore.ts`

### B.1 Model
```
ZoneTemplateDocument:
  signature: str      # indexed, unique — e.g. "aspect-1.414"
  name: str           # human-editable label; surfaces signature collisions
  zones: dict[str, {xMin, xMax, yMin, yMax}]   # fractions; only pinned zones present
  updated_by: str | None
  updated_at: datetime
```
Only pinned zones are stored, which is what makes decision 4 expressible: absent key means "keep detecting."

### B.2 Signature derivation
One shared helper, used by backend and mirrored in the client: `signature(render_bounds) -> str` from the bucketed aspect ratio. Must live in exactly one place per language and be referenced by path in a comment, like `comparisonStages.ts` / `coordinateTransform.ts` already do.

### B.3 Endpoints
- `GET /api/v1/zone-templates/{signature}` — returns the template or a 200 with `null` data (absence is normal, not an error)
- `PUT /api/v1/zone-templates/{signature}` — upsert the pinned zones

### B.4 Client
On drawing load, fetch the template for that drawing's signature; if present, use it to seed `customRegions` in preference to detected boxes (decision 3's exception). Add a **"Save as template"** action in edit mode, and show which template is active plus when it was last updated — an alignment tool that does not say what is currently in force is a guessing game.

### Phase B verification
Save from one drawing, load a second drawing of the same aspect ratio, confirm the template's boxes appear without re-aligning. Backend tests: signature bucketing, upsert-not-duplicate, partial (pinned-subset) round-trip.

---

## Phase C — The audit honors the template

**Files:** `table_extractor.py`, the four orchestrator call sites, `routers/drawings.py`

### C.1 Override parameter
`extract_dynamic_regions(entities, overrides: dict | None = None)`. After detection, replace each zone present in `overrides` (fractions × sheet bounds → absolute) and mark its confidence `"template_pinned"` in `_zone_confidence`. Zones absent from `overrides` are untouched.

`"template_pinned"` must flow through to the overlay, which should render pinned zones in a visually distinct style — otherwise there is no way to tell a hand-aligned box from a detected one, which is exactly the ambiguity this whole line of work exists to remove.

### C.2 Wire every call site
All four, or the pinned zones apply inconsistently by comparison method — the same defect the previous plan caught in its own first draft: `orchestrator.py:148`, `live_dxf_orchestrator.py:271`, `full_ai_orchestrator.py:64` **and** `:155`, plus the `/zones` endpoint.

Each site needs the drawing's `render_bounds` to resolve the signature, and each already has the drawing document in scope.

### C.3 Cache invalidation
Bump `COMPARISON_CACHE_VERSION`. Cached comparisons were computed against detected zones; after this change they are stale by definition. Beyond that, editing a template must invalidate cached comparisons for affected drawings — otherwise a user aligns the zones, re-runs, and sees the identical old result with no indication why. **Simplest correct approach: include the template's `updated_at` in the cache key**, so a template edit naturally misses cache without any explicit purge logic.

### Phase C verification
Re-run a comparison before and after pinning zones on the same pair and diff the findings; the BOM and title-block categories should change measurably. Re-baseline `test_physical_comparison.py` / `test_hybrid_pipeline.py` as needed, and record in the completion log which expectations changed and why — a test whose expected values were edited without explanation is indistinguishable from a test bent to pass.

---

---

## Phase D — Detection for the floating zones

Templates cannot solve these. Ranked by evidence:

**D.0 Cap-then-pad ordering — FIXED.** See the completion log entry below for measured effect. Two related experiments are recorded there so they are not repeated blindly.

**D.1 `iso` — 0/6 detected. No working detection exists.**
The percentage-grid fallback has been silently standing in for detection on every drawing. Worth checking first whether `ZONE_ANCHORS` even carries usable anchors for an isometric view — a 3D view often has no distinguishing *text* at all, which would explain a 0% hit rate and mean text-anchored detection is structurally the wrong tool. If so, candidates are geometric (a cluster of non-orthogonal lines outside the orthographic views) or AI vision, which already reasons visually in the `full_ai`/`hybrid` paths.

**D.2 `notes` — 4/6 detected, 39.9pp spread.**
Anchors exist and partly work; the box then over-expands (the runaway documented previously). Fixing the flood-fill likely helps more than new anchors here.

**D.3 `tolerance` — 4/6 detected, 72.8pp spread.**
Expected to be furniture. Investigate whether the spread survives the cap-then-pad fix before treating it as floating; if it does, the bottom-strip assumption in `default_pct` is wrong for this corpus.

**D.4 Measure against the templates.**
Once furniture is pinned, IoU of detected vs pinned furniture zones is a real accuracy metric. That converts all detector work from eyeballing to measurement — and is the strongest argument for doing Phase B before Phase D.

## Out of scope

- Fixing `zone_detector.py`'s flood-fill and cap-then-pad defects. Hand-aligned templates route *around* them. The defects remain (documented in the previous plan's completion log) and the templates now provide the ground truth to measure any fix against.
- Auto-deriving a template from multiple drawings, or clustering sheets into templates automatically.
- Per-drawing overrides on top of templates (the fourth option offered; not chosen).
- Rotating or non-rectangular zones.

## Completion log

### Phase A — Visible, editable zones — **done (unit-verified; visual check pending)**

`tsc --noEmit` clean. 14 new tests in `utils/zoneFractions.test.ts`; frontend suite 101 passed, 1 pre-existing failure (`RoomsView.test.tsx`, unrelated, confirmed in the previous plan).

What landed:
- **`utils/zoneFractions.ts`** — the single CAD↔fraction conversion, plus `fractionsToScreenRect` (the hit-test's mapping) and `normalizeFractions`.
- **`reviewStore.ts`** — `DEFAULT_CUSTOM_REGIONS` now exported and defined **once**; the literal was duplicated in **five** places (not four as this plan first estimated), so any zone added previously would have missed one. `tolerance` and `title_upper_left` added. New `seedCustomRegionsFromDetected` and `hasSeededCustomRegions`. `updateCustomRegion` now normalizes on write, so a handle dragged past its opposite edge can't persist an inverted box.
- **`renderEntities.ts`** — `renderZoneEditor`: all seven zones outlined, the selected one filled with four corner handles, drawn via `fractionsToScreenRect` so handles land exactly where the hit-test looks. Excluded from exports.
- **`CanvasRenderer.tsx`** — edit mode *replaces* the read-only overlay rather than drawing alongside it. Two near-identical box sets on screen with no indication of which one a drag affects would be worse than either alone.
- **`useCanvasInteraction.ts`** — exposes `hoveredHandleId`, preferring `activeDragHandle` over hover so the highlight survives the pointer leaving the handle mid-drag.
- **`TwoDWorkspace.tsx`** — "Edit Zone Boxes" in the ⋮ menu, plus a zone-picker bar with a Reset.

Constraints inherited from the pre-existing hit-test, both surfaced by reading it rather than discovered later:
- **One zone is draggable at a time** (`selectedComparisonRegion`). This is why the zone picker exists and is not optional garnish — without it, edit mode can only move whichever zone that field happens to hold. Entering edit mode defaults the selection to `title` so the mode is never inert.
- **Four corner handles only.** No edge-midpoint handles were drawn, because the hit-test does not recognize them and an affordance that does not respond is worse than an absent one.

**The Y-direction question was settled empirically and this document was wrong about it first.** An earlier revision of A.2 said seeding must *not* flip Y. It must. Detected boxes are CAD Y-up; `customRegions` fractions are Y-down. Verified against real entity coordinates — the two notes lines in `M7452A0N01_reference.dxf` are at CAD y=599.5 and y=577.9 within bounds y −37.125…779.625, and they render 22% from the sheet top, which is where they visibly sit; unflipped would put them at 78%. The correction and its evidence are now in A.2, and the orientation is pinned by a test rather than by comment.

**Scope limits to be aware of when testing:** alignment saves to **localStorage keyed by drawing id**. It does not yet transfer to other drawings (Phase B) and does not yet affect BOM extraction, category assignment, or comparison results (Phase C). Aligning boxes now changes what you see and nothing else.

**Not visually verified.** Whether the handles are comfortable to grab, and whether the seeded boxes land where expected on a real sheet, are manual checks the user is running in the Tauri app.

### Phase D.0 — Cap-then-pad ordering fix — **done**

`_expand_bbox` now pads and then clamps back inside `max_w`/`max_h`, trimming symmetrically so the box stays centred on the cluster that was found. Backend suite 311 passed, 2 pre-existing failures (`test_vision_ocr_grounding`, unrelated — confirmed by stash in an earlier phase).

Measured across the 6-drawing corpus, before → after:

| zone | spread | mean area | detected |
| :--- | :--- | :--- | :--- |
| `title_upper_left` | 3.8 → 3.8pp | 0.3 → 0.8% | 6/6 |
| `bom` | 4.6 → 4.6pp | 1.7 → 2.6% | 6/6 |
| `title` | 17.7 → **12.9pp** | 22.9 → **17.4%** | 6/6 |
| `views` | 40.4 → **33.0pp** | 85.9 → **78.9%** | 6/6 |
| `notes` | 39.9 → 37.1pp | 27.8 → **13.8%** | 4/6 |
| `tolerance` | 72.8 → **64.2pp** | 31.3 → **23.1%** | 4/6 |
| `iso` | 0.0 → 0.0pp | 9.5% | 0/6 |

Real but partial. Boxes are meaningfully tighter — `notes` nearly halved in area — yet only `title_upper_left` and `bom` are stable enough to template. `title` improved to 12.9pp but is still above the 8pp bar, and `tolerance` at 64.2pp is nowhere near it despite being printed furniture. **The revision's hypothesis that `title`/`tolerance` spread was purely padding contamination is therefore disproved**: something else moves those boxes, and Phase B's templatable set stays at two zones until that is understood.

**Negative result — scale-relative padding, tried and reverted.** `BBOX_PADDING` is absolute, so a 30-unit margin is 2.5× more significant on the corpus's 327-unit-tall sheet than on its 817-unit one, which looked like an obvious driver of cross-sheet fractional divergence. Implemented as fractions of sheet height calibrated to be a no-op on the reference sheet, then measured: `title_upper_left` and `bom` improved by 0.4pp and 0.3pp, `views` got **worse** by 3.0pp and `notes` by 0.6pp; `title` and `tolerance` were unchanged. Net neutral-to-negative, so it was reverted rather than kept on principle, and the reasoning is recorded at the `BBOX_PADDING` definition so the next person does not re-derive it. The scale hypothesis is wrong: absolute padding is not what drives zone instability here.

**Coverage gap this exposed.** The fix changed zone geometry on every drawing in the corpus and the entire backend suite still passed — nothing asserted on box size at all. `tests/test_zone_detector_caps.py` (10 tests) now pins the cap invariant, symmetric trimming, the tighter `exclude_lines` padding, and that padding is still applied when the cap is not breached.

One of those tests initially failed on a wrong assumption of mine, worth recording because the mental model is easy to repeat: the growth loop **refuses** expansions that would breach the cap rather than growing past it and being trimmed afterward. A box therefore never spans a cluster wider than `max_w`, and the clamp only ever removes padding overshoot. The test now exercises the case that actually reaches the clamp — a cluster that fits the cap but whose padded extent does not.

### Phase A.7 — Edit mode showed different boxes than the overlay — **fixed**

Reported from testing: "Show Zone Boxes" and "Edit Zone Boxes" rendered visibly different geometry. **Cause was an async race, not a coordinate-space bug.** `toggleZoneEditing` called `ensureZonesFetched()` and then read `zoneRegionsMap` from the React closure on the next line — empty on first activation, because the fetch had not resolved. Seeding silently never ran, so the editor fell back to `DEFAULT_CUSTOM_REGIONS` (a coarse guess unrelated to detection) while the overlay showed real detected boxes.

Verified the two mappings are algebraically identical before looking for the bug elsewhere: for a box converted by `zoneBoxToFractions`, `fractionsToScreenRect(...).top` reduces to `(by1 - zone.ymax) * scale + viewport.y`, exactly what `worldToScreen(zone.ymax)` yields. The spaces agree; only the data differed.

`ensureZonesFetched` now returns a promise, `toggleZoneEditing` awaits it, and post-await reads go through `getState()` rather than closure values that are stale by definition.

### Phase B — Per-template persistence — **done (backend verified live; UI unverified)**

- `domain/models/zone_template.py` — `ZoneTemplateDocument` (unique index on `signature`), `ZoneFractions`, and `zone_signature()`. Registered in `__all_models__`.
- `api/routers/zone_templates.py` — `GET`/`PUT /api/v1/zone-templates/{signature}`, wired into `api/v1.py`.
- `drawingsApi.ts` — `fetchZoneTemplate`, `saveZoneTemplate`, and `zoneSignature()` mirroring the backend helper.
- `TwoDWorkspace.tsx` — **"Save to template"** in the align bar, with inline saved/error feedback.

Round-trip verified against the running backend: absent template returns `200` with null data (absence is normal, not an error), `PUT` upserts, `GET` returns the pinned set. Backend suite 311 passed, 2 pre-existing failures.

**Only `TEMPLATABLE_ZONES` are saved** — `title_upper_left`, `bom`, `title`, `tolerance`. `notes`, `iso`, and `views` are excluded because they move (33–64pp measured), and pinning a moving zone asserts a wrong position confidently on every later drawing of the template. Their chips carry a `*` marker explaining they align per drawing only. `tolerance` is included on the argument that it is printed furniture whose 64pp spread is detector error — **that is a judgement call, not a measured fact**, and it is the first thing to revisit if a saved template misplaces the tolerance strip on a new sheet.

`PUT` replaces the zone set wholesale rather than merging, so un-pinning a zone is expressible; a merge would require a sentinel value to mean "stop pinning this."

**Not verified:** the save button in the running app, and whether a template loaded on a second drawing lands correctly. Phase C (audit honoring the template) is still not started, so saving a template currently changes nothing about comparison results.
### Phase A.8 — Two overlays collapsed into one — **done**

Requested from testing: remove "Show/Hide Zone Boxes" and keep only the alignment editor, since the aligned zones are what the comparison will be based on. Agreed — the two modes drew near-identical box sets with different meanings and no way to tell which one a drag would affect. That ambiguity was the root of the confusion in A.7, not just the seeding race.

- `renderZoneOverlays` **deleted**; `renderZoneEditor` is the single zone renderer. Zone boxes appear only in alignment mode.
- `showZoneBboxes` / `setShowZoneBboxes` removed from `ComparisonSlice`, `WorkspaceState`, `CanvasRenderer`, and the ⋮ menu. `zoneRegions` / `zoneErrors` / `fetchZoneRegions` stay — the detected payload is still needed for seeding and for confidence.
- `zoneOverlay.test.ts` retargeted onto the merged renderer (13 tests, still passing). Its harness now seeds fractions from detected CAD boxes exactly as the app does, so the Y-flip conversion is exercised by the render tests too, not only by `zoneFractions.test.ts`.

**The confidence signal was deliberately preserved, not dropped with the overlay.** Merging naively would have lost the one thing the read-only view showed that the editor did not: whether each box was measured or guessed. `renderZoneEditor` now takes the detected payload purely to mark it — dashed border and a `?` suffix for any zone the detector did not resolve `content_aware` — and the align bar carries an "N of 7 dashed = detector guess" summary so the count is legible without inspecting seven badges. The `percentage_fallback_no_sheet_bounds` suppression rule survives the merge unchanged.

That summary also gave `countFallbackZones` a real caller. It had become dead code the moment the read-only overlay was removed, which is the exact pattern this project flagged in `OverlayLayer.tsx` — an exported helper with tests and no production use.

Frontend suite 101 passed, 1 pre-existing failure (`RoomsView.test.tsx`). `tsc --noEmit` clean.

### Phase A.9 — Zone boxes are per drawing, not shared — **done**

Reported from testing: notes are one long sentence on the reference and an ordered list on the revision, so a single shared box would clip one side or swallow neighbouring content on the other and produce false mismatches. Correct, and it exposed a flaw in A.1–A.8: `customRegions` was **one set of fractions shared by both panes**.

An earlier note in this plan reasoned that "fractions are relative, so one set applies to both." That is true geometrically and wrong semantically — the two sheets share a *template*, not their *content extent*.

**The backend already disagreed with the UI.** `orchestrator.py:148-149` computes `ref_regions` and `rev_regions` independently, as do all four orchestrators. The shared editor set contradicted the model the audit actually runs on, so this was a UI defect rather than a new requirement.

Measured on the corpus pair, same template: `views` differs by **23.2pp in height** and 10.3pp in width between reference and revision. (`title`, `tolerance` and `iso` show exactly 0.0pp difference, which is not agreement — all three are clamped to their caps on both sheets, so the cap value is what matches.)

- `customRegions` is now `Record<drawingId, Record<zoneKey, fractions>>`, with `getRegionsFor`, and `updateCustomRegion` / `resetCustomRegions` / `seedCustomRegionsFromDetected` all taking a drawing id.
- `useCanvasInteraction` runs once per pane and already receives that pane's `drawing`, so each pane now reads and writes its own boxes with no new plumbing. Selecting a zone in the picker selects it on *both* panes; the boxes are independent.
- Entering edit mode seeds both panes from their own detected zones.
- "Save to template" takes furniture zones from the **reference** pane only — template zones are printed furniture, identical on both sides by definition; per-side boxes exist for the content zones, which are never templated.

**Two incidental cleanups this forced, both worth keeping:**

- `getRegionsFor` initially called `useReviewStore.getState()` from inside the store's own initializer. That circular reference collapsed `ReviewState` inference to `any` across *every* consumer of the store — `tsc` reported implicit-any errors in eight unrelated files. Fixed by taking zustand's `get`.
- Importing `DEFAULT_CUSTOM_REGIONS` from `reviewStore` broke `DrawingCanvas.test.tsx`, which mocks that module. Rather than patch the mock, `RegionFractions` and `DEFAULT_CUSTOM_REGIONS` moved to `utils/zoneFractions.ts` — where the maths that operates on them already lives, and which also removes a pre-existing import cycle (`reviewStore` → `zoneFractions` → `reviewStore`). Geometry consumers no longer import a zustand store to get a type.

Frontend suite 101 passed, 1 pre-existing failure. `tsc --noEmit` clean.

**Still unaddressed — the harder half of the reported problem.** Per-side boxes stop the *clipping* that would cause false mismatches. They do not solve comparing one long sentence against an ordered list: that is content comparison, and it belongs to the notes-comparison logic, not to zone geometry. Correct per-side boxes are a precondition for getting it right, not the fix. `iso` remains undetected on every drawing (0/6), so its box is a guess on both sides regardless of alignment.

### Phase C — Audit honors the template — **not started**

_(Append one entry per phase as it lands.)_
