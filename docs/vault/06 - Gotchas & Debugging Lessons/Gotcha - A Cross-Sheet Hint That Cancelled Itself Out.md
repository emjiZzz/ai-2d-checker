---
tags: [gotcha, canvas, coordinates, manual-check, ground-truth]
date: 2026-08-18
status: fixed
---

# Gotcha — A Cross-Sheet Hint That Cancelled Itself Out

The manual-check canvas had a "hover ghost": hover an entity on one sheet, and the other canvas
outlined **the same place**, computed as a fraction of each sheet's own `render_bounds`. The
reasoning was recorded as a deliberate restraint — a position is a weaker hint than a pairing, and
"which entities correspond" is the engineer's judgement, not the tool's.

It was wrong in two independent ways, and the second one is why the first was never noticed.

## 1. The arithmetic was an identity

Both canvases read **one shared `viewport`** from `reviewStore`. Each builds its transform as

```
scale  = viewport.scale * 1000 / spanX
transX = viewport.x - xmin * scale
```

so a point at fraction `f` of a sheet lands at

```
x_local = (xmin + f*spanX) * scale + transX
        = f * 1000 * viewport.scale + viewport.x
```

**The sheet's own `spanX` and `xmin` cancel.** Publishing a fraction on one canvas and resolving it
on the other therefore returns the source rectangle's *own* pixel position — measured `dx =
0.000000` and `dw = 0.000000` across a 3× bounds difference. The only surviving dependence on the
target sheet was through the ratio of the two aspect ratios in Y, which is not a feature, it is the
error term.

⚠ **Its tests passed and always would have.** They asserted the round trip against the same
formula the implementation used — pinning the arithmetic, never the premise. This is the
`renderViewOrigins` lesson one level up: that suite counted `stroke()` calls, so the tests here
were deliberately written to assert coordinates, and they *did* — but a coordinate derived from
the code under test is not an oracle either.

## 2. The premise was wrong regardless

`render_bounds` is not the paper. `infrastructure/rendering/viewport_generator.py` computes it as
**the bounding box of the extracted entities, plus 5%** — a quantity defined by the content, which
is the very thing that differs between a reference and its revision.

Even where the two boxes agree perfectly it does not help. `M745204N01` is the demonstration: its
reference is a clean **3× uniform scaling** of the revision's box (1386 × 980.10 against 462 ×
326.70), aspect matching to four decimals — and the two sheets still arrange their views
differently, so the same fraction is a different feature. Other pairs do not even get that far:
`M745203N01` is 1.3611 against 1.4141, `M745221N01` 1.3740 against 1.4141.

**The sheets are not aligned. No coordinate mapping between them exists to be fixed.**

## The fix: match the value, not the place

Hovering `145` on one sheet now outlines every `145` on the other, through
`normalizeEntityValue` in `entityPicking.ts`. Matching raw strings finds almost nothing, because
the two exporters spell the same value differently — all measured on real pairs:

- the revision writes **full-width** (`Ｒ2`, `１`), the reference half-width (`C2`, `3-9キリ`);
- the reference still carries **raw DXF override codes** (`%%c8`), undecoded;
- the diameter prefix is frequently **not in the data at all** — on `M745204N01` both sides store a
  bare `145`, and the `ø` the engineer sees is printed by the dimension style.

So: decode `%%c`/`%%d`/`%%p`, strip MTEXT inline codes, **NFKC**, drop the diameter mark, drop
whitespace, upper-case. `%%d` and `%%p` are *decoded rather than dropped* — both sides spell them
the same way once decoded, and discarding them would collapse `60°` onto a bare `60`.

⚠ **The value is in `properties.text`.** `geometry.text` is `None` on every entity in the corpus —
checked across dimension, text and mtext on both sides of `M745230A01`. An index reading only the
geometry field matches nothing and looks like a logic bug.

Measured coverage, hovering a valued entity:

| pair | ref → finds match | rev → finds match | shared values hitting >1 box |
| :--- | ---: | ---: | ---: |
| M745204N01 | 90% | 61% | 29 |
| M745230A01 | 84% | 55% | 24 |
| M745203N01 | 89% | 55% | 21 |

The asymmetry is not a defect: the revision sheets carry ~60% more annotation (280 against 175 on
`M745230A01`), so many revision values have no reference counterpart.

### Value alone was still too loose

The first version matched on value only and outlined everything it found, which showed up in the app
as one hovered angle producing three boxes labelled `x3` — because a sheet carries the same value
several times, and 21–29 shared values per pair resolve to more than one box. A candidate must now
agree on **all** of:

- **value**, normalized as above;
- **entity type** — a note reading `145` is not the dimension reading `145`;
- **dimension kind** (`dim_type & 0b111`) — an 80° angular dimension is not a linear `80`;
- **zone** — a value in the BOM is not the same value in a view.

⚠ **Zone membership needs the Y flip.** Detected zone boxes are CAD Y-up and the picking index is
flipped-world, so comparing them raw assigns zones mirrored about the sheet centreline — right in
the middle, wrong at top and bottom. That is CLAUDE.md constraint 3 and the `renderViewOrigins`
failure in another costume. `zoneKeyForBox` applies the flip once, and the smallest containing zone
wins because zones nest (`title_upper_left` inside `title`).

Ties that survive all four — three 60° angular dimensions in one view — are separated by position
**within the zone**. That is a much weaker positional claim than the one this note demolishes, and a
different one: the *sheets* do not line up, but a single view's contents do. On `M745204N01` the
60°/50°/80° callouts sit at the same clock positions on both sides even though the sheets do not.

⚠ **Ties are only broken when there is something to break them with.** With no zone information on
either side there is no basis to choose, so every candidate is outlined and the count is labelled.
Returning one arbitrary box would be indistinguishable from a confident answer, which is the exact
failure this overlay must not produce.

## The cost, recorded rather than argued away

This **does** suggest a correspondence the fraction version withheld, which is a real reduction in
the independence of a CHANGED marking — the concern that motivated the original design. Owner's
call, 2026-08-18, made with the trade-off stated: the positional hint was not withholding anything,
it was drawing a rectangle in an arbitrary place. **The category selector is still never
pre-filled**, which is the load-bearing half of the independence guarantee.

## Lesson

**A transform that normalises into a space and immediately back out of it may be doing nothing.**
Before trusting one, substitute the two halves and see whether the intermediate quantity survives.
Here it cancelled exactly, and the feature had shipped, been reviewed, been documented in a
handover as a locked design decision, and been pinned by three passing tests.

⚠ **The value itself was also wrong** on angular dimensions when this landed — stored in radians,
so the overlay matched `1.05` where the sheet reads `60°`. Separate defect, separate note:
[[Gotcha - An Angular Dimension Stored Its Measurement in Radians]].

Related: [[Gotcha - A Missing Y Flip Is Invisible Near the Centreline]],
[[Gotcha - Reference and Revision in Different Coordinate Spaces]],
[[Gotcha - Full-Width Grid Labels Bridged Zones]],
[[Gotcha - Path2D Batching Destroys Entity Identity]],
[[Gotcha - A Marking Cannot Store an Entity Id]]
