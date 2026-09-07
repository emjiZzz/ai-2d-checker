# Visual Zone Bounding-Box Overlays on the 2D Review Canvas — Implementation Plan

**Project:** ai-2d-checker
**Source:** Revision of an initial draft plan, rewritten after a codebase review that found four blocking defects in the original backend approach. Follows the phase/completion-log conventions of `docs/hybrid-comparison-engine-implementation-plan.md`.
**Status:** Not started. Revised twice. The second review pass corrected the confidence model (three values, not two), Phase 4's degraded-state handling, the Phase 5 schema regression test, a contradiction in Phase 3.2 about where the draw helper runs, and a false claim about `PYTHONPATH` — all wrong in the first revision. Claims in this document that cite a file and line have been checked against the code; claims about timing and cost have not been measured and say so.

## Context

`zone_detector.py` / `extract_dynamic_regions()` decide, per drawing, where the title block, BOM table, tolerance strip, notes, ISO view, upper-left metadata block, and main drawing views physically live in CAD coordinates. Every downstream audit path depends on those boxes: BOM row extraction is clipped to `bom`, the RAG orchestrator excludes safe zones from comparison, `result_parser.py` assigns findings to categories by which box contains them, and the crop verifier renders image tiles from them.

Today those boxes are invisible. When a finding lands in the wrong category, or the BOM extractor returns nothing, there is no way to tell whether zone detection produced a sane box, ran away and swallowed half the sheet, or silently fell through to the percentage-grid fallback — short of adding print statements and re-running the pipeline. This plan makes the boxes visible on the review canvas behind a toggle, with their detection confidence, so that question is answered by looking.

The audience is engineers and developers debugging the audit pipeline, not end reviewers. The overlay is off by default and is a diagnostic surface, not a product feature.

**A note on what "no box" means here, because it shapes the whole design.** `extract_dynamic_regions()` never returns a missing zone. It pre-populates all seven keys from a percentage grid first (`table_extractor.py:48-57`), then content-aware detection *overrides* per zone where a semantic anchor was found (:64-74). Every zone always has a box. The question this overlay answers is therefore never "was a zone detected?" — it is **"is this box a measurement or a guess?"** Everything below follows from that.

## What changed from the original draft, and why

The first draft proposed threading `spatial_regions: Optional[dict]` through `PhysicalComparisonResponse` / `ComparisonDiagnostics` and populating it from two orchestrators. Review against the code found four defects; all four are addressed by the architecture decisions below rather than patched individually.

1. **`Optional[dict]` on `PhysicalComparisonResponse` breaks every AI comparison request.** `gemini_client.py:75` passes that model directly as Gemini's `response_schema`. A bare `dict` field emits open-ended `additionalProperties`, which Gemini rejects with `400 INVALID_ARGUMENT` on *every* call, populated or not. The `ComparisonDiagnostics` docstring (`schemas.py:336`) already documents this exact failure — it is why that model is a fixed-field model instead of a dict in the first place.
2. **`extract_dynamic_regions()` does not return a clean bbox map.** It smuggles two non-bbox keys into the same dict: `safe_zones` (a list) and `_zone_confidence` (a `dict[str, str]`) — see the comment at `table_extractor.py:37`. Serializing it wholesale into a bbox-typed schema raises a validation error.
3. **Two of four call sites were missing.** `extract_dynamic_regions` is called in `orchestrator.py:148`, `live_dxf_orchestrator.py:271`, and **twice** in `full_ai_orchestrator.py` (:64 and :155). `hybrid_orchestrator.py` also assembles a `PhysicalComparisonResponse`. Covering only two means the overlay silently renders nothing for `rag_ai` and `hybrid`.
4. **Cached comparisons would return no regions.** `orchestrator.py:859` and `live_dxf_orchestrator.py:254` both do `PhysicalComparisonResponse(**cached)` from disk JSON. Every existing cache entry predates the new field, so the overlay would be empty on cache hits until Force Refresh — indistinguishable from a bug.

## Architecture decisions

1. **Zone boxes are served by their own endpoint, not carried on the comparison response.** Zone detection is pure geometry over already-parsed entities — no AI call, no drawing pair, no cache dependency. Coupling it to the comparison response means an engineer debugging a bad BOM box must burn an LLM call (or wait on a cache) to see it, and can never inspect a single drawing in isolation. A dedicated `GET /api/v1/drawings/{id}/zones` is a smaller backend delta than four orchestrator edits and structurally sidesteps defects 1, 3, and 4. **This is the load-bearing decision in this plan** — every other simplification follows from it.

2. **`PhysicalComparisonResponse` and `ComparisonDiagnostics` are not touched.** They are the LLM's structured-output contract. Diagnostic telemetry that the model neither produces nor consumes does not belong on them. If a future need arises to freeze zone boxes into the persisted audit record, that is a separate change to the persistence layer, and it must use fixed-field models — never a bare `dict`.

3. **The response model mirrors the existing `BoundingBox2D` field shape but does not import it.** `BoundingBox2D` (`infrastructure/audit/comparison/schemas.py:17`) is the precedent for `xmin/ymin/xmax/ymax` floats and the new model matches it exactly, but importing an infrastructure DTO into `api/schemas.py` points the dependency the wrong way for a transport model. Validate inline in the router instead. (The repo is already loose here — the new `domain/contracts.py` imports *upward* from `api.schemas`, and no test enforces layering — so this is a preference, not a rule being defended.) The seven zone keys are a closed set, already enumerated in `default_pct` in `table_extractor.py`, so the response model has seven explicit fields, not an open map. The new models are deliberately **not** re-exported from `domain/contracts.py`: they are transport for a debug view, not domain contracts.

4. **`_zone_confidence` ships with the boxes and is rendered.** For a debugging tool, knowing a box was a guess rather than a measurement matters more than seeing the box. A percentage-grid box is *always* plausible-looking and *always* in roughly the right place — that is exactly what makes it dangerous to eyeball. There are **three** values, not two (`table_extractor.py:53/57/74`), and the third is the one that matters:

   | Value | Meaning | Treatment |
   | :--- | :--- | :--- |
   | `content_aware` | Semantic anchor found, box flood-filled around it. A measurement. | Solid stroke. |
   | `percentage_fallback` | No anchor; percentage grid over real sheet bounds. A plausible guess. | Dashed stroke, `?` in badge. |
   | `percentage_fallback_no_sheet_bounds` | `compute_drawing_bounds` returned nothing; **all seven zones are the literal placeholder `(0, 0, 1000, 1000)`**. Not a guess about this drawing — no information at all. | **Draw nothing.** Banner instead (decision 5). |

5. **When zone detection had no sheet bounds, the overlay renders no boxes at all.** On a drawing whose CAD coordinates are in the hundreds of thousands, seven identical `(0,0,1000,1000)` rectangles land as a speck near the origin, far off the visible sheet. An engineer reads that as "the overlay is broken" or "detection put everything in the corner," when the real fact is that bounds computation failed upstream and zone detection never meaningfully ran. A diagnostic tool that renders fabricated geometry during its own upstream failure is worse than no tool. Suppress the boxes; show the reason.

6. **Boxes are drawn inside `CanvasRenderer`'s existing transform pass, not as an SVG sibling layer.** The canvas is a raster `<canvas>` drawn imperatively; a React-rendered SVG overlay updates on a different tick and visibly lags during drag. Drawing in the same `ctx.translate/scale` block that draws entities gives frame-perfect sync, which is the entire point of the feature. Cost: styling is canvas API rather than CSS. Accepted.

7. **The Y-flip is not re-derived.** `coordinateTransform.ts` is the single implementation of screen↔world maths and its header comment spells out the three-conversion contract. Zone boxes are world-space points, so they use `getNormalization` + `worldToScreen` — which means `ymin`/`ymax` **swap** when they become screen top/bottom. Getting this backwards mirrors every box vertically, and because most zones are roughly symmetric about the sheet centre, a mirrored box looks almost right. Phase 5's test asserts the swap explicitly.

8. **Each canvas instance renders only its own drawing's zones.** `DrawingCanvas` is mounted twice in `TwoDWorkspace.tsx` (reference at :68, revision at :136) and `DrawingCanvasProps` currently has no side discriminator. Zones are fetched per drawing id and passed as a prop, so there is no ref/rev mix-up possible by construction.

9. **`OverlayLayer.tsx` is left alone.** It is an existing stub with a hardcoded `mockOverlays: [] ` and no live data source. This plan neither extends nor deletes it — noted here so the next reader does not assume the new overlay lives there. Removing it is out of scope.

## Zone definitions

Seven zones, matching the keys already produced by `extract_dynamic_regions()`. Colors are chosen for distinguishability at low opacity against both light and dark canvas backgrounds.

| Zone key | Description | Color | Hex |
| :--- | :--- | :--- | :--- |
| `title` | Bottom-right title block | Indigo | `#818cf8` |
| `title_upper_left` | Top-left metadata block | Teal | `#2dd4bf` |
| `bom` | Bill of materials schedule | Emerald | `#34d399` |
| `tolerance` | General tolerance table | Amber | `#fbbf24` |
| `notes` | Technical notes & requirements | Rose | `#fb7185` |
| `iso` | 3D isometric view | Violet | `#c084fc` |
| `views` | Main geometry drawing views | Sky | `#38bdf8` |

Rendering per zone: 1.5px stroke at full color, 8% fill, and a small filled badge at the box's top-left with the zone label in uppercase. `content_aware` zones use a solid stroke; `percentage_fallback` zones use a dashed stroke and append `?` to the badge label. `percentage_fallback_no_sheet_bounds` is not a per-zone style at all — it is set for every key at once, and the whole overlay is suppressed (decision 5). Stroke width and badge text are drawn in screen space (constant apparent size) even though box corners are transformed — a 1.5px stroke scaled by a 25× zoom would be a 37px slab.

`safe_zones` and `_zone_confidence` are reserved keys, not zones, and are never rendered as boxes.

## Build order

1. **Phase 1** — Backend: response models + `/drawings/{id}/zones` endpoint.
2. **Phase 2** — Frontend: API client, store state, toggle button.
3. **Phase 3** — Frontend: canvas rendering of boxes and badges.
4. **Phase 4** — Degraded states and fallback styling.
5. **Phase 5** — Tests.

Phases 1 and 2 are independently shippable and independently verifiable (endpoint via curl; toggle via a stubbed response).

---

## Phase 1 — Backend: zone endpoint

**Files:** `services/backend/api/schemas.py`, `services/backend/api/routers/drawings.py`

### 1.1 Response models

Add to `schemas.py`, near the other response models. These are plain API models with no relationship to the Gemini-facing schemas — add a comment saying so, since they sit in the same file as models that *are* LLM-facing and the distinction is invisible otherwise.

```python
class ZoneBBox(BaseModel):
    """One detected zone's CAD-world bounding box, plus how it was resolved.

    Not part of any LLM structured-output schema — this model is only ever
    serialized outward to the desktop client by GET /drawings/{id}/zones.
    Do not nest it into PhysicalComparisonResponse; see that model's sibling
    ComparisonDiagnostics docstring for why open-ended shapes break Gemini's
    response_schema validation.
    """
    xmin: float
    ymin: float
    xmax: float
    ymax: float
    confidence: str = Field(
        default="unknown",
        description="How this box was resolved, verbatim from _zone_confidence: "
                    "'content_aware' (semantic anchor found, box flood-filled — a "
                    "measurement), 'percentage_fallback' (no anchor; percentage grid over "
                    "real sheet bounds — a plausible guess), or "
                    "'percentage_fallback_no_sheet_bounds' (no sheet bounds at all; the "
                    "box is the literal (0,0,1000,1000) placeholder and means nothing). "
                    "Pass the value through unmapped — the client decides presentation, "
                    "and collapsing the last two here would hide the only case that must "
                    "not be drawn."
    )


class DrawingZonesResponse(BaseModel):
    """Fixed-field, not a map: the seven zone keys are a closed set, enumerated in
    table_extractor.default_pct.

    In practice every zone is always populated — extract_dynamic_regions() fills all
    seven from the percentage grid before content-aware detection overrides any of them,
    so there is no "zone not found" case. The fields are Optional purely so a future
    detector change, or a malformed tuple rejected at the boundary, degrades to a missing
    box rather than a 500. Client code must not treat None as a meaningful signal; the
    signal is `confidence`.
    """
    drawing_id: str
    render_bounds: Optional[list[float]] = None
    views: Optional[ZoneBBox] = None
    notes: Optional[ZoneBBox] = None
    bom: Optional[ZoneBBox] = None
    title: Optional[ZoneBBox] = None
    tolerance: Optional[ZoneBBox] = None
    iso: Optional[ZoneBBox] = None
    title_upper_left: Optional[ZoneBBox] = None
```

`render_bounds` is included so the client can sanity-check that the boxes and the canvas agree on the drawing's extent before trusting on-screen positions — the same `boundsMatch` idea already used for annotation coordinates.

### 1.2 Endpoint

Add to `drawings.py`, modeled directly on the existing `get_drawing_scene` (:231-273) — same `get_or_404` + `ExtractedEntity.find(...)` load, same `ENTITIES_NOT_READY` error shape when the entity set is empty. Do not invent a new error contract.

```python
@router.get(
    "/drawings/{id}/zones",
    response_model=StandardResponse[DrawingZonesResponse],
    summary="Detected template-zone bounding boxes for canvas debug overlay",
    dependencies=[Depends(get_auth_token)]
)
async def get_drawing_zones(id: str):
    ...
```

Body:
1. `get_or_404(DrawingDocument, id, ...)`.
2. Load entities; if empty, return the `ENTITIES_NOT_READY` failure shape used by `/scene`.
3. `regions = extract_dynamic_regions(entities)` (import from `...infrastructure.audit.bom.table_extractor`).
4. `render_bounds` from `(drawing.metadata or {}).get("render_bounds")` — a flat `[xmin, ymin, xmax, ymax]` list, matching what `parseBounds` in `coordinateTransform.ts` already expects.
5. Hand both to the builder below and return its result.

**Put the mapping in a module-level pure function, not inline in the handler:**

```python
def build_zones_response(
    drawing_id: str,
    regions: dict,
    render_bounds: list[float] | None,
) -> DrawingZonesResponse:
```

It **explicitly whitelists the seven keys** — never iterates `regions`, which also contains `safe_zones` (a list) and `_zone_confidence` (a dict) and will raise on bbox validation. For each key it validates the tuple (length 4, all coercible to float) so a malformed tuple fails at the boundary rather than reaching the client, and attaches `(regions.get("_zone_confidence") or {}).get(key, "unknown")`.

Keeping it a free function is what makes backend tests 1 and 2 possible without a FastAPI client, a Mongo fixture, or a real DXF — they call `build_zones_response` with a hand-built dict. Inline in the handler, the reserved-key regression test (the one guarding the defect that motivated this plan) becomes an integration test nobody runs.

**Cost note:** `extract_dynamic_regions` runs flood-fill over every entity, so cost scales with entity count. It has not been measured on a large sheet and this plan does not assume it is cheap — it avoids the question instead: the endpoint is only hit when an engineer switches the toggle on, and the result is cached client-side per drawing id (Phase 2). Do **not** call it eagerly on drawing load. If it does prove slow, cache it in `drawing.metadata` at parse time — deliberately not done now, since that adds a metadata migration for a debug feature.

### Phase 1 verification
Start the backend and hit the endpoint for a drawing whose entities are already extracted; confirm seven keys, coordinates that fall inside `render_bounds`, and a `confidence` value on each. Confirm a drawing with no extracted entities returns the `ENTITIES_NOT_READY` shape rather than a 500.

Note for whoever runs this: on a healthy drawing you should see a *mix* of `content_aware` and `percentage_fallback` — all seven coming back `content_aware` is more likely a bug in the confidence plumbing than a perfectly-anchored drawing.

---

## Phase 2 — Frontend: client, state, toggle

**Files:** `apps/desktop/src/services/drawingsApi.ts`, `apps/desktop/src/stores/workspace/types.ts`, `apps/desktop/src/stores/workspace/slices/createComparisonSlice.ts`, `apps/desktop/src/components/review/TwoDWorkspace.tsx`

### 2.1 API client

Add `fetchDrawingZones(id, signal?)` to `drawingsApi.ts` alongside `fetchDrawingScene`, following the same `buildHeaders` / `parseOrThrow` pattern. Type it properly (`DrawingZonesResponse`) rather than `Promise<any>` — `fetchDrawingScene` returns `any`, but that is not a precedent worth extending. Mirror the seven-key shape as a TS interface with a comment pointing at `schemas.py::DrawingZonesResponse`; the repo has no cross-language type sharing (same situation as `comparisonStages.ts` and `coordinateTransform.ts`, both of which hand-mirror backend types with a pointer comment).

### 2.2 Store state

**`workspaceStore.ts` is a slice aggregator, not a state file** — nothing is declared there directly. Add to `createComparisonSlice.ts`, with the fields declared on `WorkspaceState` in `stores/workspace/types.ts`:

- `showZoneBboxes: boolean` — default `false`.
- `setShowZoneBboxes(show: boolean)`.
- `zoneRegions: Record<string, DrawingZonesResponse>` — keyed by drawing id, so both canvases read from one cache and a ref/rev pair costs two fetches, once.
- `fetchZoneRegions(drawingId: string)` — no-op if already cached; fetch and store otherwise.

Do **not** add `showZoneBboxes` or `zoneRegions` to the persisted partial in `saveWorkspaceState` — this is a per-session debug toggle, and persisting cached boxes to IndexedDB would serve stale geometry after a re-parse.

### 2.3 Toggle

Add a `Zones` toggle button to the viewport header in `TwoDWorkspace.tsx`, beside the existing **Reset Viewport** control at :557. (Note: the draft referred to "Zoom" and "Reset View" buttons — the actual control is labeled "Reset Viewport" and there is no discrete Zoom button.) Match the surrounding buttons' styling; use a `lucide-react` icon (`SquareDashedBottom` or similar) rather than an emoji, consistent with every other control in that header.

On toggle-on, call `fetchZoneRegions` for both `oldDrawing.id` and `newDrawing.id` (guarding for null).

### Phase 2 verification
`npx tsc --noEmit` clean. Toggle flips state and issues exactly two network requests on first activation and zero on subsequent toggles.

---

## Phase 3 — Canvas rendering

**Files:** `apps/desktop/src/components/review/DrawingCanvas.tsx`, `apps/desktop/src/components/review/CanvasRenderer.tsx`, `apps/desktop/src/components/review/renderEntities.ts`

### 3.1 Prop threading

Add `zoneRegions?: DrawingZonesResponse | null` and `showZones?: boolean` to `DrawingCanvasProps`, passed down to `CanvasRenderer`. `TwoDWorkspace` supplies each canvas its own drawing's entry from the store cache. `DrawingCanvas` must **not** read `showZoneBboxes` from the store directly and derive which drawing it is — the component has no side discriminator today and adding one is the wrong fix (decision 8).

### 3.2 Drawing the boxes

Add a `drawZoneOverlays(ctx, zones, norm, viewport)` helper — new function in `renderEntities.ts`, called from `CanvasRenderer` **after entities are drawn and after `ctx.restore()`**, so boxes sit on top and the helper works in screen space.

Two placements are possible and the choice is not arbitrary:

- *Inside* the active `ctx.translate(transX, transY); ctx.scale(scale, scale)` block, box corners are world units and the canvas does the transform — but every stroke width and font size must then be divided by `scale` to stay visually constant, scattering `/scale` through the helper.
- *After* `ctx.restore()`, the helper transforms the four corners itself via `worldToScreen` and draws in plain screen pixels, so constant apparent size is the default rather than something maintained by division.

**Take the second.** It keeps the one rule that matters — screen-space stroke and text — structural rather than a convention someone can forget on the next line they add. Note this means the helper needs `norm` and `viewport`, not the canvas's composed transform.

Apply the CAD Y-flip via `coordinateTransform.ts`'s `worldToScreen`. Remember `ymin` maps to the **larger** screen Y — the box's screen top is derived from world `ymax`.

Per zone: stroke the rect (solid for `content_aware`, `setLineDash([6, 4])` for `percentage_fallback`), fill at 8% alpha, then draw the badge — a filled rounded rect at the screen top-left corner with the uppercase label in ~10px, suffixed `?` for fallback. Skip any zone whose transformed rect is entirely outside the visible canvas.

The helper takes the whole zones payload, not a pre-filtered list, and returns early drawing nothing if any zone reports `percentage_fallback_no_sheet_bounds` — that value applies to all seven at once (it is set in a single `else` branch covering every key), so it is a whole-payload condition, not a per-zone one. Phase 4 owns the banner that explains why nothing drew.

### 3.3 Redraw wiring

`CanvasRenderer` is `React.memo`'d and its redraw effect has an explicit dependency list. Add `showZones` and `zoneRegions` to it, or toggling produces no visible change until the next pan. This is the single most likely thing to be missed in this phase.

### Phase 3 verification
See the manual checks below.

---

## Phase 4 — Degraded states

There is no "no zones detected" state (see Context) — every degraded case below is about a box that exists but should not be trusted, or should not be drawn at all. Each surfaces as a small inline notice in the canvas header, never a silent no-op and never a thrown error boundary. The notice text names the actual cause; "something went wrong" is useless in a debugging tool.

| Condition | Behavior |
| :--- | :--- |
| Entities not yet extracted (`ENTITIES_NOT_READY`) | Notice: "Zones unavailable — drawing entities not extracted yet." No boxes. |
| Any zone reports `percentage_fallback_no_sheet_bounds` | **No boxes at all.** Notice: "Zone detection found no sheet bounds — all boxes are placeholders and are not shown." This is the case that must never render (decision 5). |
| Some zones `percentage_fallback` | Draw them dashed with `?`. Notice: "N of 7 zones fell back to the percentage grid." Counting them in the header saves squinting at seven badges. |
| Zones response `render_bounds` disagrees with the canvas's current bounds | Draw, plus a **visible** notice — not just a console warning. A bounds mismatch means the boxes and the geometry were computed against different extents, so every box is offset by an unknown amount. That is exactly the class of bug this overlay exists to expose, and burying it in the console defeats the purpose. |
| Fetch failure | Notice with the error text; toggle stays on so retry is one click. |

**Why the last two rows differ, since both are "untrustworthy geometry."** Placeholder boxes carry *zero* information — seven identical rectangles that describe no drawing — so rendering them can only mislead. Bounds-mismatched boxes still carry real relative structure (the title block really is bottom-right of the notes block); they are offset, not meaningless, and seeing the offset is often how you diagnose the mismatch. Draw those, label them loudly. The rule is not "hide anything suspect," it is **never render geometry that contains no information.**

A zone field arriving `null` (not expected — see the `DrawingZonesResponse` docstring) is simply not drawn, with no notice. It is a wire-robustness path, not a real state.

---

## Phase 5 — Tests

### Backend (`tests/test_zone_overlay_endpoint.py`, new)

1. **Reserved keys are filtered.** Feed `extract_dynamic_regions`'s real output shape — including `safe_zones` (list) and `_zone_confidence` (dict) — to `build_zones_response` and assert it validates and that neither reserved key appears as a zone. *This is the regression test for defect 2.* A hand-built dict, no DXF or DB fixture (see Phase 1.2).
2. **Confidence is threaded, all three values.** Percentage fallback surfaces `"percentage_fallback"`; content-aware surfaces `"content_aware"`; a no-sheet-bounds run surfaces `"percentage_fallback_no_sheet_bounds"` on all seven zones. The third assertion is what stops someone "tidying up" the confidence strings into a two-state boolean and silently re-enabling the placeholder boxes.
3. **`ENTITIES_NOT_READY`** when the entity set is empty.
4. **Gemini schema is unpolluted.** *Regression test for defect 1 — it fails loudly if anyone later nests a bare `dict` into the LLM contract, which is the mistake this plan exists to avoid and which costs a production outage on the first request. Worth having regardless of this feature.*

   **Implement it as a structural walk, not a substring search.** The obvious version —
   `assert "additionalProperties" not in json.dumps(PhysicalComparisonResponse.model_json_schema())` —
   **fails on the current, healthy codebase**: the `ComparisonDiagnostics` docstring literally contains the word `additionalProperties` (explaining this very hazard), and Pydantic emits docstrings as `description` strings. Recurse the schema tree and assert no node carries `additionalProperties` as a **key**. Verified: a structural walk over today's schema finds zero such nodes, so the test passes as intended once written correctly.

   Scope caveat, so nobody over-trusts it: this asserts against Pydantic's JSON schema, which the Gemini SDK converts further. It is a proxy for what Gemini receives, not proof of acceptance. It would have caught the original draft's defect, which is enough to justify it — but a green result is not a guarantee the API will accept the schema.

### Frontend (`apps/desktop/src/utils/zoneOverlay.test.ts` or alongside `renderEntities.ts` — colocate with wherever `drawZoneOverlays` lands, per Phase 3.2)

5. **Y-flip.** A known world box under a known normalization + viewport produces the expected screen rect, asserting specifically that world `ymax` maps to the smaller screen Y. *Regression test for the mirroring failure in decision 7.*
6. **Constant apparent size.** Stroke width and badge font are unchanged between a 1× and a 10× viewport scale.
7. **Off-screen cull.** A box fully outside the viewport issues no draw calls.
8. **Placeholder suppression.** A payload where every zone is `(0,0,1000,1000)` / `percentage_fallback_no_sheet_bounds` issues **zero** draw calls. *Regression test for decision 5 — the failure mode is silent and looks like a rendering bug rather than a data problem, so it needs a test rather than a code comment.*

### Verification commands

No `PYTHONPATH` prefix is needed. `pyproject.toml` sets `pythonpath = ["."]` under `[tool.pytest.ini_options]`, so pytest puts the repo root on `sys.path` itself and the `services.backend.…` imports resolve. Run from the repo root:

```bash
services/backend/.venv/Scripts/python.exe -m pytest tests/test_zone_overlay_endpoint.py -v
```

> **Correction to an earlier revision of this document.** It claimed the draft's `$env:PYTHONPATH="…\services\backend"` prefix "makes every import fail at collection." That is false — verified by running collection with exactly that value, which succeeds, because `pythonpath = ["."]` adds the repo root regardless of what the env var says. The prefix is redundant and misleading, not breaking. Recorded rather than quietly deleted, since the wrong claim was stated confidently twice.

The TypeScript check does need care: the draft chained it with `&&` after a PowerShell command, and `&&` is a parser error in PowerShell 5.1 (verified on this machine, 5.1.19041). Either run it in bash, or use `;` in PowerShell. From `apps/desktop`:

```bash
npx tsc --noEmit
```

Note that `tests/test_hybrid_pipeline.py` (the draft's chosen suite) covers reconciliation and would not catch any of the four defects — it is not a useful gate for this work.

### Manual verification

1. Launch the desktop app, open a room with both drawings loaded.
2. Toggle **Zones** on *without* running a comparison — boxes must appear. (If they do not, the endpoint decoupling has been undone somewhere.)
3. Confirm each box sits over the feature it names on both reference and revision, and that the two canvases show *different* boxes where the drawings differ — identical boxes on visibly different sheets means the ref/rev prop wiring is crossed.
4. Confirm any dashed `?` box corresponds to a zone with no semantic anchor in that drawing.
5. Zoom to maximum and pan to a sheet corner: boxes must track the vector geometry with no lag and no drift, and stroke/badge size must not grow. This is the acceptance gate for decision 6 — if boxes lag during drag, the rendering approach is wrong and must not be papered over with a throttle.
6. Confirm the fallback count in the header notice matches the number of dashed `?` badges actually on screen.
7. Toggle off — no residual boxes, no leftover network activity.

The `percentage_fallback_no_sheet_bounds` path is hard to trigger with a real file and is covered by frontend test 8 instead; do not treat "I never saw that banner" as evidence it works.

---

## Out of scope

- Persisting zone boxes into the audit record or PDF report.
- Making zones clickable, selectable, or editable.
- Any change to zone *detection* logic in `zone_detector.py` — this plan only visualizes what is already computed. Bad boxes discovered via this overlay are follow-on work, and finding them is the point.
- Removing the dead `OverlayLayer.tsx` stub or the unused `fetchDrawingScene` client (no consumers today).
- Sub-view boxes from `detect_subviews()` — a plausible follow-on once the seven top-level zones are trusted.

## Noted in passing, not fixed here

`extract_dynamic_regions`'s docstring advertises three detection tiers — content-aware, a "LAYER HEURISTIC (Secondary)" scoring entities by layer-name keywords, and the percentage fallback. The implementation has only two: the percentage grid (`:45-57`) and the content-aware override (`:64-74`). There is no layer-heuristic step, and correspondingly no such value in `_zone_confidence`.

Flagged because anyone debugging *with this overlay* will read that docstring and look for a middle tier that does not exist. Whether the tier was removed or never built is not established here. Fixing the docstring, or building the tier, is separate work.

## Completion log

### Phase 1 — Backend zone endpoint — **done**

`ZoneBBox` and `DrawingZonesResponse` added to `api/schemas.py`; `ZONE_KEYS`, `_to_zone_bbox`, `build_zones_response`, and `GET /drawings/{id}/zones` added to `api/routers/drawings.py`. Tests in `tests/test_zone_overlay_endpoint.py` — 13 passing.

Two things the plan predicted were confirmed empirically against the real detector rather than assumed, and both are now pinned by tests:

- **Reserved keys are real and would have broken a naive mapping.** `extract_dynamic_regions()` on a synthetic A3 sheet returns exactly `{views, notes, bom, title, tolerance, iso, title_upper_left, safe_zones, _zone_confidence}`. `test_real_extract_dynamic_regions_output_maps_cleanly` runs the actual detector, so it also fails if a future change adds another reserved key — the hand-built fixtures in the other tests could not catch that.
- **Decision 5's premise holds exactly as described.** Entities with text but no lines make `compute_drawing_bounds()` return `None`, and all seven zones come back as the literal `(0.0, 0.0, 1000.0, 1000.0)` with `percentage_fallback_no_sheet_bounds`. Frontend suppression in Phase 3/4 keys off that string.

Deviation from the plan, deliberate: `_to_zone_bbox` returns `None` for a malformed tuple instead of raising. The plan said "fails loudly at the boundary," but one bad zone taking out the whole overlay is the wrong trade for a debug view — the other six still carry information, and a missing box is self-evident on screen. `DrawingZonesResponse`'s fields were already `Optional` for exactly this.

**Pre-existing failures, not caused by this work:** `tests/test_vision_ocr_grounding.py::test_orchestrator_falls_back_on_gemini_ocr_failure` and `::test_orchestrator_skips_ocr_when_crop_returns_none` fail with `AttributeError: 'MockEntity' object has no attribute 'layer'`. Verified by stashing the Phase 1 changes and re-running: both still fail. Full suite otherwise 301 passed.

### Phase 2 — Frontend client, store state, toggle — **done**

`ZoneBBox` / `DrawingZonesResponse` / `ZONE_KEYS` mirrored into `services/drawingsApi.ts` with `fetchDrawingZones`; `showZoneBboxes`, `zoneRegions`, `zoneErrors`, `setShowZoneBboxes`, `fetchZoneRegions` added to `ComparisonSlice`; toggle wired into `TwoDWorkspace.tsx`. `npx tsc --noEmit` clean. 11 new tests in `services/zoneRegions.test.ts`.

Two additions beyond the plan, both because Phase 3/4 would otherwise duplicate the logic across two canvas instances:

- **`isPlaceholderOnly()` and `countFallbackZones()` live in the API module, not the renderer.** Decision 5's suppression rule is a property of the payload, not of drawing, so it belongs where the payload is defined and can be unit-tested without a canvas. `countFallbackZones` deliberately counts *any* non-`content_aware` value, including `"unknown"` — defaulting an unrecognized confidence to "trustworthy" would silently present a guess as a measurement, and erring toward the dashed style is the safe direction.
- **`zoneErrors`, keyed by drawing id.** The plan's Phase 4 table calls for notices naming the actual cause, but had nowhere to put the message. `parseOrThrow` already converts the `ENTITIES_NOT_READY` envelope into a thrown `Error` carrying the backend's text, so the cause survives to the UI.

Placement deviation: the toggle went into the existing **View** menu as "Show Zone Boxes", beside "Show Canvas Grid" / "Show Canvas Stats", rather than as a standalone header button. That menu is where `Reset Viewport` actually lives, and it already has the exact icon + label + `Check` idiom for view toggles — a bare button in the header would have been the only one of its kind.

**Not visually verified, deliberately.** The toggle currently changes a boolean and fetches JSON; nothing renders until Phase 3. Standing up the Tauri app, backend, auth, and a populated room to confirm a menu item exists would not test anything `tsc` and the unit tests do not already cover. Visual verification happens in Phase 3, where the manual checks in this plan become meaningful.

**Pre-existing failure, not caused by this work:** `src/pages/workspace/RoomsView.test.tsx` fails on a button background assertion (`expected "rgb(255, 255, 255)"`, got `"var(--bg-sidebar)"`). Verified by stashing the Phase 2 changes and re-running: it still fails. Frontend suite otherwise 74 passed.

### Phase 3 — Canvas rendering — **done (unit-verified; visual check pending)**

`renderZoneOverlays` added to `renderEntities.ts`, called from `CanvasRenderer`'s `renderContent` after entities and pins. 13 tests in `components/review/zoneOverlay.test.ts`. `tsc --noEmit` clean.

**Phase 1's endpoint verified live** against the running backend (port 8080, not 8000) on two real drawings — `M7452A0N01_reference.dxf` and `..._FSRS2_kmti.dxf`. All seven zones returned on both, six `content_aware` and `iso` on `percentage_fallback`, exactly the mixed result Phase 1's verification note said to expect. The two sheets have entirely different coordinate extents (reference spans ~1100 units, revision ~440), which makes decision 8 concrete rather than theoretical: rendering the reference's boxes over the revision would misplace every one of them.

Deviation from Phase 3.1, deliberate: **zones are read from the store inside `CanvasRenderer`, not threaded as props through `DrawingCanvas`.** The plan's reason for props was that `DrawingCanvas` "has no side discriminator" — but `CanvasRenderer` already receives its own `drawing`, so `zoneRegions[drawing.id]` is unambiguous with nothing to derive. This is the same mechanism annotation pins already use one block above (`annotations.filter((a) => a.drawing_id === drawing?.id)`, with a comment noting that coordinates live in the owning drawing's CAD space — the identical concern). Props would have added two more to a 4-prop component and introduced a way to pass the wrong entry.

Two things the plan did not specify, both discovered while reading the renderer:

- **The overlay is excluded from exports (`if (isExport) return`).** `renderContent` is the same path `useComplianceReportExport` drives for PDF report images. Debug geometry must not appear in a customer-facing compliance report. Pinned by a test.
- **The Y-flip question was settled by precedent, not derivation.** The renderer's own `ctx` transform contains no flip; both existing overlays that must align with geometry (`renderViolationReticles`, `renderAnnotationPins`) convert through `worldToScreen` and then self-reset the transform with `setTransform(localDpr, …)`. Zone boxes are CAD-space like annotation coordinates, so they follow the same idiom. Corners are re-normalized with `Math.min/max` after transforming rather than assuming `ymin` is the screen top.

A test-fixture bug worth recording: the zoom-invariance tests initially placed the box mid-sheet, where at 10x it legitimately leaves an 800x600 viewport and the cull correctly suppressed it — the failure was the fixture, not the renderer. They now anchor the box at CAD `y ≈ ymax`, which after the flip is screen top-left, and assert the box is still on screen before comparing stroke widths.

**Not visually verified by me.** The manual checks in this plan — box-over-feature alignment, and no lag or drift during pan at high zoom (the acceptance gate for decision 6) — remain unrun. The user is running them in the Tauri app.

### Phase 4 — Degraded states — **not started**

Nothing consumes `zoneErrors` yet, and there is no header notice. Consequence to be aware of while testing Phase 3: when zones fail to load or detection had no sheet bounds, the overlay draws nothing **and says nothing**. The suppression logic is in place and tested; only the explanatory UI is missing.

_(Append one entry per phase as it lands, per the convention in `docs/hybrid-comparison-engine-implementation-plan.md`.)_
