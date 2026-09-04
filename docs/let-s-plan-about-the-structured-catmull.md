# Architecture Roadmap — AI 2D Checker

## Context

The stated concern was: *"the system uses ingestion to gather CAD data but displays PNG on the frontend, so we can't touch CAD drawings."*

**That premise is half wrong, and the half that's wrong is the good half.** Full entity-level CAD data is already extracted and persisted. The PNG is a *display* decision, not a data ceiling. What's actually missing is (a) enough fidelity in the extracted entity model to render or write CAD, and (b) a coordinate contract that survives a round trip.

The chosen direction is three-fold:
1. **Better AI revision comparison** — ground the diff on CAD entities instead of PNG vision.
2. **Write findings back into CAD** — redline layer exported as DXF/DWG.
3. **Full vector rendering** on the frontend — drop the PNG.

All three depend on the *same* foundation, which does not exist yet. This document defines that foundation and sequences the work.

---

## What exists today

| Capability | Status |
|---|---|
| DXF/DWG/PDF/STEP/IGES/SLDPRT ingestion | Working. `services/backend/infrastructure/cad/extraction_pipeline.py` |
| Entity extraction to Mongo | Working. `extracted_entities` collection — 13 entity types with layer, handle, color, text, bbox |
| Vector geometry API | Working. `GET /drawings/{id}/layers` → `infrastructure/rendering/geometry_serializer.py` |
| PNG render (matplotlib + ezdxf) | Working, high quality, solves SHX/CJK fonts |
| Client vector renderer | Exists but **disabled** — `renderEntities.ts:129` sets `skipEntities = true` whenever a PNG is present |
| AI comparison (Gemini) | Working, 4 modes. Grounded on **PNG pixels** + normalized 0–1000 `visual_bbox` |
| Annotations CRUD | Working. `api/routers/annotations.py` |
| CAD writeback | **Does not exist** |
| Rules engine | **Does not exist** — "audit" is freeform LLM prose in 6 fixed categories |

---

## The three real blockers

These are the actual reasons the PNG can't be dropped and CAD can't be written. Each is a data-model defect, not a rendering defect.

### Blocker 1 — The entity model is lossy in ways that matter

`infrastructure/cad/entity_mapper.py` extracts enough to *describe* an entity but not enough to *draw* or *reproduce* it:

- **`map_dimension`** stores only `def_point` and `text_point`. No extension lines, dimension line, arrowheads, or `dimstyle`. A dimension is unrenderable and un-writable from stored data.
- **`map_hatch`** stores `edge.start` only, capped at 20 points — no closed boundary, no pattern geometry. Unfillable.
- **No lineweight is extracted by any mapper**, yet `geometry_serializer.py:43` reads `properties.get("lineweight", 1.0)`. Every stroke is therefore width 1.0.
- **No linetype is extracted by any mapper**, yet `geometry_serializer.py:55` checks `properties.get("linetype")`. Dashes never apply — **hidden lines and centre lines render as solid**. On a mechanical drawing that is a semantic error, not a cosmetic one.
- **`map_arc`/`map_circle`** put `radius` in `properties`, but the paperspace projector writes the scaled radius into `geometry`. Two sources of truth.
- **`map_block` + explosion double-counts.** `dxf_parser.py:145-152` explodes an INSERT via `virtual_entities()` *and then* maps the INSERT itself. Both land in Mongo. The PNG hides this; a vector renderer would draw block content twice.

### Blocker 2 — The coordinate space is a one-way, partially-applied projection

`dxf_parser.py:99-235` projects model-space geometry through the active paper-space VIEWPORT into paper coordinates. Two consequences:

- **It is not invertible.** The per-entity `scale` is computed and then discarded — never persisted. There is no stored transform to map a paper-space annotation back into the source file's model space. **This blocks CAD writeback directly.**
- **It is applied inconsistently.** The `elif` chain covers line, circle/arc, polyline, text, dimension. It does **not** cover `hatch`, `tolerance`, `leader`, `multileader`, or `block`. Those five stay in model space while everything else moves to paper space. The PNG masks this today; full vector rendering exposes it as scattered, wildly misplaced geometry.

### Blocker 3 — Annotation coordinates have no provenance

`AnnotationDocument.coordinates` is a bare `[x, y]`. No units, no `render_bounds` snapshot, no layout name, no transform version. If a re-render picks a different layout as the render target, `render_bounds` changes and **every existing pin silently moves**. This is a latent data-integrity bug today and an outright blocker for writeback.

---

## Target architecture

The unifying idea: **make the extracted entity model a faithful, invertible, self-describing representation of the source drawing**, then let rendering, AI grounding, and writeback all consume it.

```
                    ┌────────────────────────────────────┐
   DXF/DWG/PDF ───► │  Ingestion                         │
                    │  • full entity attrs (lw, ltype,   │
                    │    dimstyle, hatch boundary)       │
                    │  • model-space geometry preserved  │
                    │  • explicit stored transform       │
                    └──────────────┬─────────────────────┘
                                   │
                    ┌──────────────▼─────────────────────┐
                    │  Drawing Model (Mongo)             │
                    │  entities + DrawingTransform doc   │
                    │  (model↔paper↔render, invertible)  │
                    └──┬──────────┬──────────┬───────────┘
                       │          │          │
         ┌─────────────▼──┐  ┌────▼───────┐  ▼──────────────────┐
         │ Vector render  │  │ AI compare │  │ CAD writeback     │
         │ (client)       │  │ entity-    │  │ redline layer →   │
         │ scene-graph +  │  │ grounded,  │  │ DXF (ezdxf) →     │
         │ tiled fetch    │  │ handle IDs │  │ DWG (ODA)         │
         └────────────────┘  └────────────┘  └───────────────────┘
```

### Key architectural decisions

**A. Preserve model space; store the transform, don't bake it.**
Entities keep original model-space coordinates. A new `DrawingTransform` record (per drawing, per layout/viewport) stores `{layout, viewport_id, center, view_center, scale, offset}`. Projection becomes a pure function applied at render/query time, and its inverse becomes available for writeback. This also fixes Blocker 2's inconsistency by making projection a single code path rather than five hand-written `elif` branches.

**B. Coordinates become typed, not bare arrays.**
Introduce a `CadPoint` envelope: `{space: "model"|"paper"|"render", layout, x, y, transform_version}`. Applies to `AnnotationDocument.coordinates`, `CanvasMarking.coordinates`, and violation anchors. Migration writes `space: "render"` + the current `render_bounds` onto existing records so nothing silently moves.

**C. Entity handles become the AI's addressing scheme.**
The comparison prompt already asks for `visual_bbox` in 0–1000 space and then back-projects — which is why `full_ai/coordinate_resolver.py` needs hallucination guardrails, fuzzy text matching, and 5 mm spatial dedup. Replace that: send the model a **structured entity manifest** (handle, type, layer, text/measurement, bbox) alongside the images, and require findings to cite `handle`. `visual_bbox` degrades to a fallback for genuinely unaddressable visual findings. Most of `coordinate_resolver.py` can then be deleted rather than extended.

**D. Rendering: vector scene-graph, PNG demoted to fallback.**
Client builds a display list from a **render-ready** payload (a new endpoint, not today's raw `/layers`) where the backend has already resolved lineweight/linetype/color-by-layer and tessellated dimensions and hatches into drawable primitives. This keeps the client renderer simple and keeps CAD semantics on the Python side where `ezdxf` lives. PNG stays available for export/print and as a degradation path.

**E. Writeback via ezdxf on the original upload — never through the entity model.**
`ezdxf` is already a dependency and can write. Source DXFs persist at `storage/uploads/<sha256>.dxf`. For DWG the ODA-converted DXF is currently deleted after parse — it must be retained.

The critical property: **writeback opens the original file, adds one layer, and saves.** It never reconstructs the drawing from `extracted_entities`. Everything the extraction drops — lineweights, hatch patterns, dimstyles, xrefs, proprietary objects — survives because it is never touched. Consequently Phase 5 depends on Phase 1's **invertible transform only**, not on the richer entity attributes.

**F. Text fidelity is a substitution choice, not a fidelity cliff.**
SHX and BigFont are *stroke* fonts — glyphs defined as pen paths, not outlines — and cannot be reproduced by any TTF, in a browser or otherwise. The current PNG path does not render them either: `rendering/dxf_background_renderer.py` **substitutes** `msgothic.ttc` for `TXT.SHX`, `GOTHICJ`, `EXTFONT2`, `ROMANS`, `SIMPLEX`. So the vector path is not choosing between fidelity and a gap — both paths substitute. The real problem is *placement*, not glyph shape: TTF advance widths differ from SHX, so text can overflow title-block cells. Solved by fitting to the stored per-entity `bbox`.

---

## Phases

### Phase 1 — Foundation: entity model + transform *(prerequisite for everything else)*
- Extend `entity_mapper.py`: lineweight, linetype, true-color, ltscale, transparency; dimension geometry (`dimstyle`, extension/dimension line points, arrowheads); closed hatch boundaries with arc edges.
- **Make text `bbox` a first-class field.** Today it is computed inside a bare `try/except: pass` (`entity_mapper.py:168-176`) and is silently `None` on failure. Phase 3's text placement depends on it — give it an explicit metrics-derived fallback (height × char-count estimate) rather than absence.
- Stop double-storing exploded blocks — store either the INSERT or its virtual entities, with a parent-handle link, not both.
- Extract projection into a `ViewportTransform` class; persist it; apply as one code path over all entity types.
- Add a `transform_version` / schema version to `DrawingDocument` so stale extractions are detectable.
- **No backfill.** Existing drawings are test data and will be wiped (decided 2026-07-27). Phase 1 can change the extraction schema freely — no migration job, no dual-read compatibility shim. Still add `transform_version` so *future* schema changes are detectable, but nothing needs to read an old value.

*Files:* `infrastructure/cad/entity_mapper.py`, `dxf_parser.py`, new `infrastructure/cad/viewport_transform.py`, `domain/models/extracted_entity.py`, `domain/models/drawing_document.py`

### Phase 2 — Coordinate contract
- `CadPoint` envelope in `packages/types` and `api/schemas.py`.
- Change `AnnotationDocument.coordinates` and violation anchors to the typed envelope outright. **No migration or backfill** — existing annotations belong to test drawings being wiped. This makes Phase 2 substantially smaller than originally scoped: a type change, not a data migration.
- Rewrite `apps/desktop/src/utils/coordinateTransform.ts` around the typed envelope. Its header comment already documents 7 call sites, two of which (ROI %-space, laser sign-inversion) deliberately deviate — the typed envelope is what makes those deviations explicit instead of load-bearing comments.

### Phase 3 — Full vector rendering
- New `GET /drawings/{id}/scene` returning resolved, render-ready primitives; paginated or tiled by bbox (a dense DXF is tens of thousands of entities — today's `/layers` serialises all of them into one JSON response).
- Client scene-graph renderer replacing `renderEntities.ts`'s 4-primitive path: dimensions, hatch fills, GD&T frames, leaders, blocks, dashed linetypes, lineweight scaling.
- Entity-level hit-testing and selection — the capability that actually unlocks "click a dimension, see the finding".
- **Text rendering** (see decision F): bundle Noto Sans JP, draw with canvas `fillText`, and horizontally scale each string to fit its stored `bbox`. The extracted text content is already correct — the `latin-1 → cp932` transcode in `dxf_parser.py:373-394` is the hard part and it is done. Accept a documented glyph-shape gap vs. SHX; matching is not achievable and is not a goal.
- Retire the unused `pixi.js` / `@pixi/react` dependencies or actually adopt them; don't leave them installed and unimported.

*Precursor spike (half a day, before the rest of Phase 3):* render one real Japanese customer drawing's title block as vector text and compare against its PNG. This is **calibration, not a go/no-go gate** — it sizes the placement work and validates the `bbox` fit approach.

### Phase 4 — Entity-grounded AI comparison
- **Build the entity manifest as a reusable queryable index**, not a one-off helper inside `prompt_builder.py`. It should support filtering by layer, entity type, region bbox, and text pattern. A future rules engine is essentially "run predicates over that index" — getting the shape right here costs almost nothing and avoids a rewrite. See decision 4 below.
- Manifest feeds `full_ai/prompt_builder.py` alongside the images.
- Response schema requires `handle` (ref and rev) per finding; `visual_bbox` becomes optional fallback.
- Retire the bulk of `full_ai/coordinate_resolver.py` — fuzzy text search, hallucination auto-correction, spatial dedup — as the grounding makes them unnecessary.
- Bump `COMPARISON_CACHE_VERSION`; the existing three-lever cache versioning in `comparison/cache_manager.py` handles invalidation cleanly.

### Phase 5 — CAD writeback *(needs only `ViewportTransform`, not the full Phase 1 entity work)*
- Retain ODA-converted DXFs instead of unlinking them after parse.
- Redline writer: findings + annotations → `AI_REDLINE_<session>` layer (clouds, leaders, MTEXT notes), inverse-transformed to model space via the Phase 1 transform.
- Open the original, add the layer, save a copy. Never mutate original geometry and never rebuild the drawing from `extracted_entities` (see decision E).
- **`GET /audits/{session}/redline.dxf` first**, verified end-to-end; **then** `.dwg` as a trailing step via the existing ODA converter with the output format flag reversed. Not an either/or — DWG is a format flag on a subprocess already trusted on the read path (`infrastructure/cad/oda_converter.py`), and customers work in DWG, so DXF-only would leave manual conversion in the real workflow for no meaningful saving.

### Phase 6 — Cleanup (can run in parallel throughout)
Real rot found during exploration, each independently actionable:
- `infrastructure/cad/pdf_parser.py:162-183` **fabricates 120 fake lines and 40 fake text entities** when PyMuPDF is unavailable, and persists them to Mongo indistinguishable from real data. Should fail loudly.
- `infrastructure/cad/three_d_pipeline.py:423-426` fabricates `volume_mm3`/`surface_area_mm2` from `face_count` when gmsh returns 0.
- `stores/threeDStore.ts:126-156` — 3D audit is a hardcoded mock returning score 85 and two canned violations.
- Default credentials `admin/admin123` seeded unconditionally on every DB connect (`infrastructure/database/connection.py:73-93`); `services/backend/storage/secure/.api-token` is committed to git.
- `TwoDWorkspace.tsx` writes layout to a `-v10-` localStorage key but reads `-v11-`; user layout changes are never restored.
- Manually-added canvas markers (`custom_marker_*`) exist only in Zustand and are never persisted.
- The entire `components/copilot/` subsystem is built and unmounted — decide: adopt or delete.

---

## Sequencing constraint

Phases 3, 4 and 5 are independent of each other. Their dependencies on the foundation differ in strength:

| Phase | Needs | Can start when |
|---|---|---|
| 3 — Vector rendering | Full Phase 1 (entity attrs + transform) **and** Phase 2 | Both foundations complete |
| 4 — Entity-grounded AI | Phase 1 handles + Phase 2 coordinate envelope | Both foundations complete |
| 5 — CAD writeback | **`ViewportTransform` only** | As soon as the transform lands — earlier than the rest of Phase 1 |

Attempting full vector rendering before Phase 1 will surface the five unprojected entity types (hatch, tolerance, leader, multileader, block) as visibly broken geometry. Attempting writeback before the transform exists is impossible because the projection cannot be inverted — but writeback does *not* need the richer entity attributes, so it is the earliest of the three to unblock.

---

## Decisions — all resolved 2026-07-27

1. **Backfill vs. forward-only → forward-only.** Existing drawings are test data and will be deleted. No migration, no compatibility shims anywhere in Phases 1–2. Wipe the `ai_2d_checker` database rather than deleting via the API — `DELETE /drawings/{id}` cleans up the upload, PNG and glTF but leaves `extracted_entities`, `annotations` and `audit_sessions` orphaned. The seeder in `infrastructure/database/connection.py` recreates users and clients on next connect.

2. **CJK vector text → accept a documented fidelity gap.** Matching SHX is not achievable by any TTF path, and the PNG baseline is itself a font substitution, so there is nothing to match. Reframed as a placement problem (fit to `bbox`), which is tractable. Not a blocker; de-risk with the Phase 3 precursor spike. See decision F.

3. **Writeback target → DXF first, DWG as a trailing step.** Not either/or. Writeback correctness lives in the `ezdxf` layer; DWG is a format flag on an already-trusted subprocess. See Phase 5.

4. **Rules engine → stays deferred, substrate gets built.** Which standards, whose interpretation, and per-client rule sets are product decisions, not engineering ones, and three concurrent workstreams is already enough. But Phase 4 builds the entity manifest as a queryable index so the engine has a foundation when it is picked up.

   Note it would not start from zero: `SpatialDiffer`, `BOMAnalyzer`, the title-block extractor, and `apply_deterministic_overrides` in `comparison/full_ai/result_parser.py` are already deterministic checks that override Gemini's output. A rules engine generalizes that existing layer rather than replacing it.

**Net effect of decisions 2–4:** Phase 3's risk drops (its fidelity goal becomes achievable rather than impossible), Phase 5 can start earlier (transform only), and Phase 4 gains one small design constraint that keeps the rules-engine door open.

---

## Verification approach

Roadmap-level; per-phase detail to be planned when each phase is picked up.

- **Phase 1:** golden-file tests over a fixture set of real customer DXFs (JP title blocks, paper-space viewports, blocks, hatches) asserting entity counts by type, lineweight/linetype presence, and — critically — that `transform.inverse(transform.apply(p)) ≈ p` for every entity type.
- **Phase 2:** no migration test needed (forward-only). Instead: round-trip test asserting a `CadPoint` placed on the canvas, persisted, reloaded, and re-projected lands on the same screen pixel.
- **Phase 3:** visual regression — vector render vs. current PNG for the fixture set, reviewed by eye. Judge on *geometry and placement*, not glyph shapes; text differences are expected by decision 2. Assert no string overflows its `bbox`. Plus the existing Playwright suite in `apps/desktop/e2e`.
- **Phase 4:** replay cached Gemini comparisons from `storage/cache/`; assert findings resolve to entity handles and compare finding counts against the current pipeline to detect regressions in recall.
- **Phase 5:** write a redline DXF, re-ingest it through the system's own pipeline, and assert the redline entities land within tolerance of the original finding coordinates. Separately assert the output is a **superset** of the input — every original handle still present — proving the add-a-layer approach never drops content. Repeat once through the DWG round-trip.
