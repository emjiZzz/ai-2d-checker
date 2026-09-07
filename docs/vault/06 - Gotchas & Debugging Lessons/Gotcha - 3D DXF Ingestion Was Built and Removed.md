---
tags: [gotcha, cad, ingestion, dxf, 3d, frontend, negative-result, removed-feature]
status: removed — the defects below are LIVE again, by decision
cache-version: reverted v43 → v42
date: 2026-08-06
verified-against: 11 corpus DXFs, all reporting has_3d false; eval identical to baseline-v38
---

# Gotcha — 3D DXF Ingestion Was Built and Removed

> [!IMPORTANT] **Read this before adding any 3D DXF support.** It was built once, end to end,
> and removed. This note exists so the next attempt starts from what was measured rather than
> from scratch — and so the four defects listed under "What is broken again" are recognised as
> *known and accepted*, not rediscovered as new findings.

Built 2026-08-06 as phases B1–B3 (backend ingestion) and F1–F3 (a per-pane 2D↔3D toggle in
`TwoDWorkspace`, plus an F1 hotkey). Removed the same day on the user's instruction: the
in-pane mode flip was the wrong surface, and **none of it was ever verified against a drawing
that contains 3D.**

## What was measured, and is worth keeping

- **6 of 11 corpus DXFs run a non-identity paper-space transform** (2–3 viewports each, all on
  an `ICADSX Layout`). The Z-truncation path is therefore live on the majority of real
  drawings, not an edge case.
- **All 11 corpus DXFs report `has_3d: false`** — zero non-zero Z values, zero 3D entity types,
  zero non-standard extrusion vectors, across 4,035 coordinates in model space and every
  paper-space layout. The drawings that carry 3D are not on this machine.
- **The Z fix was provably Z-only.** All 11 DXFs re-parsed under old and new code, full parser
  output serialised with every coordinate truncated to `[x, y]`: byte-identical, 4.9 MB,
  sha256 `1399e0c8…`.
- **`tools/eval.py` cannot validate a parser change.** The eval corpus reads frozen
  `entities.jsonl` payloads and never re-parses a DXF, so it never reaches
  `project_mapped_entity`. It validates the comparison engine and nothing upstream of it. A
  green eval is *not* evidence about ingestion — the parser dump above is what that takes.
  Same family as [[Gotcha - The Corpus Borrowed Its OCR From a Volatile Cache]].

## What is broken again, by decision

The revert restores all four. They are **known**, not undiscovered:

1. **`project_point` drops the third component** (`dxf_parser.py`). Every coordinate on a
   drawing with a paper-space viewport loses its Z at ingestion. Stored geometry therefore has
   *mixed* shape — 2-component for viewport drawings, 3-component for the rest.
2. **`map_any` returns `None` for `3DFACE`, `MESH` and polyface/polymesh `POLYLINE`** — silently,
   with no error and no warning. Exactly the class of defect recorded in
   [[Gotcha - Dropped ELLIPSE & SPLINE Geometry]], which cost 111 ellipses and 46 splines before
   anyone noticed. `map_any` returning `None` is indistinguishable from "no such entity in the
   file".
3. **A polyface `POLYLINE` contributes one phantom `(0,0,0)` point per face**, because
   `map_polyline` reads the mesh's face-record vertices as real geometry. This can pull a
   bounding box to the origin.
4. **LWPOLYLINE flattens to Z = 0** rather than reading `dxf.elevation`. An LWPOLYLINE is planar
   by definition, but that plane is not necessarily the origin plane.

Comparison is unaffected by all four: `COMPARABLE_ENTITY_TYPES` is text + dimension, so the
engine never reads a surface. The cost is confined to anything that wants to *display* or
*measure* 3D content.

## Why it was removed

- **Unverifiable.** The original plan made "ingest a genuine revised DXF" an explicit gate
  before B2/F2 could be called complete. The gate was never met, so the button's enabled state,
  the F1 toggle, camera framing on real extents, and whether real 3D content is `3DFACE`/`MESH`
  (renders) or `3DSOLID` (counted, not rendered) were all still open when it shipped.
- **Wrong surface.** A per-pane mode flip inside a two-pane comparison view trades the thing
  that view exists for. The STEP/glTF workspace behind **Ctrl+2** is the established 3D
  affordance and was left untouched; having two unexplained 3D affordances was itself an open
  item on the removed plan.

## If it is rebuilt

**Get the fixture first.** A real revised DXF settles, and only it can settle, two questions
that determine the whole shape of the work: whether the 3D content is `3DFACE`/`MESH`, plain
non-zero Z on ordinary entities, or ACIS-encoded `3DSOLID`; and whether that geometry sits in
model space or inside a viewport — i.e. whether the Z-truncation fix is on the critical path or
merely a correctness fix alongside it.

Three things learned that survive the removal:

- **`ezdxf` is not an ACIS kernel.** `mesh_from_body` silently omits every curved face and does
  not raise — a bracket with a drilled hole renders as a solid box with the bore missing. In a
  tool whose job is spotting differences, that is a plausible-looking wrong answer. If it is
  ever attempted, validate the mesh bbox and face count against `vertices_from_body` and fall
  back to a non-rendered placeholder on any disagreement.
- **Requesting a STEP export alongside the DXF costs zero new code** — `ThreeDPipeline` → glTF →
  `ThreeDViewer` already works end to end. The DXF stays the artifact being *checked*; the STEP
  is a viewing companion.
- **A 3D view adds a third coordinate convention.** CLAUDE.md constraint 3 already documents two
  spaces with opposite Y directions; CAD is Z-up and three.js is Y-up. That conversion belongs
  in exactly one named place. A mirrored or lain-flat model looks plausible, which is precisely
  how the zone-overlay bug survived — see [[Gotcha - A Reshaped Zone Is Not Its Bounding Box]].

**Rule: a feature gated on a fixture that never arrives is not "nearly done" — it is unverified,
and shipping it puts an unproven surface in front of the user. Either get the fixture or do not
build the feature.**
