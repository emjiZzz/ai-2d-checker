---
tags: [gotcha, frontend, rendering, canvas, hidpi]
date: 2026-08-11
---

# Gotcha — A Blurry CAD Canvas and Its Four Causes

## Symptom

The 2D review canvas looked visibly soft next to iCAD SX displaying the same sheet. Linework
read as fuzzy grey rather than crisp coloured hairlines. Reported as a styling problem; it was
four independent defects stacked on top of one another.

**Fixing only the interesting-looking one does not fix the symptom.** That happened here: the
line-thickening pass below was removed first, on a confident diagnosis, and the canvas was
still blurry. The dominant cause was the dullest one.

---

## Cause 1 (dominant) — CSS size did not match the backing store

```jsx
// BEFORE — every pixel on this canvas is a resample
<canvas
  width={Math.round(width * dpr)}     // backing store: integer device px
  height={Math.round(height * dpr)}
  style={{ width: '100%', height: '100%' }}   // CSS box: whatever the parent is
/>
```

`width`/`height` arrive from a `ResizeObserver`, and **`entry.contentRect` reports fractional
sizes** — a flex column happily produces `689.6px`. So the backing store was
`Math.round(689.6 × 1) = 690` device px while the CSS box was `689.6` px. The browser then
bilinearly rescaled a 690px bitmap into a 689.6px box.

A 0.06% stretch sounds harmless. It is not: a non-integer scale factor means **no** pixel lands
on a pixel, so every pixel of the canvas is interpolated from its neighbours. The result is a
uniform softness that is independent of zoom level, render mode, image quality, and every other
thing you might spend a day tuning.

`TwoDWorkspace` compounded it with a tolerance:

```js
if (Math.abs(prev.width - newW) > 2 || Math.abs(prev.height - newH) > 2)
```

which let the prop sit up to 2px away from the container's true size — a 0.3% stretch.

### Fix

Derive **both** sizes from one rounded device-pixel figure so `cssPx × dpr === backingPx`
exactly:

```jsx
const backingW = Math.round(width * dpr);
const backingH = Math.round(height * dpr);

<canvas
  width={backingW}
  height={backingH}
  style={{ width: `${backingW / dpr}px`, height: `${backingH / dpr}px` }}
/>
```

and round in the observer, comparing exactly rather than through a deadband. There is no thrash
risk: the canvas is absolutely positioned inside a 100%-sized wrapper, so its size never feeds
back into the observed element.

> `ThreeDWorkspace.tsx` still passes raw fractional `contentRect` values. It drives a Three.js
> renderer, which manages its own pixel ratio, so it is not the same bug — but it has not been
> checked.

---

## Cause 2 — the canvas was never drawing vectors

The HUD said so outright, and nobody read it:

```
ZOOM: 81%   VIRTUALIZED: 0/518   RENDER: 0.1ms
```

**`0/518`** — zero of 518 vector entities drawn. `reviewStore.ts` defaults
`renderMode: 'raster'`, and `renderEntities.ts` skips the whole entity loop in that mode. What
is on screen is a downscaled PNG of the drawing. `RENDER: 0.1ms` corroborates: 518 entities
cannot be drawn that fast; that is the cost of one `drawImage`.

This bounds how good the raster path can ever look. At 81% zoom the sheet spans ~690 CSS px
from an 8400px source (`figsize=(24,18) dpi=350`) — **8% scale**. Title-block text 30px tall in
the source lands at 2.5px. A vector renderer draws a 1-device-pixel hard-edged stroke at any
zoom; a downsampler must average that stroke into a light grey smear. No filter recovers it.
That difference *is* the "looks like a real CAD viewer" difference.

### ⛔ NEGATIVE RESULT — `renderMode: 'vector'` was tried and REVERTED

The reasoning above is sound and the diagnosis held: after cause 1 was fixed the canvas was
still blurry, but only when zoomed **out** — the signature of minification rather than a
stretched bitmap. Vector is genuinely the only fix for that. **It was switched on anyway,
without being run, and it was wrong.**

Measured on M745221N01 at 81% zoom: **`VIRTUALIZED: 356/518`** — 162 entities not drawn. The
linework that did render was sharp, and the sheet was unusable:

| Missing | Cause |
|---|---|
| **Every dimension** — φ175, φ145, φ100, all arrowheads and extension lines | `dimension` is its own `entity_type` holding only anchor points (`defpoint`, `text_midpoint`, `ext1`, `ext2`) plus `measurement` and a `dimstyle`. **No dimension-line geometry is stored anywhere**, and `renderEntities.ts` has no branch that would synthesise it from the dimstyle. |
| Tolerance table and most title-block text | `if (screenHeight < 4) return;` — the LOD guard. At fit-to-screen zoom nearly all table text is under 4px. |
| Closing segment of closed ellipses/polylines | Stroked as an open `moveTo`/`lineTo` chain; `is_closed` is never read. |
| Any hatch/solid fill; centred and right-aligned text drifts | No branch; `halign`/`valign` attachment points ignored. |

Sharp-but-incomplete is a worse product than soft-but-complete, and much worse in a tool whose
entire purpose is catching what changed between two drawings — a silently dropped dimension is
a false negative the reviewer cannot see.

### Follow-up: the blockers were fixed; the default is still `'raster'`

`EntityMapper._dimension_render_geometry` now flattens each DIMENSION's anonymous block via
`virtual_entities()` into `render_paths` (stroked) and `render_fills` (arrowhead SOLIDs),
recursing through arrowhead INSERTs and tessellating radial/angular arcs. Measured against
ezdxf: a linear dimension with closed-filled arrows yields 4 paths + 2 fills; a radial yields
2 paths + 1 fill.

**The geometry attaches to the DIMENSION rather than being exploded into sibling entities, and
that is the load-bearing decision.** `context_builder.py:64-65` pools `entity_type == 'text'`
and `entity_type == 'dimension'` *separately*. Exploding a dimension into real LINE/TEXT
entities — the obvious reading of "explode it like INSERT does" — would make every dimension
appear twice in the audit: once carrying `measurement`, once carrying the same string as text.
Attaching keeps the comparison entity set byte-identical, so no `COMPARISON_CACHE_VERSION` bump
is needed (verified: nothing in the backend reads the new `text_height` property, and
`ViewportGenerator.calculate_bounds` is per-type with named keys, so no generic walker picks
the new geometry up).

`GEOMETRY_SCHEMA["dimension"]` gained `point_list_groups: ("render_paths", "render_fills")`, so
the model→paper projection reaches them — an unlisted key stays in model space while its
siblings move, drawing a dimension's value in one place and its arrows in another. The existing
parametrized projection guards cover this automatically because the new keys were added to
`ENTITY_GEOMETRY_SAMPLES`.

Also fixed, same code path: the text LOD floor dropped 4px → 2px (at fit-to-screen zoom 4px
culled the whole tolerance table, rendering it as an empty grid), closed ellipses/polylines now
`closePath()`, and an unresolved `<>` placeholder is never painted literally.

**Still `'raster'` by default, deliberately.** The fix has not been run against a real drawing —
that needs the backend and an ingested DXF. A `PenTool` toggle was added to the 2D view-controls
menu so it can be A/B'd on real geometry first; `setRenderMode` had no caller anywhere in the
app before this, which is precisely how the vector path shipped unable to draw a dimension.

⚠ **Dimension geometry is produced at extraction time.** Drawings already in MongoDB have
dimensions with no `render_paths` and must be re-extracted. *(As written this said re-**uploaded**,
because until 2026-08-14 there was no other option; `POST /drawings/{id}/reextract` now does it
without discarding the drawing's id, room slot or audit history —
[[Gotcha - The Extraction Pipeline Had Never Been Run Twice]].)*

### Measured after re-ingestion (M745221N01, 2026-08-11)

Verified against the running backend rather than by eye. All 4 DIMENSION entities on each
drawing now carry `render_paths`, with `measurement` resolved into `text` (`'125'`, `'6'` —
no surviving `<>` placeholders) and `text_height` harvested from the rendered block.

Accounting for the original **356/518**:

| | count | |
|---|---|---|
| Text recovered by the 4px → 2px LOD floor | **+137** | the real cause of the empty tolerance table and title block |
| DIMENSION entities now drawn | +4 | |
| LEADER entities now drawn | +3 | had no branch at all; callout pointers rendered as nothing while their text stayed |
| **Expected total** | **500/518** | |

The residual 18 are `layer` (6) and `block` (12) — layer-table records and INSERT containers
whose children are exploded and drawn separately. **Both are correctly not drawn.** Note that
`GeometrySerializer` puts them in the drawable payload, so the HUD's denominator counts 18
entities that can never be drawn.

> [!NOTE] The healthy ceiling is **497/518**, not the 500 this round predicted.
> [[Gotcha - Clipped Model Geometry Still Gets a Coordinate]] landed after this section was
> written and correctly skips 3 more entities — model geometry that falls outside every
> paper-space viewport. 518 − 18 non-drawable − 3 clipped = **497**, which is what `CLAUDE.md`
> and `tools/render_audit.py` both state today. See the census table further down.

The dimensions on this drawing produced **0 fills** — its dimstyle uses open stroke arrowheads,
not solid triangles (confirmed: 0 closed loops among the paths). The SOLID/TRACE fill branch is
exercised by `test_closed_filled_arrowheads_become_fills_not_strokes` instead.

### Two further defects the count could not show

`VIRTUALIZED: 500/518` was correct and the sheet was still wrong, because entity *count* says
nothing about entity *correctness*. Both were found by rendering the extracted vectors beside a
crop of the backend's own ezdxf raster — the cheapest ground truth available, and the thing that
should have been built before the first flip.

1. **Dimension text drew horizontally.** MTEXT keeps its orientation in `text_direction` (a
   vector), not `rotation` — which reads `None` on MTEXT and silently degrades to `0.0`. The
   two 90° dimensions on this sheet have `text_point`s only 8.5 units apart, so drawn
   horizontally the `145` and `100` landed on top of each other. `MText.get_rotation()`
   resolves the vector and returns 90.0 / 90.0 / -35.76 for the three rotated dimensions.
   **This is the same trap as the documented `map_text` MTEXT case** (`char_height` vs
   `height`): reading the TEXT-shaped attribute off an MTEXT yields a wrong-but-plausible
   default instead of raising.
2. **The isometric flange rendered as a broken crescent** — elliptical arcs that wrap through
   2π were swept backwards. Written up separately, because it corrupts the `iso` zone and not
   just the picture: [[Gotcha - Wrapped Elliptical Arcs Were Tessellated Backwards]]
   (`COMPARISON_CACHE_VERSION` v43 → v44).

Both are computed at **extraction** time, so they need a re-upload to take effect — the second
re-upload this exercise required, which is the argument for having built the offline comparison
harness first.

**Turning on a path that had never been exercised also exposed three latent defects** in the
serializer, all invisible for as long as the raster PNG sat in front of them. These fixes were
KEPT — they are correct regardless of render mode:

| Defect | Effect once vectors render |
|---|---|
| `COLOR_MAP.get(index, "#FFFFFF")` never resolved ACI 256 | BYLAYER is *most* entities on a real drawing — the whole sheet went flat white |
| `lineweight / 100 if lineweight > 10 else lineweight` | 5 and 9 are valid lineweights (0.05/0.09mm); they passed through as 5–9**px** slabs |
| `linetype in ["dashed", "hidden"]` | real names are decorated (`HIDDEN2`, `CENTERX2`), so hidden and centre lines rendered solid |

Fixed in `geometry_serializer.py`: resolve BYLAYER/BYBLOCK against the layer records already
present in the same entity set, let 24-bit `true_color` outrank the ACI index, use ezdxf's
authoritative `aci2rgb` palette instead of a hand-written 10-entry table, lift near-black to
white for the dark canvas (the raster path got this free from `ColorPolicy.COLOR_SWAP_BW`), and
match linetype names as substrings. Pinned by six tests in `test_phase5_visual_workspace.py`.

Two renderer changes matter as much as the switch itself:

- **Hairlines floor at one *device* pixel (`1 / dpr` CSS px), not 1.5 CSS px.** 1.5 CSS px
  cannot land on the pixel grid — it straddles two device pixels and antialiases into a pair of
  greys, reproducing the exact soft edge vectors were meant to escape. Without this, switching
  to vectors looks barely different and the conclusion "vectors didn't help" gets recorded.
- **Text is no longer forced `bold`,** and honours `properties.rotation`. The bold was
  compensating for washed-out downsampled raster glyphs; applied to text rasterised at screen
  size it smears 4–6px CJK title-block strings.

Still not handled by the vector path: hatch and solid fills, and text `halign`/`valign`
attachment points (the insert point is used directly, which is correct for default-aligned
text and drifts for centred or right-aligned strings). Raster remains selectable and is still
the better answer for a drawing whose extraction is incomplete, since the PNG comes from ezdxf
and cannot be missing anything.

> [!NOTE] Superseded 2026-08-11 — raster is no longer selectable.
> MTEXT attachment points were fixed later the same day (defect 1 in the table below). Raster
> was removed from the display path entirely by [[ADR-011 Vector as the Only Render Path]], so
> the "keep it as the safe fallback" argument above no longer holds — `tools/render_audit.py`
> carries that load instead. Hatch/solid still have no branch.

---

## Cause 3 — the line-thickening pass was a blur kernel

A pass composited the rendering at five 1px offsets to approximate a morphological dilation.
But `drawImage` uses `source-over`, which is **not** a max operation — it accumulates alpha:

```
a_out = a_src + a_dst · (1 − a_src)
```

A fully transparent pixel adjacent to a 0.6-alpha antialiased edge came out **0.6 opaque**.
Every stroke grew ~1px outward with a soft fringe, which the mipmap chain then smeared across
the whole reduction. A dilation meant to *preserve* ink was spreading it.

**Why it existed, and why it was already dead.** Git settles the ordering: the thickening pass
is committed in `217b3a1`; `buildMipmapLevels` had *no commit* — it was uncommitted
working-tree code. So the dilation predates the mipmap chain. It was the pre-mipmap workaround
for hairlines vanishing when an 8400px image was downsampled in a **single** `drawImage`, where
sparse sampling misses thin strokes entirely. The mipmap chain solves that properly — each
halving averages 4 pixels, so a hairline survives as reduced alpha instead of being skipped.
That made the dilation redundant the day it landed. Nobody removed it, so both ran, and the
redundant one was destructive.

---

## Cause 4 — LOD selection in the wrong unit, and a stale DPR

`selectOptimalMipmap` was called with `scale`, which is CSS-px-per-world-unit because
`drawCanvas` installs the dpr transform first. So it picked a mipmap sized for the CSS box,
which the GPU then upscaled to the backing store. On the 125%/150% display scaling Windows
ships as default on many panels, that is a guaranteed 1.25–1.5× upscale of an already-minified
mipmap, stacked on the minification blur. Multiply by `devicePixelRatio` for screen; leave
export alone, since export renders at an explicit pixel size with no dpr transform.

Separately, `CanvasRenderer` read `window.devicePixelRatio` **once** into a plain const while
`drawCanvas` re-read it every frame. Drag the window to a monitor with different OS scaling and
the transform and the backing store disagree — blurry until some unrelated state change forces
a re-render. `matchMedia('(resolution: Ndppx)')` is the only DPR-change signal browsers expose,
and it is resolution-specific, so it must be re-armed after each fire.

---

## Lessons

1. **Check `cssPx × dpr === backingPx` before touching the renderer.** It is the single most
   common cause of a blurry canvas and the easiest to overlook, because the canvas still looks
   *correct* — just soft. `width: '100%'` on a canvas is almost always a bug.
2. **`ResizeObserver.contentRect` is fractional.** Round it before it reaches anything that
   sizes a bitmap, and drop the tolerance — a deadband on a size that feeds a backing store
   trades a re-render you can afford for blur you cannot.
3. **Read the diagnostic HUD before theorising.** `0/518` and `0.1ms` named cause 2 exactly.
4. **`drawImage` at offsets is not dilation.** `source-over` accumulates alpha; it blurs.
5. **A workaround outlives the defect it worked around.** When the real fix lands, delete the
   compensation — two mechanisms for one problem means the older one is now damage.
6. **LOD/mipmap selection must happen in device pixels**, and DPR is not a constant.
7. **A confident single-cause diagnosis of a visual defect is usually incomplete.** Blur
   composes: four sub-visible softenings multiply into one obvious one. Verify against the
   running app, not against the plausibility of the story.
8. **Use the symptom's shape to pick the cause.** Zoom-*independent* blur is a stretched
   bitmap (cause 1). Blur that worsens as you zoom *out* is minification (cause 2). That one
   distinction separated two rounds of guessing from the actual answer.
9. **A code path nothing calls is not "working, just unused" — it is unverified.** Switching
   `renderMode` to `'vector'` exposed three serializer defects *and* four renderer gaps that
   had sat behind the raster PNG. Expect that whenever you enable something for the first
   time, and budget for it.
10. **Do not ship a default flip you cannot run.** The vector switch was landed on a correct
    diagnosis, passing types and 278 green tests — and it deleted every dimension from the
    drawing. Nothing in the suite covers "does the sheet look right", so green meant nothing
    here. If verifying needs the backend and a real DXF, either stand that up or hand the
    change over as a toggle for someone who can, but do not change what everyone sees by
    default on the strength of reasoning alone.

---

## Round three — the count was right and the sheet was still wrong (2026-08-11)

Reported as "still so many differences" against a side-by-side of the canvas in **vector** mode
and iCAD SX on `M745221N01_FSRS2_KMTI.DXF`. The HUD read `VIRTUALIZED: 497/518`.

### Nothing was missing. The arithmetic closes exactly.

This is the finding that reframes the whole round, and it is worth writing down because two
previous rounds were spent hunting for absent geometry:

| | count |
|---|---|
| Deep DXF census (all layouts, INSERTs exploded): MTEXT 249, LINE 172, ELLIPSE 33, LWPOLYLINE 28, INSERT 12, ARC 6, CIRCLE 4, VIEWPORT 4, DIMENSION 4, LEADER 3, TEXT 1 | 516 |
| + layer-table records | 6 |
| − VIEWPORT (no mapper; ezdxf draws no border for them either) | −4 |
| **= HUD denominator** | **518** |
| − 6 `layer` − 12 `block` (containers, correctly never drawn) | 500 |
| − 3 `outside_viewport` (clipped model geometry, correctly skipped) | **497** |

So `497/518` is the healthy ceiling, not a shortfall, and **no entity type is absent from the
sheet**. Every remaining difference was in *how* entities were drawn. A census cannot see any of
them — which is the point of the harness below.

### The harness that should have existed two rounds ago

`tools/render_audit.py`. Offline, no backend, no MongoDB. It runs the real `DXFParser` and
`GeometrySerializer`, applies a declarative port of the `renderEntities.ts` branch table to
reproduce the HUD count, and then does the part that matters: renders the same layout through
`ezdxf.addons.drawing.Frontend` into a **`Recorder`** backend, which yields the exact placed ink
box of every entity keyed by handle. Comparing each string's insert point against the point
inside that box which its attachment implies gives a per-string `dx`/`dy`/`width_ratio` in
drawing units.

Two supporting decisions:

- The ezdxf preamble — Japanese font registration, latin-1 read + cp932 transcode, SHX→MS Gothic
  style override, layout selection — moved out of `dxf_background_renderer.py` into
  `dxf_render_setup.py`. A harness that configured fonts differently from the renderer it audits
  would report differences that exist only in the harness.
- The harness declares `RENDERER_APPLIES_*` flags at the top. That is the drift surface against
  the TypeScript renderer, so it is stated rather than buried; flip one to re-measure the
  corresponding defect.

### Six defects, all measured

| # | Defect | Scope on this sheet |
|---|---|---|
| 1 | `attachment_point` ignored — every string drawn left/alphabetic | **106 of 228** strings displaced; worst `dx` **33.3 units** |
| 2 | `width_factor` extracted, never applied | **248 of 249** MTEXT carry `\W` 0.60–0.91 |
| 3 | `font: {height}px` treats DXF **cap** height as an **em** size | all text at **0.7617×** correct size — a flat factor, not scatter |
| 4 | Dimension text rebuilt from `actual_measurement`, dropping the block's own string | 3 of 4 dimensions lost their `⌀` |
| 5 | Lineweight read as CSS px, floored to a hairline | 1.00mm ×136, 0.50mm ×331, 0.25mm ×51 collapsed to one width |
| 6 | `MText.get_rotation()` not used in `map_text` | 2 vertical headers drew horizontally |

Result: `|dx|` median 0.849 → **0.115**, p90 4.90 → **0.750**, max **33.31 → 1.27**.
`width_ratio` → 1.022. The residual is glyph side bearing (comparing an anchor point against an
*ink* box), not a defect — that is the floor of this measurement.

Two more the harness found that no one had listed:

- **MTEXT column wrapping was ignored.** 5 title-block headers (`材 質`, `品 名`, …) declare a
  column width narrower than their text; ezdxf wraps them and the canvas drew one long line
  across the neighbouring cell. Line advance measured at **1.0× char height** against ezdxf
  (3.010 and 2.890 for a char height of 3.0) — *not* AutoCAD's documented 1.667×. Matching ezdxf
  is right while the raster is the ground truth; that constant is the first thing to revisit if
  wrapped text ever looks wrong.
- **`_dimension_render_geometry` discards TEXT/MTEXT children by design.** That was correct for
  avoiding double-counting in `context_builder`, and it is also where the `⌀` was being lost. The
  fix stores the block string as a **new `render_text` property** rather than overwriting
  `properties["text"]`, keeping the comparison entity set byte-identical and avoiding a
  `COMPARISON_CACHE_VERSION` bump — the same reasoning that put the geometry there in the first
  place.

### ⛔ NEGATIVE RESULT — tracking (`\T`) must NOT be applied

The obvious reading of `\W` + `\T` is "two horizontal multipliers, fold them into one scale".
Measured, that made every string too narrow by exactly the tracking factor: across the 81
comparable strings carrying a `\T`, `width_ratio` equalled `tracking` to within **0.019**.
**ezdxf applies `\W` only.** `properties.tracking` is still extracted; it is simply not a glyph
scale. Applying it would put the vector and raster modes back out of agreement.

### The oracle's own blind spot — `textBaseline` is not a DXF anchor

Reported after the anchor fix had landed and measured clean: *"text are being pushed upward and
collides with lines"*. The oracle said `|dy|` median 0.017, max 0.67. Both were true.

`ctx.textBaseline = 'bottom'` aligns the bottom of the font's **em box** to the anchor. A DXF
bottom attachment aligns the **baseline**. The gap between them is the descender — **0.18 of the
cap height** in MS Gothic — so every bottom-anchored string was drawn that much too high: 0.39
drawing units at char height 2.2, 1.44 at 8.0. In a title-block cell about 5 units tall that is
enough to ride up into the rule above. It affected **215 of 247 strings**.

**Why the oracle missed it, and this is the transferable part:** `dy` compares where the *insert
point* lands against ezdxf's ink box. It never modelled what the canvas does with the insert
point afterwards. The instrument checked the input to the renderer and called it the output. A
measurement that does not close the loop through the thing being measured will report zero error
for an entire class of defect.

Fixed by removing the browser's font metrics from the decision: `textBaseline` is now always
`'alphabetic'` and the vertical offset is computed from the DXF cap height
(`baselineOffsetPx` — 0 for bottom, half a cap for middle, a full cap for top, with multi-line
blocks stacking from the correct end). Browser ascent/descent can no longer disagree with ezdxf,
because it is no longer consulted. Pinned by a test asserting the baseline is never a
font-metric one.

### ⛔ NEGATIVE RESULT — MTEXT column wrapping is a knife-edge we cannot win

Honouring `column_width` looked like a clean win: 5 title-block headers that ezdxf wraps were
running across the neighbouring cell. Implemented, and it broke the sheet in a more visible way —
a lone `）` dropped below its line in `４ロール：２４（４×６台）`, and single characters split off
other headers.

The measurement says why. Of **247 MTEXT entities carrying a column width, 99 would wrap and
every one is over by less than 6%** — most by exactly **3.0%**, the signature of an exporter that
set each column to its own text's natural width. The browser measures with its MS Gothic, ezdxf
with fontTools, and `measureText` returns an *advance* width where the column was authored
against ink. That few percent decides the break, and there is no threshold that separates noise
from intent: ezdxf's own genuine wrap of `材 質` is only ~4% over.

So the canvas wraps only past **15%**, plus an orphan guard that refuses a final line of one
character. On this drawing that means nothing wraps. The cost is real and accepted: the handful
of two-line headers iCAD shows stacked render on one line, slightly overflowing their cells.
A wide string reads correctly; a one-character orphan reads as a broken drawing.

**The only way to actually win this** is to stop deciding in the browser: have extraction compute
the line breaks with ezdxf's own metrics and ship them in the payload, the way `render_text`
already ships the dimension string. Not done — it needs the font configuration from
`dxf_render_setup` to be applied during extraction, which it currently is not.

### ⛔ NEGATIVE RESULT — lineweight is NOT a world-space width

Fixing defect 5 by treating the millimetre value as a world-space width is the reasoning that
matches the raster: ezdxf's default `LineweightPolicy.ABSOLUTE` bakes weights into the PNG
proportionally to the sheet, so zooming the bitmap scales them.

**It was landed, and it was wrong** — reported within minutes as "why are the lines on the
template too thick". At title-block zoom a 1.00mm frame line becomes a ~15px slab. Lineweight is
a *plotting* property, not a dimension of the geometry, so live CAD viewers — iCAD SX included —
display it at constant screen thickness. Converting at a fixed `96/25.4` CSS px per mm, unscaled
by zoom, preserves the ratio without slabs.

That still was not the whole answer. **`$LWDISPLAY` is 0 on both M745221N01 files** — the DXF
header switch for "do not display lineweights at all" — which is why iCAD draws them with uniform
thin linework despite the FSRS2 sheet recording 1.00mm on 136 entities and 0.50mm on 331. An
entity can record a weight and still be meant to draw as a hairline; the weight is what the
*plotter* uses, and this header says whether the *screen* honours it. Now extracted as
`metadata.lineweight_display` and defaulted to off when absent.

**What made this hard to see is worth remembering:** the bug was invisible in the left-hand pane
and obvious in the right. `M745221N01_REFERENCE.DXF` is a uniform 0.25mm across 320 entities, so
ignoring `$LWDISPLAY` changed nothing there; its neighbour carries three weights and turned into
slabs. A defect that only one of two open drawings can express will be reported as "why does that
one look wrong" rather than as the header it actually is — compare both files before believing a
renderer is at fault.

The screen-constant conversion is kept and still deliberately diverges from the raster at high
zoom, for the drawings that do set `$LWDISPLAY`. The raster is a stand-in for the CAD viewer, not
the target.

### Lessons

11. **A healthy entity count is not evidence of a correct sheet, and this is the second round it
    has fooled someone.** `497/518` was exactly right while half the text was in the wrong place.
    Count answers "is it there"; only a placement oracle answers "is it right".
12. **Build the measuring tool before the fix when three defects overlap.** Cap height makes text
    bigger, width factor makes it narrower, attachment point moves it. Any one alone looks like a
    regression of the other two, and `width_ratio` sat at a deceptively healthy 0.954 *because*
    two errors were cancelling. Nobody eyeballs their way out of that.
13. **Ask the ground truth rather than the specification.** AutoCAD documents MTEXT line spacing
    as 1.667×; ezdxf renders 1.0×. AutoCAD applies `\T`; ezdxf does not. Both were settled in
    minutes by measuring the renderer we actually match against.
14. **"Matches the raster" and "matches the CAD viewer" are different targets, and they diverge
    under zoom.** The raster is a bitmap, so anything baked into it scales. Say which one a fix
    is aiming at.
15. **An instrument that stops at the renderer's input will report zero error for whole classes
    of defect.** `dy` measured where the insert point landed and never modelled what
    `textBaseline` did with it, so a 0.18-cap upward shift on 215 of 247 strings measured as
    clean. When a measurement disagrees with a human looking at the screen, suspect the
    measurement's scope before suspecting the human.
16. **Prefer deriving layout from the CAD value over trusting the platform's equivalent.** Cap
    height, line advance, dash length and lineweight all have a browser-native mechanism that is
    *almost* the DXF meaning. Every one of them was wrong by a few percent to 20%, and every
    fix in this round was the same move: compute it from the DXF number instead.

## Closed out — the flip finally landed, on the third attempt

Ratified as [[ADR-011 Vector as the Only Render Path]] on 2026-08-11. `renderMode` was not set to
`'vector'` — it was **deleted**, along with the raster display path, the mipmap chain, the
per-pixel light-theme recolour, the loading overlay that covered the PNG download, the `PenTool`
toggle, the declined `hybrid` mode, and `GET /drawings/{id}/rendering`.

The third attempt differed from the two failed ones in exactly one respect, and it is the whole
lesson of this note: **it was measured before it was shipped, by an instrument that exists outside
the app.** The numbers it was justified on:

```
=== CENSUS =====  497/518 drawn
|dx|  median=0.1148   p90=0.7216   max=1.4017
width_ratio  median=1.0222        rotation lost: 0
```

### ⛔ NEGATIVE RESULT — the raster *generator* cannot be deleted

The 2026-07-27 direction said "drop the PNG display path entirely", and the obvious next cleanup
is to stop generating the PNG at all. **It is bounded, and not by rendering.**
`metadata["render_bounds"]` comes from matplotlib's autoscale inside the very function that saves
the PNG, and every zone template is stored as *fractions of it* — `zone_signature()` derives the
template's identity from it, `SpatialDiffer` normalises its matching frame by it, and
`coordinate_stamp` drift-checks against it. The entity-bbox fallback a few lines below produces
different numbers, so it is not a substitute. Removing the generator is a template-invalidation
event wearing a cleanup's clothes. Full reasoning in the ADR.

### What now answers "is this sheet complete?"

Nothing in the UI. That was raster's job and raster is gone. `tools/render_audit.py` answers it
better and offline — but only if someone runs it, so **run it after any change to
`renderEntities.ts`, `entity_mapper.py` or `geometry_serializer.py`**, per `CLAUDE.md`.

One standing prerequisite survives the flip: `render_paths`, MTEXT rotation and the elliptical-arc
fix are all computed at **extraction** time, so drawings already in MongoDB must be re-extracted.
*(Written when the only way to do that was a re-upload; `POST /drawings/{id}/reextract` has done it
in place since 2026-08-14.)*

## Related

- [[ADR-011 Vector as the Only Render Path]] — the decision this note's debugging produced.
- [[Gotcha - Zone Detection Accuracy & Stability]] — the other place CSS-px vs CAD-space
  confusion yields a plausible-looking wrong result.
- [[Gotcha - Clipped Model Geometry Still Gets a Coordinate]] — the 3 entities that moved the
  healthy census from 500 to 497.
- [[CanvasRenderer & Entity Drawing]] — the renderer this lives in.
- [[ADR-006 Removing the Three AI Comparison Methods]] — documented `renderMode` as surviving
  surface area; ADR-011 retires it.
