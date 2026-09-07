---
tags: [gotcha, frontend, export, pdf, canvas, react]
status: fixed
cache-version: n/a — the export path never touches the comparison cache
date: 2026-08-24
---

# Gotcha — The Report's Drawing Pages Were Blank Because the PDF Was 112 MB

> Reported as *"the drawings don't show up in the report"*, with a screenshot of a three-page PDF
> whose two drawing pages were empty white rectangles and whose text page rendered perfectly.
> There were **three** independent causes stacked under that one symptom, and each of them would
> have produced the identical screenshot on its own.

## Symptom

`Export PDF Report` produced a report whose drawing pages were blank. The cover page — plain
jsPDF text and rectangles — rendered fine, which is what made the failure look like a rendering
quirk in the viewer rather than a defect in the export.

Nothing was logged. Every step on the path is optional-chained or best-effort:

```ts
const leftImgData = canvasRefs?.old?.current?.exportImage?.();
if (leftImgData) { /* add the page */ }
```

## Cause 1 — `addImage` embeds DECODED pixels, so the file was 112 MB

`doc.addImage(dataUrl, 'PNG', …)` without a compression argument writes the image's raw decoded
samples into the PDF. It does **not** pass the PNG's own Flate stream through.

The old export asked `CanvasRenderer.exportImage()` for its default **7016 × 4960** canvas, twice.
That is 7016 × 4960 × 3 bytes ≈ **104 MB per drawing page**, before the cover.

Measured on the rebuilt four-page report (one 4608 × 2920 drawing plus three 3600 × 2400 checklist
sheets), in the dev build:

| `addImage` compression | Output |
| :--- | :--- |
| omitted | **112.66 MB** |
| `'FAST'` | **0.90 MB** |
| `'MEDIUM'` | 0.92 MB |

Flate is lossless, so the pixels are identical either way. The argument is not a size preference;
it is the difference between a PDF a viewer will render and one it will not.

⚠ **`addImage`'s compression is the 8th positional argument**, and the 7th is `alias` — so it has
to be written `doc.addImage(data, 'PNG', x, y, w, h, undefined, 'FAST')`. Passing `'FAST'` one slot
early registers it as the image's cache alias and leaves the image uncompressed: the failure this
note is about, with the fix apparently applied. (jsPDF also reaches `compression = "SLOW"` on its
own when the document carries a `FlateEncode` filter, i.e. `new jsPDF({ compress: true })`. That
works, costs more time, and hides the decision in the constructor; the explicit argument is
preferred here because it is the one thing on this path that must not be lost in a refactor.)

## Cause 2 — `useImperativeHandle` listed 14 of `renderContent`'s 30-odd inputs

```ts
useImperativeHandle(ref, () => ({ exportImage: … }), [
  drawing, activeLayers, showViolations, /* …11 more… */
]);
```

`layers` was not among them. And layers arrive **five to six seconds after** the drawing they
belong to — `setNewDrawing` deliberately publishes `{ newDrawing, newLayers: {} }` in one `set()`
and fires an async `fetchLayers` behind it, so the canvas never shows the previous sheet's
geometry under the new sheet's name.

So the handle captured a `renderContent` closed over `layers = {}`, and nothing in the dependency
list moved when the real layers landed. `exportImage` painted its white background and no
geometry, for the rest of the session. A manual marking recorded after the last captured change
was absent for the same reason — the report was missing the engineer's own checkmarks.

The fix is `[renderContent]` and nothing else. It has to be **declared below** `renderContent`:
naming a `const` in a dependency array evaluates it during render, so keeping the hook above its
own dependency is a TDZ `ReferenceError`, not a stale value.

> **The general shape:** a hand-maintained dependency array on a hook whose body calls a
> `useCallback` is a second copy of that callback's dependency list, and the two drift silently.
> Depend on the callback.

## Cause 3 — one of the two export buttons had no canvas refs at all

`useComplianceReportExport` took `canvasRefs` as a parameter. `TwoDWorkspace` passed them;
`ManualMarkingList` — the manual-check room's own **Export PDF Report** button, four components
away from where the refs live — did not. Its report contained no drawing page whatsoever, and the
optional chain above meant the pages were simply never added.

Now in `canvasExportRegistry.ts`: the workspace publishes both ref objects on mount, and any
caller reaches them by side. The hook takes no arguments.

⚠ It registers the **ref object**, not `ref.current`. Flexlayout unmounts and remounts a canvas
panel whenever its tab moves, so a captured handle goes stale while the ref object stays valid.

## Cause 4 (found while fixing the margins) — the page was 564 x 376 mm

Not a cause of the blank pages, but the same class of defect and found in the same file, so it is
recorded here rather than in a note of its own.

**jsPDF's `px` unit is not 96 dpi.** Its default scale factor for `px` is `96 / 72`, i.e. 1.333 pt
per pixel; the 96-dpi reading everyone assumes requires opting into the `px_scaling` hotfix. So
`new jsPDF({ unit: "px", format: [1200, 800] })` produces a **564.4 x 376.3 mm** page — larger
than A2. Verified by reading `/MediaBox` out of the generated file rather than by reasoning about
it:

| constructor | `/MediaBox` (pt) | physical |
| :--- | :--- | :--- |
| `unit: "px"` | `0 0 1600 1066.67` | 564.4 x 376.3 mm |
| `unit: "px", hotfixes: ["px_scaling"]` | `0 0 900 600` | 317.5 x 211.7 mm |
| `unit: "mm", format: [317.5, 211.7]` | `0 0 900 600` | 317.5 x 211.7 mm |

Nothing failed. The report looked correct on screen, printed at whatever scale the print dialog
chose, and no margin expressed in millimetres could mean anything on it. The page is now A4
landscape declared in `mm`, with the geometry in `reportPageGeometry.ts` and pinned by
`reportPageGeometry.test.ts`.

⚠ **`CHECKLIST_PAGE_H` is derived from the paper's aspect, not chosen.** It was a round 800
against a 1200 width — a 1.5 aspect placed full-bleed onto a 1.414 page, which stretches every row
of type by 6% vertically. That reads as slightly heavy type, not as a bug.

## Cause 5 — `render_bounds` is Matplotlib's autoscale, not the drawing's extent

With the page finally a real size, the margin still measured ~21 mm against a declared 7. The
remaining 14 mm was not on the page at all — it was inside the capture, and it comes from
`dxf_background_renderer.py`:

```python
# Extract the exact tight bounds generated by Matplotlib's autoscale
xmin, xmax = ax.get_xlim()
```

They are not tight, and **the comment saying they are is why this went unexamined**. `get_xlim()`
returns the *autoscaled* limits, which carry Matplotlib's default `axes.xmargin` / `axes.ymargin`
of **5% per side**; `set_aspect('equal', 'box')` then expands whichever axis is short of the
figure's ratio, adding more. Every sheet in the system has ~10% of dead space baked into its
bounds.

Measured against a canvas at the export's real capture size, with a sheet whose bounds were built
the way Matplotlib builds them:

| | ink coverage of the capture | gutter |
| :--- | :--- | :--- |
| fitted to `render_bounds` | 90.0% x 90.0% | 174 x 123 px |
| fitted to the ink | 99.0% x 98.9% | 18 x 14 px |

⚠ **`render_bounds` must not be "fixed".** Zone templates store their boxes as fractions of it,
`zone_signature` derives a sheet's template identity from it, and every stored `CadPoint` carries
a snapshot of it for drift detection. Re-deriving it would silently invalidate all three across
every drawing already ingested. The export measures the drawing's real extent instead, which is a
question only the export asks — `exportFit.ts`, and a corrected comment now sits at the source.

**The export crops to painted pixels, not to the entity list.** The page has to contain the
manual markings, annotation pins and marker labels, none of which are entities; and reading back
the renderer's own output means the crop cannot disagree with it about culling. The measuring pass
therefore runs at **full resolution**, not on a cheap low-res probe: `renderEntities` culls text
below one pixel high, so a probe answers for a different set of entities than the final render
draws — and the labels it drops are the small ones at the edges, which are exactly the ones a crop
must not cut off.

## What the report is now

Page 1 is the revision drawing with its markings, filling A4 landscape to a uniform **3 mm margin
on all four sides** (owner's call, 2026-08-24 — 7 mm first, then "much smaller" once the drawing
stopped floating inside its own bounds; ⚠ 3 mm is inside most printers' unprintable border) — which is why it carries no header band: a caption
cannot share an edge with a 7 mm top margin. Page 2 is the checklist behind those markings,
continuing onto further pages when it is long. The metrics cover page and the reference-drawing
page are gone — the cover restated counts the checklist itself carries, and the reference sheet is
the one drawing in the room that carries no marks.

## The checklist page is a canvas, not `doc.text`

Deliberate, and it is a real trade. jsPDF's built-in fonts are WinAnsi; every sheet this system
audits is Japanese, and a checklist row's REFERENCE and REVISION columns are verbatim drawing
text. Typed through jsPDF they come out empty or as mojibake — a report that looks complete while
missing exactly the values the check was about. The canvas renders them correctly, so
`complianceChecklistSheet.ts` rasterises the table at 3x.

The cost is that the checklist's text is not selectable or searchable in the PDF. If that ever
matters more than the Japanese does, embed a CJK font; do not go back to `doc.text`.

## Lessons

1. **An optional chain across a whole subsystem cannot report a failure.**
   `canvasRefs?.old?.current?.exportImage?.()` returning `undefined` was indistinguishable from
   "this room has no reference drawing". The export now prints a red panel where the drawing
   should be rather than a white rectangle.
2. **A blank page is a size symptom until proven otherwise.** Causes 2 and 3 were found by reading
   the code. Cause 1 — the one that would have survived fixing the other two — only appeared once
   the output's *bytes* were measured. 112 MB is not visible in any screenshot.
3. **Three causes, one symptom, each sufficient alone.** Fixing the dependency array and stopping
   there would have produced a 200 MB PDF with the same blank pages, and the obvious conclusion
   would have been that the fix was wrong.
4. **A library's unit is a claim to verify, not a name to trust.** `px` meaning 1.333 pt cost this
   report a page size nobody could print, and the only way to see it was to read `/MediaBox` out
   of the output.
5. **A comment asserting a property is not evidence of it.** *"the exact tight bounds"* sat above
   an autoscale call for as long as the renderer has existed, and every consumer downstream
   inherited a 10% margin it had no idea it was carrying. Two of this note's five causes were a
   confident sentence nobody re-measured.

## Related

- [[Gotcha - A Blurry CAD Canvas and Its Four Causes]] — the other place `CanvasRenderer`'s size
  arithmetic has cost something, and the same lesson about fractional vs integer canvas sizing.
- [[Gotcha - A Window Listener in a Per-Pane Hook Fires Once Per Pane]] — the neighbouring class of
  React-lifecycle defect in this workspace.
- [[Gotcha - A Room Restored From Its Findings Lost Every Checkmark]] — checkmarks going missing
  with no error, one layer down.
