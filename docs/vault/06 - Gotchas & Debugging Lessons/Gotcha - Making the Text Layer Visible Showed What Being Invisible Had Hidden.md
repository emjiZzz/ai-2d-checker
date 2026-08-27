---
title: Gotcha - Making the Text Layer Visible Showed What Being Invisible Had Hidden
type: gotcha
tags: [gotcha, rendering, pdf, export, performance, pymupdf, ezdxf, text-layer, dimensions, tolerances]
status: fixed. All three defects closed and guarded in `tests/test_vector_pdf_export.py`; the
  report now requests `TextSource.LAYER` and measures **3.4x-8.0x** end-to-end. The tolerance
  blocker was closed WITHOUT an extraction change - see "How the blocker was closed".
  Landed 2026-08-25.
cache-version: n/a — export-side only. No extraction, comparison or `render_bounds` change.
related: [Gotcha - The Vector PDF Had No Text at All, Gotcha - The Dimension Text Was Anchored to the Line It Had to Avoid, Gotcha - Three Quoted Figures That No Command Could Reproduce, ADR-011 Vector as the Only Render Path]
date: 2026-08-25
---

# Gotcha — Making the Text Layer Visible Showed What Being Invisible Had Hidden

> The question was about speed: *"this drawing is small yet generating the PDF takes so much
> time — what about an assembly?"* The answer is that **text is 90–98% of the export**, and the
> page already contains a second, 20× cheaper copy of every string that could replace it.
>
> Turning that copy visible was a four-line change. It also revealed that the layer had been
> **white**, **rotated the wrong way**, and **missing every dimension tolerance** — for its whole
> life, because none of those are things an invisible layer can be observed to be.
>
> All three are now closed and the report requests the visible layer. The tolerance one was closed
> **without touching extraction**, by letting ezdxf keep drawing the seven strings per sheet that
> the layer cannot reproduce.

---

## The measurement that started it

`draw_layout` is the whole cost, and inside it the text is nearly all of it. On the largest sheet
in `storage/uploads` (`7c71ec65…`, 2263 entities, 484 placed strings):

| | end-to-end | geometry pass | our text layer | file |
| :--- | ---: | ---: | ---: | ---: |
| `TextSource.OUTLINES` | **28.5 s** | 26.7 s | 1.03 s | 1.87 MB |
| `TextSource.LAYER` | **6.3 s** | 5.7 s | 1.06 s | 0.37 MB |

(Those are the figures before the tolerance deferral; with it the same sheet is **7.5 s**, because
ezdxf is drawing seven strings again. The per-sheet table further down is the current one.)

⚠ **The headline is ~4× on this sheet, not the 10× that `draw_layout` alone suggests**, and across
the corpus it ranges **3.4× to 8.0×**. Parse, PyMuPDF, `subset_fonts` and the marker pass are a
fixed floor that no text policy touches. Quote the end-to-end number, and quote a range.

The number that actually answers the assembly question is **per string**: ezdxf spends ~44 ms on
each one (21 s / 484), our layer **2.18 ms**. That is a change of *scaling*, not of constant — at
2000 strings the text is 88 s one way and 4.4 s the other, so an assembly becomes a geometry
problem, and geometry is 5.7 s at 2263 entities.

---

## Defect 1 — the layer was white

`TextWriter.write_text`'s `color` argument defaults to **white**. Under render mode 3 it is never
painted, so it was never wrong and never asserted. Made visible without stating the ink, the page:

```
extractable chars: 2609        search_for('特記'): 1 hit
span count:         577        every span color: 16777215
```

…and is **blank**. Every assertion that can be written *about the text* passes. Found by
rasterising the page and looking at it, which is the only oracle that could have.

✅ Fixed: `_TEXT_INK = (0.0, 0.0, 0.0)`, stated at the call site rather than defaulted.
Guarded by `test_the_visible_text_layer_is_black`.

## Defect 2 — every rotated string was turned the wrong way

`fitz.Matrix(ux, -uy, uy, ux)` is the form that *reads* like a rotation by `+rotation`. Measured
with `TextWriter.append` at a known point, it lays a `+90°` string **down** the page, where CAD's
counter-clockwise `+90°` must read bottom-to-top. `morph` applies its matrix in the opposite sense
to the one the operand order suggests; **the transpose is the rotation.**

The cost is not a visibly broken page — it is a string at a *plausible* angle, displaced by
roughly its own length:

| population | n | \|d\| median | p90 | max |
| :--- | ---: | ---: | ---: | ---: |
| dimension | 42 | 0.152 | 0.220 | 0.258 |
| dimension (rotated) | 69 | **6.901** | 10.181 | 16.305 |
| text | 264 | 0.100 | 0.165 | — |
| text (rotated) | 3 | **8.742** | — | — |

After the fix: **0.154** and **0.104** — rotated strings land exactly as well as unrotated ones.

✅ Guarded by `test_a_rotated_string_turns_the_way_cad_turns`, asserted as a comparison between a
`+90°` and a `-90°` string from one insert point, so it depends on no coordinate, no page size and
no anchor model. Both new tests were confirmed to **fail** against the pre-fix code.

---

## 🔴 Why neither was caught: the acceptance metric scores under half the page

`tools/text_layer_audit.py` reports **width ratio 1.027, 97% within ±20%, |dx| median 0.095, 0
missing** on this exact sheet, and it is *right* — for the population it scores. It skips:

```python
if abs(float(props.get("rotation") or 0.0)) > 1e-6:   continue   # rotated
if entity["entity_type"] != "text":                   continue   # every dimension
if len(text) < _MIN_CHARS:                            continue   # under 3 chars
```

Measured over the same sheet's 484 text-bearing entities:

| | share |
| :--- | ---: |
| scored by `text_layer_audit` | **47%** |
| excluded — dimension text | 23% |
| excluded — under 3 chars | 28% |
| excluded — rotated | 2% |

⚠ **The excluded half is dimension values and callout letters** — the content a reviewer actually
checks — and the exclusions have defensible individual reasons (a 2-character string repeats
dozens of times and a `search_for` hit cannot be attributed). The defect is not any one skip; it
is that the headline is quoted as if it covered the page. This is
[[Gotcha - Three Quoted Figures That No Command Could Reproduce]] in its other costume: not a
figure no command reproduces, but a figure whose command answers a narrower question than the
sentence around it.

**The oracle for the excluded populations exists and is cheap**: record ezdxf twice, once at
`TextPolicy.FILLING` and once at `IGNORE`, and the records a handle *gains* are its glyphs. That
isolates a DIMENSION's text from the lines and arrowheads in its own anonymous block, which is the
reason the tool skipped dimensions in the first place.

---

## ✅ How the blocker was closed — dimension tolerances

Under `OUTLINES`, `40` prints as `40⁻⁰·¹₋₀·₂`. Under a naive `LAYER` it printed as `40`: **the
tolerance was gone from the page.** The values live in the DIMENSION's `DimStyleOverride`
(`dimtol`/`dimtp`/`dimtm`, invisible to `get_dim_style()` — only `e.override()` sees them), and
ezdxf composes them into a stacked MTEXT fraction at *render* time:

```
\A1;\W0.800000;\T0.875000;170{\H16.799999;\S+0.02^ +0.1;}
```

`strip_mtext` drops the whole `{…}` group, so `render_text` is bare `170`. Measured across
`storage/uploads`: **46 of 724 dimensions on 14 of 57 sheets.**

The obvious fix — capture the tolerance at extraction, bump `EXTRACTION_SCHEMA_VERSION`,
re-extract the corpus — was **not** what landed, because two ways of reproducing the layout were
measured and both failed:

⛔ **`MTextExplode` is not the drawing frontend.** It returns each piece as a placed TEXT entity
and looks exactly like the answer. Rendered through the `Recorder` and compared against the same
MTEXT rendered normally, in the same document with the same face, it disagrees by up to **5.1
drawing units** across these seven strings, consistently laying the stack narrower. Building on
it would have shipped a worse error than the rotation bug this same note records.

⛔ **Re-deriving the stack from `dimtp`/`dimtm` is the same mistake one layer down** — a second
opinion about ezdxf's composition rule, living in the exporter, correct until ezdxf changes and
silently wrong after. That is the DRY failure this repo keeps paying for, in a new costume.

✅ **What landed instead: draw with ezdxf exactly the strings the layer cannot reproduce.**
`TextPolicy` has no setting between "all text" and "none", but the *frontend* dispatches text per
entity — so `_UNREPRODUCIBLE_MTEXT` names the raw MTEXT codes that force a string back to ezdxf,
and `AnnotationAwareFrontend` skips every other one. The tolerance is then right **by
construction** rather than reproduced, and the cost is bounded by how rare it is: **7 of 484
strings on the densest sheet.**

⚠ **The handle is the join, and it exists in only one place.** A DIMENSION's text is an MTEXT
inside its anonymous block, and nothing on it says which dimension it belongs to by the time it
reaches `draw_mtext_entity` — `properties.handle` is not populated there, which
`_annotation_aware_frontend` already had to document for the lineweight override. So the parent
handle is tracked around `draw_composite_entity`, returned from `_render_geometry`, and consumed
by `_text_items`. **One decision, made once.** Both halves drawing is every character struck twice
in two typefaces; neither is a value missing from the sheet. Guarded by
`test_a_deferred_string_is_not_also_written_by_the_layer`, and verified positionally on the real
sheet: **no text span sits at any deferred string's location.**

⚠ Deferring trades searchability for fidelity — a deferred tolerance is paths, so `search_for`
misses it. That is the right way round, and it is ~1.5% of strings.

## 🔴 A third defect the same mechanism papers over but does NOT fix

`strip_mtext` removes the **backslash but not the letter** from four MTEXT codes:

| raw | `strip_mtext` gives | should be |
| :--- | :--- | :--- |
| `\LA-A\l S=1/2` | `LA-Al S=1/2` | `A-A S=1/2`, underlined |
| `\OOVER\o` | `OOVERo` | `OVER`, overlined |
| `\KSTRIKE\k` | `KSTRIKEk` | `STRIKE`, struck through |
| `line one\Pline two` | `line one line two` | two lines |

Found because the section-view label printed as `L　Ａ－Ａ　l Ｓ＝1/2` on a visible layer.
Measured across the corpus: **11 strings on 7 of 57 sheets carry `\L`, 8 on 4 carry `\P`**; `\O`
and `\K` do not occur here.

🔴 **The page is fixed and the data is not.** Those codes are in `_UNREPRODUCIBLE_MTEXT`, so
ezdxf draws those strings — with their underline, which the layer could never have drawn anyway.
But `properties.text` is what the comparison engine pools, what the checklist quotes and what
`EntityAddress.text` captures as ground truth, and it still holds `LＡ－Ａl`. Fixing that changes
comparison input: it needs a `COMPARISON_CACHE_VERSION` bump and a re-extraction, and it is a
separate piece of work.

## Two smaller findings, both pre-existing and both newly visible

- **A balloon letter is a lone `\x82`.** One string on `7c71ec65…` is half of a 2-byte cp932
  sequence that `DXFParser`'s transcoding split; ezdxf reads the file directly and renders it
  correctly, so the balloon is empty only under `LAYER`. **1 of 484 strings on one sheet, 0 on
  the other** — an isolated data defect, not a systemic encoding problem.
- **`_script_runs` splits a string at every script change**, so `2×2-R20` is written as three PDF
  runs and `search_for("2×2-R20")` returns **0 hits** while `search_for("R20")` returns 2. The
  text is on the page and correctly placed; it is only unfindable *across* the `×`. This affects
  `OUTLINES` identically and always has.

---

## What landed, and what it costs

`TextSource` is one enum, not two booleans, because both copies visible double-strikes every
character in two typefaces and neither leaves the sheet with no text at all.

`_resolve_text_source` downgrades a `LAYER` request to `OUTLINES` for any payload that cannot
place every string, so asking for it is always safe and sometimes slow. It asks the **payload**
whether it can place its dimension text rather than asking the version stamp whether it ought to
be able to — a sheet with no dimension text is safe at any version, and a v7 extraction of a DXF
that never recorded a text midpoint is not safe despite its stamp. The downgrade is
all-or-nothing because `TextPolicy` is: there is no rendering half the strings from each source.

⚠ **The rotation fix moves the invisible layer too.** Rotated strings' selection rectangles have
been in the wrong place under `OUTLINES` since the layer was written; they are now correct.
`tools/text_layer_audit.py` reproduces its documented numbers **byte for byte** on both sheets
(ratio 1.027 / 1.026, 97% / 96% within ±20%, |dx| 0.095 / 0.094, 0 missing) — the proof the change
is inert where it was already measured, and it reproduces them precisely *because* it skips the
population that moved.

### The measured cost of the visible layer

⚠ **Our text carries ~7% more ink than ezdxf's**, and the number is real rather than an artifact:
the ratio converges as the raster gets finer (1.140 at 110 dpi → 1.098 → 1.077 → **1.074** at 880),
so it is a weight difference between PyMuPDF's rendering of Yu Mincho and ezdxf's outline fill of
the same face — not a size error, which would grow with the square, and not a double-strike. It
reads slightly bolder on paper, which for a printed report is the harmless direction.

⚠ **One string on one sheet is still blank** — the balloon letter `DXFParser`'s cp932 transcoding
left as a lone `\x82`. ezdxf reads the DXF directly and draws it, so it was visible under
`OUTLINES` only. An extraction defect, not an export one: the stored text is already wrong for the
checklist and the comparison, and the PDF merely stopped hiding it.

### Timing, on the six densest sheets in `storage/uploads`

| strings | `OUTLINES` | `LAYER` | speedup | deferred |
| ---: | ---: | ---: | ---: | ---: |
| 484 | 27.0 s | 7.8 s | 3.4x | 7 |
| 484 | 29.7 s | 8.2 s | 3.6x | 7 |
| 391 | 20.7 s | 4.9 s | 4.3x | 7 |
| 391 | 18.3 s | 4.2 s | 4.4x | 7 |
| 280 | 16.3 s | 2.1 s | 7.8x | 2 |
| 280 | 15.9 s | 2.0 s | 8.0x | 2 |

⚠ **For the assembly question, read the per-string figure and not the ratio.** The ratio is capped
by a fixed ~2 s floor (parse, PyMuPDF, `subset_fonts`, markers) that no text policy touches. What
changed is the SCALING: ~44 ms per string became **2.18 ms**.
