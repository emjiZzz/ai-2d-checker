---
title: Gotcha - The Vector PDF Had No Text at All
type: gotcha
tags: [gotcha, rendering, pdf, export, ezdxf, matplotlib, pymupdf, fonts, japanese, cjk, report]
status: fixed — all four are handled in
  `infrastructure/rendering/vector_pdf_exporter.py`, landed 2026-08-25 and guarded by
  `tests/test_vector_pdf_export.py`. The placement model moved to
  `infrastructure/rendering/text_placement.py` so production no longer depends on `tools/`.
  ⚠ The exporter is not yet reachable from the app — no route, and the frontend still builds the
  raster page 1.
cache-version: n/a — no engine change. Extraction, comparison and `render_bounds` are untouched;
  this is an export-side investigation only.
related: [ADR-011 Vector as the Only Render Path, Gotcha - A Blurry CAD Canvas and Its Four Causes, Gotcha - The Report's Drawing Pages Were Blank Because the PDF Was 112 MB, Gotcha - The Dimension Text Was Anchored to the Line It Had to Avoid, Gotcha - Three Quoted Figures That No Command Could Reproduce]
date: 2026-08-25
---

# Gotcha — The Vector PDF Had No Text at All

> A plan proposed replacing the report's raster page-1 with `ezdxf Frontend + MatplotlibBackend`,
> promising CAD text that is *"crisp, selectable, and searchable (`Ctrl + F`)"*. The geometry half
> is true and better than expected. The text half is **not achievable that way at all**, and one
> command says so.
>
> Then: adding the text layer that does deliver it took five attempts, because **four separate
> things displace it**, three of them silently and two of them in opposite directions.

---

## Symptom

Render the repo's own reference sheet (`0029fc8cdf974f5e92fa7148a679255d.dxf`, the drawing
`tools/render_audit.py` is pinned to) through the proposed pipeline, then read the PDF back:

```
EXTRACTED TEXT CHARS: 0
fonts on page:        []
vector drawing ops:   714
images:               0
```

Everything the plan promised about *print quality* holds — 714 real vector operations, no raster,
0.38 MB, 5.6 s. And there is **not one character of text on the page.** `Ctrl + F` for `SS400`
finds nothing, because there is nothing to find: every glyph is a filled path.

**Nothing in the pipeline reports this.** The PDF opens, looks perfect at 1000%, and prints
beautifully. Only extraction reveals it, which is why it was worth measuring before building.

---

## The premise — ezdxf renders text as paths in *every* backend

`MatplotlibBackend` implements `draw_filled_paths`. It **does not implement `draw_text`.** The
frontend converts every string to filled glyph outlines before the backend ever sees it, and the
only knobs are `TextPolicy.FILLING` (default, solid fill), `OUTLINE` (still paths) and `IGNORE`.

> [!WARNING] This is a property of the drawing add-on, not of the matplotlib backend.
> `ezdxf.addons.drawing.pymupdf` behaves the same way. **Do not go looking for a backend that
> emits real text** — the conversion happens upstream of all of them. The only way to get a text
> layer is to write one yourself, over the top.

That is what the rest of this note is about: geometry from ezdxf, text from `DXFParser`, overlaid
in **PDF text render mode 3** (invisible). Which also buys a property worth having on its own —
what a reader selects is the same `ExtractedEntity` data the canvas draws and the checklist
quotes, so the two cannot disagree about what the sheet says.

---

## Prerequisite — matplotlib's default `pdf.fonttype` deletes CJK from the text layer

Before any placement question: anything you draw with matplotlib's own `ax.text` (checklist
tables, badges, stamps) is subject to this.

`matplotlibrc` ships `pdf.fonttype: 3`, and `backend_pdf._font_supports_glyph` returns `True` for
a Type 3 font **only when `glyph <= 255`**. Everything else is emitted as an XObject glyph
procedure — drawn, not typed. Measured on `msgothic.ttc` through `configure_cad_fonts`:

| `pdf.fonttype` | extracted text | `search_for("ロール")` |
|---|---|---|
| **3** (default) | `'SS400 M745206N01 4\n: 18'` | `[]` — **the CJK is gone** |
| **42** | `'SS400 M745206N01 4ロール: 18'` | matches |

```python
matplotlib.rcParams["pdf.fonttype"] = 42   # never rely on the default here
```

⚠ A `.ttc` **does** subset correctly at Type 42, contrary to the obvious worry about fontTools
needing a font number for a collection. It emits a benign `'name' table stringOffset incorrect`
warning and produces a valid subset. That was measured, not assumed.

---

## Displacement 1 — `MatplotlibBackend.finalize()` resizes the figure out from under you

```python
fig = plt.figure(figsize=(11.69, 8.27))          # A4 landscape, as asked
...
Frontend(ctx, MatplotlibBackend(ax), ...).draw_layout(layout, finalize=True)
fig.get_size_inches()                            # -> (6.788, 4.8)
```

The page you set is discarded and replaced with one at the *drawing's* aspect ratio. The resulting
PDF page is `488.7 x 345.6 pt`, not `841.7 x 595.4`.

**Anyone planning "a 297 × 210 mm A4 vector page" should read that as a plan to fight this.** Set
the page size *after* `draw_layout`, or place the figure inside a page you control.

## Displacement 2 — `transData` is stale until something forces a draw

`set_aspect('equal', 'box')` defers the axes-box adjustment to draw time. Read the transform
before that and it is wrong by the sheet's aspect ratio:

```
after draw_layout   px/unit = 1.0394
after canvas.draw   px/unit = 1.4692      # factor 1.4135 = the sheet aspect
```

Every glyph in the text layer was therefore sized **1.41× too large**, uniformly, on the first
attempt — visible only by rendering the layer in red over ezdxf's own ink and looking at it.

```python
fig.canvas.draw()          # then, and only then:
pt_per_unit = ((ax.transData.transform((100, 0))[0]
                - ax.transData.transform((0, 0))[0]) / 100) * (72.0 / fig.dpi)
```

⚠ **Derive the scale from `transData`, never by hand from `figsize / xlim`.** Hand arithmetic
happens to give the right answer here *and* would silently stop doing so the moment displacement
1 changes.

## Displacement 3 — PyMuPDF writes every glyph from `msgothic.ttc` at 0.5 em

The font object reports correct advances. The written PDF does not honour them.

```python
f = fitz.Font(fontfile=r"C:\Windows\Fonts\msgothic.ttc")
f.text_length("指", 10)    # 10.00  -- full width, correct
f.text_length("AB", 10)    # 10.00  -- half width each, correct for MS Gothic
```

But measuring the resulting text rects against ezdxf's own ink boxes:

| script | width ratio vs ezdxf ink |
|---|---|
| Latin | **1.195** (≈ correct; the excess is advance-vs-ink side bearings) |
| CJK | **0.588** — exactly half |

Every glyph is being advanced at ~0.5 em: right for MS Gothic's half-width Latin, half of right
for full-width CJK. PyMuPDF's built-in CID font encodes full-width properly (`0.588 → 1.175`) but
carries *proportional* Latin, which then runs ~20% wide.

**Fix: two fonts, split by script**, each chosen for its advance widths — neither is ever visible.

```python
font_cjk   = fitz.Font("japan")                    # correct full-width advances
font_latin = fitz.Font(fontfile=font_path)         # correct half-width advances
```

⚠ **`pdf.subset_fonts()` is innocent.** It was the obvious suspect and was measured with and
without: byte-identical width ratios either way. Keep it — it is worth **4.95 MB → 0.51 MB**.

## Displacement 4 — `TextWriter` ignores per-glyph points and re-lays the run

Positioning each character explicitly looks like the way to absorb DXF `width_factor` into the
layout. It does not work:

```
requested per-glyph step : 6.01 pt
actual step in the PDF   : 2.54 pt, uniform
```

`TextWriter` re-lays a run out from its own font advances. So the run must be appended **once**,
and `width_factor` carried by the **text matrix**, which is what a text matrix is for:

```python
m = fitz.Matrix(wf, 0, 0, 1, 0, 0)     # x-scale about the baseline origin
tw.write_text(page, render_mode=3, morph=(origin, m))
```

Leaving it unapplied costs **4.3×** on placement error — `|dx|` median **0.566** drawing units
against **0.131** with it, and string-width error median **1.768** against **0.310**, both
measured against ezdxf's ink boxes.

⚠ ezdxf's own metrics are **additive and correct** for both scripts — `1.3128` cap units per
full-width CJK glyph, `0.6564` for MS Gothic's half-width Latin — so they are the right source for
stepping *between* runs. It is the PDF writer, not the measurement, that misbehaves.

---

## Displacement 5 — the SHX substitution makes the text too wide for its own cells

Found by an engineer looking at a real export, not by any of the measurements above: title-block
and BOM labels **overflow their cells and collide with their neighbours**.

The instinct is that ezdxf is drawing wider than the canvas. It is not — it draws ~5% *narrower*
(median ezdxf-ink / canvas-model **0.945** over 210 strings), and it honours `width_factor`
correctly. The overlap is real and it is **in the source data as rendered**, agreed on by both
renderers to within 0.2 units. On `M745206N01`:

| string | spans |
|---|---|
| `材料個数` | 291.92 → **306.48** (canvas model), 292.05 → 306.31 (ezdxf ink) |
| `Material Weight(kg)` | starts at **304.87** |

The cause is upstream of both: this corpus is drawn in `txt.shx` plus the `extfont2` BigFont,
**ezdxf cannot rasterise SHX glyphs at all**, and `configure_cad_fonts` redirects both to MS
Gothic — whose glyphs are wider than the stick font the title block was laid out for.

`renderEntities.ts` has compensated since the vector canvas landed, and says so:

```js
// Scaled (0.80x) so text fits comfortably within table cells without unwanted line breaks or
// column collisions.
const emPx = (capHeightPx * 0.80) / getCapHeightRatio(ctx, CAD_FONT_STACK);
```

> [!IMPORTANT] The lesson is where the fix goes.
> The PDF looked wrong *because it was more faithful to the DXF than the canvas is*. A compliance
> report may not disagree with the sheet the engineer reviewed, so the exporter applies the same
> 0.80 — `CAD_TEXT_FIT_SCALE` in `text_placement.py`, pinned against the TypeScript literal by
> `tests/test_report_style_consistency.py::test_text_fit_scale_matches_the_canvas`.

⚠ `Configuration` has **no text-scale knob**, so the height is scaled on the loaded document
before rendering (`_shrink_text_to_fit`), walking `entitydb` rather than the layout — a DIMENSION
keeps its drawable text in an anonymous geometry block, which is exactly where the strings sitting
tightest against their dimension lines live.

---

## Displacement 6 — the canvas and the raster resolve different typefaces

`renderEntities.ts` declares its font stack with this docstring:

> *"Mirrors the SHX→TTF substitution the raster path makes … which points `txt`/`extfont2` at
> **MS Gothic**. Both render modes have to resolve to the same glyphs or every width measurement
> disagrees between them."*

and then names a stack that is **entirely Mincho**: `"Yu Mincho", "游明朝", "MS Mincho", … serif`.
Not one Gothic face in it. So the canvas draws **Yu Mincho (serif)** and the ingestion raster
draws **MS Gothic (sans)** — the comment and the value contradict each other, and have since the
vector canvas landed.

Owner's call (2026-08-25): the **export follows the canvas**, so the printed sheet and the screen
show the same typeface. `REPORT_FONT_CANDIDATES` in `text_placement.py`, applied through
`load_and_transcode`'s per-document `style.dxf.font` parameter.

> [!WARNING] ⚠ The ingestion raster deliberately stays on MS Gothic, and this is why the two
> are separate constants rather than one.
> `render_dxf_background`'s output produces `render_bounds`; every zone template stores its boxes
> as *fractions* of it and `zone_signature` derives a sheet's identity from it. Changing the face
> there moves all of them at once — a template-invalidation event, not a rendering change. Pinned
> by `test_the_report_face_is_not_the_ingestion_faces`.

⚠ **The Mincho faces are not interchangeable members of one family.** At equal cap height,
relative to MS Gothic — and the ratio is **string-dependent**, because MS Gothic's Latin is
half-width while Mincho's is proportional, so a lowercase label and an all-caps drawing number do
not scale alike:

| face | `Material Weight(kg)` | `M745206N01` |
| :--- | :--- | :--- |
| `yuminl.ttf` (Light) | — | **1.196x** |
| `yumin.ttf` (Regular) | 1.001x | **1.283x** |
| `MSMINCHO.TTF` | **1.140x** | — |

⚠ An earlier revision of this note quoted Yu Mincho as "1.001x for Latin" **as if it were a
property of the face**. It is a property of that one string. Picking MS Mincho re-creates every
collision Displacement 5 fixed, and it presents as a scale bug rather than a font bug. The
candidate order is pinned by `test_the_mincho_order_runs_lightest_and_narrowest_first`.

**Light is preferred over Regular, which is a deliberate divergence from the canvas.**
`CAD_FONT_STACK` asks for `"Yu Mincho"` and gets Regular; its vertical stems are invisible on
3 mm labels and read as **bold** on the 9.5 mm title-block values — flagged by an engineer
reading a printed sheet, not by any measurement here. The root cause cannot be fixed by choosing
a face at all: **`txt.shx` is a monoline STROKE font and every TTF substitute is a filled OUTLINE
font**, so weight grows with glyph size in a way the original never did. Light is one step back
toward the stick font, and it is *narrower* than Regular, so it cannot introduce a collision
Regular did not already have.

⚠ `tools/render_audit.py` still models widths in `CANVAS_FONT = msgothic.ttc` while the canvas
actually paints Yu Mincho. Left alone deliberately — changing it moves the harness's published
baselines — but its `width_ratio` is measuring a face the canvas does not use, and that is worth
knowing before trusting the statistic to ~5% on CJK.

---

## Displacement 7 — ezdxf ignores `$LWDISPLAY`, so the report printed at full pen weight

Reported as *"the lineweight was too thick"*, and it was: every stroke on the page carried the
DXF's real pen weight (**0.72 pt and 1.00 pt** measured), against a canvas drawing all of them as
hairlines.

`$LWDISPLAY` is **0** across this corpus. Lineweight is a *plotting* property — how thick the pen
is on paper — and that flag is the drawing's own statement about whether to show it at all. A CAD
viewer, a plot preview and `renderEntities.ts` all honour it; **`ezdxf/addons/drawing` contains no
reference to `$LWDISPLAY` anywhere** and applies `LineweightPolicy.ABSOLUTE` unconditionally.

`renderEntities.ts` had already settled this argument for the canvas and left the warning:

> *"⚠ This deliberately diverges from the ezdxf raster at high zoom … Matching the live CAD viewer
> beats matching the bitmap here, because the bitmap is only a stand-in for it."*

The report is not a stand-in for anything — it is the copy that gets printed and signed — so the
exporter honours the flag: hairlines at `$LWDISPLAY` 0, real pen weights when it is set. Pinned
both ways by `test_lwdisplay_off_draws_hairlines` and `test_lwdisplay_on_honours_the_pen_weights`,
because a blanket hairline override would pass the first test alone and would flatten a drawing
whose weights carry meaning.

> [!WARNING] ⚠ `Configuration.min_lineweight` says "in 1/300 inch". Through `MatplotlibBackend`
> it is **PDF points**, 1:1.
> Measured: `min_lineweight` 0.25 → 0.25 pt strokes, 1.0 → 1.0, 2.0 → 2.0. Trusting the docstring
> turned a 0.13 mm hairline into **1.535 pt — twice as thick as the weights it was replacing**,
> which presents as the setting having had no effect rather than as a unit error, and sends you
> looking at the policy instead of the arithmetic. Pinned by
> `test_min_lineweight_is_converted_as_points_not_thirtieths_of_an_inch`.

The recipe for a fixed width is from `LineweightPolicy`'s own docstring and is not obvious:
`lineweight_scaling = 0` collapses every stroke onto the floor, and the floor is `min_lineweight`.

---

## Displacement 8 — `cap_height_ratio` defined its own answer into existence

Found on **2026-08-25**, by re-measuring the acceptance metric after the font switch rather than
by looking at a page. It is the eighth instance of this note's own thesis, and the cleanest: the
function stated its load-bearing assumption in a comment, the assumption stopped being true, and
nothing anywhere re-read the comment.

```python
# A font built at cap_height=1 measures widths in cap-height units. Latin glyphs in MS
# Gothic are exactly half-width, so "MMMM" is 2 em; dividing gives em per cap unit.
em_in_cap_units = font.text_width("MMMM") / 2.0
```

That is exact for MS Gothic and **circular for anything else**: it returns whatever value makes
`M` half-width. `M` is **0.5000 em** in `msgothic.ttc` and **0.9390 em** in `yuminl.ttf`, whose
Latin is proportional — a fact `text_placement.py`'s own `REPORT_FONT_CANDIDATES` docstring
states two screens above the function. Displacement 6 changed the report face to Yu Mincho Light
and this function was not revisited, so it began returning **0.3890** against a true **0.7305**.

`_write_text_layer` sizes every run as `item.height / cap_ratio * pt_per_unit`, so the entire
invisible layer was written at **1.92×** the glyphs it sits over. Two symptoms, neither visible:

- a selection rectangle roughly twice the width of its text — the only thing a reader could
  ever notice, and only by dragging over it;
- **six strings silently dropped from the layer**, pushed past the page rect that
  `TextWriter(page_obj.rect)` is bounded by. The page still looked perfect; it just had six
  fewer searchable strings than it reported.

**The fix reads ezdxf's own measurement instead of re-deriving it** —
`glyph_cache.font_measurements.cap_height / head.unitsPerEm` — which is the right source rather
than merely a working one: `_write_text_layer` takes its ADVANCES from that same font object, so
any other cap height makes the size and the spacing disagree. Measured after the change,
PyMuPDF's advances match ezdxf's at a ratio of exactly **1.0000** on Latin, CJK and
U+3000-padded strings alike.

⚠ **It is inert for every face where the old assumption held**, which is why
`tools/render_audit.py`'s committed baselines do not move: `msgothic.ttc` returns 0.761719 and
`MSMINCHO.TTF` 0.667969, both bit-identical to the estimate, because MS CJK faces really do set
`M` at exactly 0.5 em. `render_audit.py` calls this with the default and was unaffected;
`--json` is byte-identical across the fix at 185,536 bytes.

Guarded by `tests/test_vector_pdf_export.py::test_cap_height_is_not_measured_by_forcing_m_to_half_width`,
and — because the instance matters less than the class — by
`test_cap_height_ratio_is_typographically_possible_for_every_report_face`, which asserts every
entry in `REPORT_FONT_CANDIDATES` lands in the 0.6–0.85 band real fonts occupy. The old value of
0.389 fails that band, so a future face change is caught the moment it lands, by someone who does
not have to know which faces are half-width.

---

## ⛔ Negative result — `properties.bbox` is not a placement source

The first two attempts anchored the text layer on the parser's `properties.bbox`. Measured against
ezdxf's ink with a paired displaced control:

- median ink **at** the bbox **13.4%**, displaced **11.9%** — almost no signal
- only **41.2%** of bboxes clearly inkier than a displaced copy
- **25.6% (64 of 250) sat on completely blank paper**

`bbox_source: "mtext_column"` is the declared *wrapping column*, not the rendered extent. It is
fine for hit-testing and useless for placing a glyph.

**What works is already in the repo.** `tools/render_audit.py` models exactly this and is measured
against ezdxf's `Recorder` every time the renderer changes:

| Reuse | Not |
| :--- | :--- |
| `geometry.location` / `insert` — the insert point | `properties.bbox` |
| `_ANCHOR_FRACTIONS[attachment_point]` | assuming bottom-left |
| `cap_height_ratio()` → **0.7617** | a hand-guessed constant |

> [!IMPORTANT] The lesson is the DRY one, and it cost three iterations.
> A cap-height constant *cannot* be hand-picked: MS Gothic puts Latin caps at ~0.72 em and CJK
> ideographs at ~1.0 em, and one DXF text height governs both. Guessing `0.72` inflated every
> Japanese string by 1.39×. `cap_height_ratio()` measures it from the font and had been sitting
> in `render_audit.py` the whole time.

---

## Where it lands once all four are fixed

Same sheet, prototype vs. the plan's pipeline:

| | ezdxf alone | + invisible text layer |
|---|---|---|
| extractable chars | **0** | **1612** |
| embedded fonts | 0 | 2 (subset) |
| raster images | 0 | **0** |
| vector ops | 714 | **714** |
| size | 0.38 MB | 0.51 MB |
| build | 5.6 s | ~8 s |

Placement, against ezdxf's own ink oracle:

- **model** — `|dx|` median **0.131**, p90 **0.849** drawing units. The canvas's own measured
  placement is `|dx|` median 0.115 (ADR-011), so the text layer is as good as the renderer it
  sits on.
- **end to end** — PDF text rects vs ezdxf ink: median width ratio **1.031**, **83% within ±20%**,
  **166 of 167** strings found.

> [!WARNING] ⚠ **The three figures above are the PROTOTYPE's, and the oracle behind them no
> longer describes the page.** They were taken in MS Gothic at full DXF height. Displacement 5
> then introduced `CAD_TEXT_FIT_SCALE` and Displacement 6 changed the face to Yu Mincho Light,
> and nothing re-ran them for two weeks. Kept here as the point-in-time record they are; the
> re-measurement below supersedes them.

### Re-measured 2026-08-25, in the configuration the report actually renders

**Re-run it rather than quoting it** — the figures above went stale precisely because the harness
that produced them lived in a scratchpad and no command could reproduce them:

```bash
services/backend/.venv/Scripts/python.exe tools/text_layer_audit.py storage/uploads/0029fc8cdf974f5e92fa7148a679255d.dxf storage/uploads/123d7dfc85284e81bb6bc5ac2d568cab.dxf
```

It exits non-zero if any string is written but unfindable, or if page 1 acquires a raster image.

**The oracle had to be rebuilt before any of this meant anything.** `record_ground_truth` records
ezdxf's ink in the CANVAS configuration — MS Gothic, full height — so against the current export
it is wrong in two directions at once, **0.8464** on width, and the two errors partly cancel into
a plausible number. The harness now mirrors `_render_geometry`'s document preparation exactly
(report face via `load_and_transcode`, then `_shrink_text_to_fit`) and swaps `MatplotlibBackend`
for `Recorder`, so "where ezdxf put the glyphs" is measured on the same document the sheet was
rendered from.

Two dense sheets, every single-line unrotated string with a handle:

| | `0029fc8c…` | `123d7dfc…` |
|---|---|---|
| strings compared | 168 | 176 |
| **not found in the layer** | **0** | **0** |
| width ratio, median | **1.026** | **1.027** |
| within ±20% | **97%** | **97%** |
| within ±10% | 86% | 85% |
| `\|dx\|` median (drawing units) | **0.094** | **0.095** |
| `\|dy\|` median | 0.356 | 0.372 |
| extractable chars | 1616 | 2605 |
| raster images | **0** | **0** |

Two sparse sheets scored 1.023 on 3 and 5 comparable strings — consistent, but too few to carry
weight; the two above are the result.

**The systematic +2.6% is definitional, not error.** A PDF text rect is an ADVANCE box and
ezdxf's oracle is an INK box, so the rect is wider by the side bearings. Measured directly,
PyMuPDF's advances match ezdxf's at exactly **1.0000** — the model's widths are not approximate.

⚠ **The remaining ~3% tail is unexplained and is a question about the harness, not a known
defect.** It is confined to U+3000-padded title-block labels (`材　　質`), which score 0.74–0.79.
Searching the page for one directly returns a single hit at its full 24.92 pt width, and the
advance check above is exact for U+3000 strings, so the model is placing them correctly; what
disagrees is the ink-box oracle. Do not "fix" the exporter against this number until the oracle
is understood.

⚠ **These figures date from AFTER Displacement 8.** The same harness on the same sheet
immediately before that fix read width ratio **1.920**, **5%** within ±20%, and **6 strings
missing** from the layer. If a future measurement lands near 1.9, look at `cap_height_ratio`
first.

`Ctrl + F` finds `M745221N01`, `SS400`, `125`, `指示なき角部は糸` and `タップ`. Rendered in red over
ezdxf's ink, the layer and the glyphs merge to solid orange across the whole notes block.

## Still open

- **Wrapped MTEXT** — line splitting is a guess. `render_audit.cluster_text_records` already
  handles *"one record per line"* and should be reused rather than re-derived.
- **Rotated text** — carried through the morph matrix, **untested**; no rotated strings on this
  sheet.
- **Halfwidth katakana** (U+FF61–FF9F) falls into the Latin bucket in `_script_runs` and will
  advance wrong. ⚠ The *"part of the p10 = 0.466 tail"* clause that stood here is stale — p10 is
  **1.008** on the 2026-08-25 re-measurement, so this gap is now **unmeasured rather than
  quantified**: neither dense sheet carries a halfwidth-katakana string. It is a reading of
  `_is_full_width`, which stops at U+FF60, not an observation.
- **Non-DXF drawings** — `extraction_pipeline` branches on `pdf` and `step/stp/iges/igs/icd`.
  `load_and_transcode(dxf_path)` has no answer for a PDF-sourced drawing. `storage/uploads` is
  57/57 DXF today, so this passes testing and fails in the field. The route now refuses these
  with 422 and the frontend falls back to the raster page with an alert — honest, not a feature.

✅ **Concurrency — the `pyplot` half is closed, the load test is not.** This item read *"drives
matplotlib through the `pyplot` state machine … port to the OO `Figure`/`FigureCanvasAgg` API
first"*. That port happened: `_render_geometry` builds `Figure` + `FigureCanvasAgg` directly and
never imports `pyplot`, pinned by
`tests/test_vector_pdf_export.py::test_the_exporter_never_touches_pyplot`, which parses the module
with `ast` rather than trusting a grep. The route offloads through `asyncio.to_thread`.
⚠ **Still true: two simultaneous exports have never actually been run.** `configure_cad_fonts`
mutates `rcParams` and ezdxf's font manager, and `_configure_fonts_once` guards that with process
state, so the remaining risk is a first-call race — whose failure mode is corrupted output rather
than an exception. Reasoned, not exercised.

✅ **The route and the frontend switch have landed**, so this note's *"nothing a user can click
has changed yet"* no longer holds: `POST /api/v1/export/drawings/{id}/vector-sheet` returns the
sheet and `useComplianceReportExport` saves it.

⚠ **They are no longer one PDF.** The merge described here lasted a day: on 2026-08-25 the export
became a **pair of files** — `<name>-drawing.pdf` and `<name>-checklist.pdf` written into a folder
the user picks once — so the drawing can be handed over without the findings attached.

🔴 **It asks for a FOLDER, and that is a permissions constraint, not a UI choice.**
`tauri-plugin-dialog` grants filesystem access to exactly what the dialog returned:
`save()` calls `allow_file(&path)` for that one path, `open({directory: true})` calls
`allow_directory(&path, recursive)`. So a save dialog authorises **one** file, and deriving a
sibling name from it writes somewhere that was never granted. This shipped as a save dialog first
and failed with *"forbidden path … not allowed on the scope for `allow-write-file`"* — but only
outside `fs:allow-home-write-recursive`, so it worked in a home directory and nowhere else. ⚠ Any
future "write a second file next to the one they chose" idea has the same defect; the scope is
per-path.

The split rule lives in
`reportDocuments.ts`, and it is a module rather than four lines in the hook because **the two
paths are not symmetrical**: in the vector path jsPDF holds only the checklist and nothing has to
be taken apart, while in the raster fallback page 1 is jsPDF's own page 0 and the split is real.
Reversing that branch writes a `-drawing.pdf` whose first page is a checklist sheet — a valid PDF
of the right size that looks like a clean export until someone goes looking for the drawing.

⚠ **A report built this way stops being evidence of what the engineer saw.** The canvas culls 7
section-callout entities and 3 clipped model-space entities that ezdxf draws, and 36 of 55 stored
drawings are at a stale `EXTRACTION_SCHEMA_VERSION`. That is an ADR-011 amendment and an owner's
decision, not a rendering detail — see the review that produced this note.

---

## Minor

`render_audit.record_ground_truth`'s return annotation says a 3-tuple; it returns **four** values
(`boxes, records, text_facts, layout_name`).
