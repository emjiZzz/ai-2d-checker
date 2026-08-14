---
title: ADR-011 Vector as the Only Render Path
type: adr
tags: [adr, architecture, rendering, canvas, vector, raster, frontend, cad]
status: accepted
date: 2026-08-11
supersedes: none
amends: none
related: [ADR-006 Removing the Three AI Comparison Methods, Gotcha - A Blurry CAD Canvas and Its Four Causes, Gotcha - Clipped Model Geometry Still Gets a Coordinate, Gotcha - Wrapped Elliptical Arcs Were Tessellated Backwards, CanvasRenderer & Entity Drawing]
---

# ADR-011 — Vector is the only render path; `renderMode` is deleted

**Status:** accepted · **Date:** 2026-08-11

Evidence: `tools/render_audit.py` on `M745221N01_FSRS2_KMTI.DXF` — census **497/518**,
`|dx|` median 0.115 / max 1.40, `width_ratio` median 1.022, rotation lost 0.

---

## Context

The direction was set on **2026-07-27**: full vector rendering on the frontend, with the PNG
display path dropped entirely. A hybrid PNG-plus-pick-layer option was offered at the same time
and **explicitly declined**.

It did not land for two and a half weeks, and the delay was earned. Two attempts to flip the
default were made and reverted:

1. The first switched `renderMode` to `'vector'` **without running it**. Every DIMENSION vanished
   (`VIRTUALIZED: 356/518`), because a DIMENSION stores only anchors and a dimstyle — its drawable
   geometry lives in an anonymous block nothing was flattening.
2. The second landed on a correct diagnosis with passing types and a green suite, and still
   deleted geometry. That is where lesson 10 in [[Gotcha - A Blurry CAD Canvas and Its Four Causes]]
   comes from: *do not ship a default flip you cannot run.*

What changed between then and now is not confidence — it is **measurement**. `render_audit.py`
renders the same layout through ezdxf's `Recorder` backend and compares every string's placement
against the canvas's own branch table, offline, with no backend and no MongoDB. Six placement
defects were found and fixed against it, and three more were rejected as negative results.

## Decision

**The canvas draws vectors, always.** `renderMode` is removed from `reviewStore` — not set to
`'vector'`, removed. With it go:

- the `drawImage` background composite and the mipmap selector in `renderEntities.ts`
- the `/api/v1/drawings/{id}/rendering` fetch, the halving mipmap chain, and the chunked
  per-pixel light-theme recolour in `DrawingCanvas.tsx` (~175 lines)
- the "Ingesting CAD Geometry…" overlay, which existed only to cover that download
- the `PenTool` view-menu toggle
- the `hybrid` mode, which closes out the option declined on 2026-07-27
- `GET /drawings/{id}/rendering`, whose only client was the canvas

## What deliberately did *not* change

**The backend still renders the PNG on every upload.** `render_dxf_background` stays exactly as
it is. This is not hesitation — it is a hard dependency, and anyone reading "drop the PNG
entirely" should stop here:

`metadata["render_bounds"]` is produced by **matplotlib's autoscale**
(`dxf_background_renderer.py:83-86`), and it is load-bearing well beyond the canvas:

| Consumer | Why it matters |
|---|---|
| Zone templates | stored as *fractions of* `render_bounds`; `zone_signature()` derives the template's **identity** from it |
| `SpatialDiffer` | matches in a frame normalised by each drawing's `render_bounds` (cache lever v12) |
| `coordinate_stamp` / `CadPoint` | drift detection compares against it — and `cad_point.py:6` records a prior incident where it shifted underneath stored points |
| `image_cropper` → title-block OCR | live comparison path, reads the PNG file |
| `context_builder.load_drawing_png()`, `pdf_exporter` | AI input and report output |

Changing how `render_bounds` is computed would move every stored template and the matching frame
at once. The entity-bbox fallback at `dxf_background_renderer.py:113-132` produces *different*
numbers than matplotlib autoscale, so it is not a drop-in substitute.

> [!WARNING] ⛔ NEGATIVE RESULT — "delete the raster generator" is bounded by `render_bounds`
> The 2026-07-27 decision says "drop the PNG display path entirely". The **display** path is now
> gone. The **generator** cannot follow it without first giving `render_bounds` an independent,
> bit-identical source — which is a template-invalidation event, not a rendering change. Do not
> attempt it as a cleanup.

So the PNG's role changed rather than ended: it is now a data-extraction artefact and an AI
input, and nothing renders it to a user.

## Consequences

**The escape hatch is gone, and that is the real cost.** The standing argument for keeping raster
selectable was that the PNG comes from ezdxf and therefore *cannot* be missing anything, making it
the better answer for a drawing whose extraction is incomplete. A drawing the extractor mishandles
now renders wrong with no in-app way to see the truth.

Two things carry that load instead:

1. **`tools/render_audit.py` is the out-of-app fallback.** No backend, no Mongo. "Is this sheet's
   extraction complete?" stays answerable in one command, and it answers it better than eyeballing
   a PNG ever did — a census plus a per-string placement oracle.
2. **Re-ingestion is a prerequisite, not a nicety.** `render_paths` (dimensions), MTEXT rotation
   and the wrapped-elliptical-arc fix are all computed at **extraction** time. Drawings already in
   MongoDB predate them. There is no re-extract endpoint — only `upload_drawing`.

   > **Superseded in part, 2026-08-14.** `POST /drawings/{id}/reextract` now re-runs extraction
   > in place, keeping the drawing's id, room slot and audit history. The prerequisite itself
   > stands — stale drawings still render wrong until re-extracted — but it is no longer paid for
   > by destroying and re-uploading the record.
   > See [[Gotcha - The Extraction Pipeline Had Never Been Run Twice]].

**Known gaps shipping with this**, all measured and none blocking:

- no `hatch`/`solid` branch in `renderEntities.ts` — the audited drawing carries zero hatches
- plain `TEXT` with non-default `halign`/`valign`: the DXF `align_point` (group 11) is not
  extracted by `map_text`, so the insert point is used directly (correct for default-aligned text)
- 6 strings that ezdxf wraps are drawn on one line — the deliberate 15% threshold plus orphan
  guard from the column-wrapping negative result

**No `COMPARISON_CACHE_VERSION` bump.** This is display-only; it touches neither spatial matching
nor zone extraction, so hard constraint 2 does not apply.

## Why this is an ADR and not another gotcha section

[[Gotcha - A Blurry CAD Canvas and Its Four Causes]] had grown to ~500 lines and was carrying an
architectural decision — raster default, vector opt-in, "the raster is a stand-in for the CAD
viewer, not the target" — with no ADR anywhere. A default-renderer change with two reverted
attempts behind it is exactly the thing this folder exists to record. The gotcha keeps the
debugging narrative; this file keeps the decision.
