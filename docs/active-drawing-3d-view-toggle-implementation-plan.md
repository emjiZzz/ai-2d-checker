# 3D DXF Coordinate Preservation & F1 / UI View Toggle — Implementation Plan

**Feature Title**: Active Drawing 2D ↔ 3D DXF View Toggle (F1 Hotkey & UI Button)
**Target Path**: `docs/active-drawing-3d-view-toggle-implementation-plan.md`
**Status**: Reconciled against the repository, 2026-08-06. **Phases B1 and B3 landed**; B2, F1–F3
outstanding. See §7 for what shipped and what it was measured against.

---

## 📋 Revision Note

The first draft of this plan was written without reading the existing 3D stack. Reconciling it
against the repo moved roughly half the proposed work into "already done" and surfaced two
ingestion defects the plan had not anticipated — one of which is larger than everything the
plan originally described. Section 1 records what was verified; the plan proper starts at
section 3.

**The headline correction:** the plan assumed the problem was *preserving* 3D coordinates.
Coordinates are only half of it. `EntityMapper.map_any` has no branch for any true-3D entity
type, so `3DFACE`, `MESH` and polyface/polymesh `POLYLINE` are dropped at ingestion before
coordinate handling is ever reached. A drawing whose 3D content is solid geometry arrives at
the frontend empty no matter how carefully Z is preserved on the entity types that *are*
mapped.

---

## 1. Verified State of the Repository

### 1.1 Already implemented — removed from the plan

| Original plan item | Actual state |
|---|---|
| Add `_as_xyz` helper | **Exists** — [`entity_mapper.py:105`](../services/backend/infrastructure/cad/entity_mapper.py). Used by ellipse, spline, dimension, text, block, tolerance, leader, multileader. |
| Add `start_3d` / `end_3d` | **Redundant** — `map_line` already stores `[start[0], start[1], start[2]]`. |
| Add `center_3d` | **Redundant** — `map_circle` / `map_arc` already store `center[2]`. |
| Add `points_3d` | **Redundant for POLYLINE** — 3D `POLYLINE` vertices already store `pt[2]`. See §1.2 for the LWPOLYLINE gap. |
| Make `project_mapped_entity` pass 3D keys through untouched | **No change needed.** It is schema-driven off `GEOMETRY_SCHEMA`; any key not listed is untouched by construction. |
| Install `three` / `@react-three/fiber` / `@react-three/drei` | **Installed** — `three ^0.184.0`, `@react-three/fiber ^9.6.1`, `@react-three/drei ^10.7.7`. |
| Build orbit / pan / tilt / zoom, camera framing, lighting | **Exists** in [`ThreeDViewer.tsx`](../apps/desktop/src/components/review/ThreeDViewer.tsx): `OrbitControls` with damping, a bounding-box `CameraFitter`, a four-light rig, a neutral-placeholder error boundary, theme-aware grid, and a telemetry HUD. |

Parallel `*_3d` keys are therefore **not** part of this plan. Adding them would duplicate data
that the existing keys already carry, and would create two sources of truth for the same
coordinate — the failure mode CLAUDE.md constraint 3 already warns about for zone geometry.

### 1.2 Defects found during reconciliation

**D1 — `project_point` truncates Z.** [`dxf_parser.py:47-53`](../services/backend/infrastructure/cad/dxf_parser.py)

```python
def project_point(point: Any) -> list[float]:
    result = transform.project(float(point[0]), float(point[1]), state["index"])
    ...
    return [result.x, result.y]        # ← the third component is dropped
```

Every coordinate on a drawing with a paper-space viewport loses its Z at ingestion. Measured
on the local corpus: **6 of 11 DXFs run a non-identity transform** (2–3 viewports each, all on
an `ICADSX Layout`), so this path is live on the majority of real drawings, not an edge case.
Drawings with no viewports return early from `project_mapped_entity` and keep their Z — which
is why stored geometry currently has *mixed* shape, 2-component for viewport drawings and
3-component for the rest.

That mixed shape is also the safety argument for the fix: every downstream consumer already
tolerates 3-component points, because that is what identity-transform drawings have always
produced. The fix moves the minority shape onto the majority one.

**D2 — every true-3D entity type is dropped at ingestion.** `map_any`
([`entity_mapper.py:864-904`](../services/backend/infrastructure/cad/entity_mapper.py)) routes
`LINE`, `CIRCLE`, `ARC`, `ELLIPSE`, `SPLINE`, `POLYLINE`/`LWPOLYLINE`, `DIMENSION`,
`TOLERANCE`, `LEADER`, `MULTILEADER`, `HATCH`, `TEXT`/`MTEXT`/`ATTRIB`/`ATTDEF` and `INSERT`.
It returns `None` for everything else. A repo-wide search finds **no mention of `3DFACE`,
`MESH`, `3DSOLID`, `POLYFACE` or `SURFACE` anywhere in `infrastructure/cad`.**

This is the same class of defect as the dropped ELLIPSE/SPLINE geometry already recorded in the
vault — an entity type absent from `map_any` disappears silently, with no error and no warning.
That one cost 111 ellipses and 46 splines across the corpus before anyone noticed.

**D3 — `map_polyline` hardcodes Z = 0 for LWPOLYLINE.**
[`entity_mapper.py:357-359`](../services/backend/infrastructure/cad/entity_mapper.py)

```python
if entity.dxftype() == "LWPOLYLINE":
    for p in entity.get_points(format="xy"):
        points.append([p[0], p[1], 0.0])       # ← LWPOLYLINE carries Z in dxf.elevation
```

An LWPOLYLINE is planar by definition, but that plane is not necessarily Z = 0: the entity
stores its height in `dxf.elevation`. Every LWPOLYLINE is currently flattened to the origin
plane.

### 1.3 Structural mismatches with the frontend

- **`CanvasToolbar.tsx` does not exist.** No file matching `*Toolbar*` under `apps/desktop/src`.
  The canvas component is `DrawingCanvas.tsx`, not `CanvasRenderer`.
- **There is no single "active drawing".** `TwoDWorkspace` is a two-pane comparison view inside
  a flexlayout: `OriginalDrawingPanel` (`oldDrawing`, tab "Original Drawing") and
  `KMTIDrawingPanel` (`newDrawing`, tab "KMTI Drawing"). Per the confirmed data profile,
  **the KMTI/revision pane is the one that carries 3D; the Original/reference pane is flat 2D.**
- **Ctrl+2 is already bound** to `setCurrentNav('3d-workspace')` in
  [`useGlobalShortcuts.ts:61`](../apps/desktop/src/hooks/useGlobalShortcuts.ts). F1 is a second,
  differently-scoped 3D affordance, and the two need to stay distinguishable to a user.
- **The existing `ThreeDViewer` cannot render DXF.** It fetches glTF from
  `/api/v1/drawings/{id}/gltf`, produced by `ThreeDPipeline` via gmsh/OCC B-Rep tessellation.
  `extraction_pipeline.py:74` gates that pipeline on `step/stp/iges/igs/icd/sldprt/sldasm`; DXF
  never enters it, and DXF has no B-Rep to tessellate.

### 1.4 Verification gap

**No local DXF fixture exercises any of this.** Scanning all 11 corpus files — 4,035 coordinates
across model space and every paper-space layout — found **zero non-zero Z values, zero 3D entity
types, and zero non-standard extrusion vectors**. The revised drawings that carry 3D are not on
this machine.

Consequences, which the plan is built around:

- D1 and D3 are verifiable **today** with a synthetic fixture (§6.1). No customer file needed.
- D2 and the viewer are **not** verifiable against anything currently available. A real revised
  DXF must be obtained before the viewer can be called working, and §6.3 makes that an explicit
  gate rather than an assumption.

---

## 2. Confirmed Decisions

1. **Data profile** — revised DXFs carry 3D; reference DXFs are flat 2D only.
2. **Approach** — land the coordinate fixes and the client-side viewer together, with the scene
   scaffolding extracted from `ThreeDViewer.tsx` and shared, rather than duplicated.
3. **Toggle scope** — per-pane, acting on the focused pane. The other pane stays in 2D so a
   comparison remains readable.

---

## 3. Backend Changes

### Phase B1 — Preserve Z through projection *(verifiable today)*

**`dxf_parser.py`** — `project_point` keeps the third component. Z is not transformed: a
paper-space viewport is a window onto the XY plane, so it has no Z axis to map into. Z passes
through as the model-space value it already was, and the docstring must say so, because a
reader will otherwise assume it was scaled along with X and Y.

**`entity_mapper.py`** — `map_polyline` reads `dxf.elevation` for LWPOLYLINE instead of `0.0`.

Neither change touches `GEOMETRY_SCHEMA`, the comparison engines, or zone extraction.

### Phase B2 — Ingest true-3D entity types

Add mappers and `GEOMETRY_SCHEMA` entries for the types `map_any` currently drops:

- **`3DFACE`** → `vertices` (`vtx0`–`vtx3`, with the DXF convention that a triangular face
  repeats `vtx3 == vtx2`). Schema: `point_lists`.
- **`MESH`** → `vertices` + `faces` (an index list, *not* coordinates — it must stay out of the
  schema's point keys or projection will corrupt it).
- **Polyface / polymesh `POLYLINE`** → routed by the `is_poly_face_mesh` / `is_polygon_mesh`
  flags, which `map_polyline` currently ignores; both fall through to the flat-vertex path and
  lose their face topology.

**`3DSOLID` is handled separately — see §3.1.** Its geometry is ACIS-encoded and needs its own
tiered treatment rather than a single in/out-of-scope call.

**Comparison must not be affected.** Do not add any new type to `COMPARABLE_ENTITY_TYPES`
(currently text + dimension only). New entity types change entity counts and layer inventories,
which is exactly what CLAUDE.md constraint 2 covers — see §5.

### 3.1 `3DSOLID` — what to do, and what not to

`3DSOLID`, `REGION`, `BODY` and the `SURFACE` family store geometry as embedded ACIS (SAT/SAB)
data, not as coordinates. They are a **viewer-only** concern: `COMPARABLE_ENTITY_TYPES` is text +
dimension, so the comparison engine never reads a solid and the DXF audit MVP cannot be blocked
by any of this. What is at stake is only whether the 3D viewport looks empty.

**Verified capability** (ezdxf 1.4.4, installed): `ezdxf.acis.api` provides `load_dxf`,
`mesh_from_body` and `vertices_from_body`. It is explicitly *not* an ACIS kernel — its own
documentation says tasks beyond "stitching some flat polygonal faces to a polyhedron" are not
possible. All 11 corpus files are `AC1015` (DXF R2000), which is exactly the minimum `load_dxf`
requires, so ACIS loading is available in principle on the files this project actually sees.

| Tier | Action | Works on | Cost |
|---|---|---|---|
| **T0** | Count `3DSOLID`/`REGION`/`BODY` into `metadata.three_d.entity_types` | always | trivial |
| **T1** | Emit a non-renderable placeholder entity carrying the bbox from `vertices_from_body` | always | small |
| **T2** | Tessellate via `mesh_from_body` | flat-faced polyhedra **only** | medium, with a trap |
| **T3** | True tessellation of curved solids | needs an ACIS kernel | not available in-repo |

**For the MVP: do T0 and T1. Stop there.**

**T0 first, because the question is still open.** Nothing on this machine tells us whether the
revised DXFs contain `3DSOLID` at all — they may carry their 3D as `3DFACE`/`MESH`, as 3D
polylines, or simply as non-zero Z on ordinary entities, all of which phases B1/B2 already cover.
T0 makes the first real ingested drawing answer that with data. Building T2 before that is
speculation.

**T1, because silence is the actual defect.** `map_any` currently returns `None` for a solid,
which is indistinguishable from "no such entity in the file" — the D2 failure mode again. A
placeholder record with `renderable: false` plus a bounding box lets the viewport say *"3 solids
present, not rendered"* and draw a wireframe box where each one sits, instead of showing an empty
scene that reads as a broken feature.

> [!WARNING]
> **The T2 trap, if it is ever attempted.** `mesh_from_body` returns meshes built from flat
> polygonal faces and **silently omits every curved one — it does not raise.** A bracket with a
> drilled hole therefore renders as a solid box with the bore missing, and a filleted edge
> renders square. That is a plausible-looking wrong answer in a tool whose entire job is
> spotting differences between two drawings, and it is the exact failure class this repo keeps
> paying for. If T2 is ever built, it must **validate before it renders**: compare the mesh
> bounding box and face count against `vertices_from_body`, and on any disagreement beyond
> tolerance fall back to the T1 placeholder rather than drawing a partial solid.

**T3 has no in-repo path.** ACIS is Spatial Corp proprietary; OpenCASCADE — the kernel already
shipped here via gmsh for STEP — has no ACIS reader, so `ThreeDPipeline` cannot be pointed at
this. The realistic options, should real fixtures show curved solids, are:

1. **Request a STEP export alongside the DXF.** The repo already supports STEP end-to-end —
   `ThreeDPipeline` → glTF → `ThreeDViewer` — for **zero new code**. The DXF stays the artifact
   being *checked*; the STEP is only a viewing companion. This keeps the MVP DXF-first and is
   dramatically cheaper than every alternative.
2. A commercial ACIS-capable converter (ODA with its modeler, CAD Exchanger, Datakit). A
   licensing and procurement decision, not an engineering one.

### Phase B3 — Report 3D content in metadata

Extraction emits a summary so the frontend can gate the toggle instead of guessing:

```
metadata.three_d = {
  "has_3d":         bool,     # any non-zero Z, or any 3D entity type present
  "nonzero_z":      int,      # count of non-zero Z coordinates
  "z_range":        [min, max],
  "entity_types":   {"3DFACE": 128, ...},
}
```

This is what makes "the reference pane is flat" a *rendered* fact rather than a documented
assumption — the 3D button disables itself on any drawing that has nothing to show, with a
tooltip saying why. It also answers §1.4 permanently: the first real revised DXF ingested
reports its own 3D profile.

**Constraint check (CLAUDE.md #1):** `metadata.three_d` is a fixed-field object on the
extraction record. It must not be added to `PhysicalComparisonResponse` or anything nested in
it — `entity_types` is an open-ended map and would emit the `additionalProperties` that Gemini
rejects on every request.

---

## 4. Frontend Changes

### Phase F1 — Extract the shared scene layer

Pull out of [`ThreeDViewer.tsx`](../apps/desktop/src/components/review/ThreeDViewer.tsx) into a
new `ThreeDScene.tsx`: `CameraFitter`, the error boundary, the lighting rig, the `OrbitControls`
configuration, and the theme-aware `Grid`. `ThreeDViewer` keeps only its glTF loading and HUD.

This is the reconciliation the task called for: one scene layer, two data sources (glTF meshes
from STEP; line geometry from DXF). Refactor-only, no behaviour change — the existing 3D
workspace must look identical afterwards.

### Phase F2 — `DxfThreeDViewer.tsx`

Renders the entity geometry the 2D canvas already receives — no second fetch, no new endpoint.

- `LINE` → segment pairs; `POLYLINE`/`LWPOLYLINE`/`SPLINE`/`ELLIPSE` → consecutive point pairs.
  All batched into **one** `BufferGeometry` per colour, drawn as `LineSegments`. Per-entity
  objects would put thousands of draw calls in the render loop.
- `3DFACE` / `MESH` → indexed `BufferGeometry`, shaded, with a wireframe overlay toggle.
- Reuses `ThreeDScene` for everything else.

**Coordinate handling — read before writing any of this.** CLAUDE.md constraint 3 documents two
coordinate spaces with opposite Y directions. This adds a third convention: CAD is Z-up, three.js
is Y-up. The conversion belongs in **one** place in this component, named and commented, and it
must not be applied anywhere else. A mirrored or lain-flat model looks plausible, which is
precisely how the existing zone-overlay bug survived.

### Phase F3 — Per-pane toggle and F1

- **State**: `viewMode: { old: '2d' | '3d', new: '2d' | '3d' }` on `reviewStore`, alongside the
  other view toggles (`showMinimap`, `showGrid`, `renderMode`). Not `workspaceStore` — the
  precedent there is state keyed by drawing id, which this is not.
- **Button**: in each pane's own header, labelled strictly **"2D"** / **"3D"**. Disabled with an
  explanatory tooltip when `metadata.three_d.has_3d` is false — which is the normal, expected
  state for the reference pane.
- **F1**: added to `useGlobalShortcuts`, resolving the focused pane from the flexlayout model's
  active tabset (`originalCanvas` | `kmtiCanvas`). `preventDefault()` to suppress the help key.

> [!WARNING]
> **F1 goes in `useGlobalShortcuts` and nowhere else.** That hook is mounted exactly once, from
> `App.tsx`. `TwoDWorkspace` renders `DrawingCanvas` **twice**, so a `window` listener added in a
> per-pane hook is installed twice and fires twice per keypress — which for a *toggle* means F1
> flips the mode and immediately flips it back, presenting as a dead key rather than as an
> error. This is a bug the project has already paid for once: see
> [[Gotcha - A Window Listener in a Per-Pane Hook Fires Once Per Pane]], where the identical
> wiring made Ctrl+Z undo two actions per press.

---

## 5. Cache & Vault Obligations

**Bump `COMPARISON_CACHE_VERSION` in `cache_manager.py` — required for Phase B2.** New entity
types change entity counts and layer inventories, which feed zone extraction. Cached audits are
served in ~0.14 s from `storage/cache/` and would silently bypass the change. Add the one-line
`# vN:` note. (CLAUDE.md constraint 2.)

For **B1 and B3 alone** the bump is a judgement call: preserving a third component and adding a
metadata field should not alter any comparison result, since every consumer slices `[0]` and
`[1]`. Verify that claim by running the eval corpus before and after (§6.2) rather than assuming
it — and if the run is not clean, bump.

**Vault notes to write** (CLAUDE.md constraint 4), linked from the MOC:

- *Gotcha — Z Is Truncated by the Paper-Space Projection.* Covers D1: why the transform is
  legitimately 2D, why dropping the third component was the wrong way to express that, and the
  mixed-shape stored data it produced.
- *Gotcha — An Entity Type Absent From `map_any` Is Dropped Silently.* Covers D2, generalising
  the existing dropped-ELLIPSE/SPLINE note into the rule: adding a mapper is not optional
  polish, and `map_any` returning `None` is indistinguishable from "no such entity in the file".

**AI Maturity Status** (constraint 5) needs **no** update: this is CAD ingestion and desktop UI,
it crosses no rung boundary, and it touches neither the comparison engines nor retrieval. Adding
a work-log entry for it would dilute the ledger.

---

## 6. Verification

### 6.1 Automated — available today

New `tests/test_dxf_3d_coordinates.py`, built on a **synthetic** DXF (a handful of entities at
known non-zero Z, inside a paper-space layout with a viewport, since the identity path returns
early and would not exercise D1 at all):

1. Z survives `project_mapped_entity` on a viewport drawing, at its model-space value.
2. Projected X/Y are **unchanged** from the current implementation — the fix must be provably
   Z-only. This is the regression test that matters.
3. LWPOLYLINE `elevation` reaches `geometry.points`.
4. Per phase B2: a `3DFACE` survives `map_any` and its four vertices keep their Z.
5. `metadata.three_d.has_3d` is false for a flat drawing and true for the synthetic one.

Existing suites must stay green:

```bash
services/backend/.venv/Scripts/python.exe -m pytest tests/ -q
```

```bash
npx vitest run
```

```bash
npx tsc --noEmit
```

Known pre-existing failures, not to be chased: `tests/test_vision_ocr_grounding.py` (2, `MockEntity`
lacks `layer`) and `RoomsView.test.tsx` (1, asserts a literal colour now behind a CSS variable).

### 6.2 Comparison regression

Run `tools/eval.py` over the 54-pair corpus before and after the backend changes. The v38
baseline at `tests/fixtures/eval/baseline-v38.json` is precision 0.85 / recall 0.68 / F1 0.76
with 0 false positives across 23 zero-finding pairs. **Any movement in those numbers means the
"3D is purely additive" claim is false** and the change needs re-examining, not a baseline
rewrite.

### 6.3 Gate — real fixture required

Phases B2 and F2 **cannot be signed off against anything currently in the repo** (§1.4). Before
either is called complete, at least one genuine revised DXF must be ingested and its
`metadata.three_d` recorded here. Two specific things that fixture, and only that fixture, can
settle:

- Whether the 3D content is `3DFACE`/`MESH` (phase B2 renders it), plain non-zero Z on ordinary
  entities (phase B1 alone suffices), or `3DSOLID` (§3.1 — and if so, whether flat-faced).
- Whether the 3D geometry sits in model space or inside a viewport — i.e. whether D1 is on the
  critical path for the viewer or merely a correctness fix alongside it.

Until then, F2 is demonstrable only against the synthetic fixture. Reporting it as working on
real drawings before that point would be exactly the unevidenced claim CLAUDE.md constraint 5
calls a defect.

### 6.4 Manual

1. Backend `./start.ps1` (port **8080**, not 8000); desktop dev server on 1420.
2. Load a reference/revision pair. The reference pane's 3D button is disabled with a tooltip;
   the revision pane's is enabled.
3. F1 with the revision pane focused switches that pane to 3D and its label to "2D". **The
   reference pane stays in 2D.**
4. Orbit, tilt, zoom. Confirm the model is not mirrored and not lying flat (§4 F2).
5. F1 again returns to 2D with layer toggles, zone overlays and checklist selection intact.
6. F1 with the reference pane focused does nothing, and says nothing alarming.
7. Run a full comparison in the 2D view and confirm the findings match a pre-change run.

---

## 7. Work Log

### 2026-08-06 — Phases B1 and B3 landed

**Changed**

- `dxf_parser.project_point` carries the third component through, unscaled, preserving arity.
- `entity_mapper.map_polyline` reads `dxf.elevation` for LWPOLYLINE instead of hardcoding `0.0`.
- `dxf_parser.summarize_three_d` + `UNMAPPED_3D_TYPES`; `metadata.three_d` now reports
  `has_3d` / `renderable` / `nonzero_z` / `z_range` / `entity_types` / `unmapped_types`, and
  ingestion logs a warning naming any 3D entities `map_any` dropped.
- `tests/test_dxf_3d_coordinates.py` — 14 tests, all passing.

**Measured, not assumed**

- All 11 corpus DXFs re-parsed under old and new code. Full parser output serialised with every
  coordinate truncated to `[x, y]`: **byte-identical**, 4.9 MB, sha256 `1399e0c8…`. This
  exercises the projection on all 6 viewport drawings, so the change is provably Z-only.
- Paper-space drawings now store 3-component coordinates where they previously stored none —
  e.g. `fresh_test_drawing.dxf` went from 0 to 1719 — while genuinely-2D values (`bbox`, hatch
  loops, ellipse/spline tessellations) correctly stayed 2-component.
- `tools/eval.py --method rag --provenance mutation`: identical before and after. **Caveat
  worth carrying forward:** the eval corpus reads frozen `entities.jsonl` payloads and does not
  re-parse DXFs, so it never touches `project_mapped_entity`. It validates the comparison
  engine; the parser dump above is what validates the fix.
- Full suite: only the two documented pre-existing `test_vision_ocr_grounding.py` failures.

**Cache version: not bumped.** `COMPARISON_CACHE_VERSION` stays at **v42** (§5 anticipated a
judgement call here; the byte-identical dump settles it). Keys are `drawing_id + file_hash`, the
files are unchanged, so existing entries still hit — harmless, because the 2D output they cache
is provably unchanged. Phase B2 **will** need the bump: new entity types change entity counts.

**Vault:** [[Gotcha - Z Was Truncated by the Paper-Space Projection]], linked from the MOC.
No `AI Maturity Status` entry — no rung boundary crossed, per §5.

**Still true after this work:** every corpus drawing reports `has_3d: false`, correctly. Nothing
here has been exercised against a drawing that actually contains 3D. §6.3 remains the gate.

## 8. Open Items

1. **Fixture acquisition** — §6.3. The binding constraint on B2 and F2.
2. **`3DSOLID`** — §3.1. T0/T1 are in scope and unconditional; T2/T3 are decisions deferred until
   a real fixture shows whether solids are present at all, and if so whether they are flat-faced.
3. **Two 3D affordances** — Ctrl+2 opens the STEP/glTF workspace; F1 flips a DXF pane in place.
   Both are 3D, and nothing currently explains the difference to a user. Worth a label change,
   but not blocking.
