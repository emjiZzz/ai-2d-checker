---
title: Gotcha - Every Published Baseline Measures a Configuration Users Do Not Get
type: gotcha
tags: [gotcha, eval, baseline, zones, zone-template, measurement, product, stage-0b]
date: 2026-08-12
cache-version: n/a — the divergence is between two configurations, not two cache versions
related: [Gotcha - Zone Templates Vanish in Offline Eval, Gotcha - One Zone Template Cannot Fit Two Sides, Gotcha - A Zone Template Gap Hid Half of a Real Change, 00 - AI Maturity Status]
---

# Every published baseline measures a configuration users do not get

Raised by the owner on 2026-08-12, as a product observation rather than a bug report:

> *"We can't rely forever on zone box alignment because we're using it only in development to
> align and lessen the system's mistake on pairing. If align zone boxes feature push to prod, it
> will just produce another step to end-users which consumes time. That way, it's not a solution."*

That is correct, and it invalidates the reading of every number this project has published since
2026-08-06.

## The problem

`baseline-v42` through `baseline-v45` all apply the **hand-aligned** zone templates captured into
the manifest, and none of them says so. [[Gotcha - Zone Templates Vanish in Offline Eval]] made
that deliberate and was right to — an eval that scored against detector boxes while users saw
hand-aligned ones was measuring the wrong thing. But it closed the gap in the direction that
assumed alignment ships.

If alignment is a **development aid** — a human dragging boxes per sheet layout, which is a
per-customer, per-layout manual step — then the published numbers describe a configuration no end
user is in.

## The measurement

36 mutation pairs, one drawing family, same engine, same corpus, cache v45. The only difference is
whether the captured templates are applied.

| | templated (`baseline-v45.json`) | detection only (`baseline-v45-detection.json`) |
| :--- | ---: | ---: |
| precision | 0.9796 | **0.8039** |
| recall | 0.8727 | **0.7455** |
| F1 | 0.9231 | **0.7736** |
| true positives | 48 | 41 |
| false positives | **1** | **10** |
| category attribution | 1.00 | 0.68 |

**−0.15 F1**, and the decomposition is the part worth keeping:

| category | templated | detection only | |
| :--- | :--- | :--- | :--- |
| `bill_of_materials` | P 0.86 / R 0.60 | P 0.86 / R 0.60 | **identical** |
| `title_block` | P 1.00 / R 0.75 | P 1.00 / R 0.75 | **identical** |
| `notes_section` | P 1.00 / R 1.00 | P **0.59** / R 1.00 | 9 false positives |
| `drawing_views` | P 1.00 / R 0.93 | P 1.00 / R **0.68** | 9 misses |

**Two of the four live categories need no human at all.** Detection matches hand-alignment exactly
for BOM and title block. The entire 0.15 sits in `notes` and `views`, and in opposite directions:
`notes` invents findings (boilerplate like `素材調質施工硬度hs35~38` reported as changed), `views`
loses them (`a-a`, `6-6.6キリ11ザグリ深6.5`, `※要確認`).

**A hypothesis that was checked and was wrong:** the 9 `notes` false positives are not the 9
`views` misses mis-categorised. Measured directly — **0 of 14** missed findings appear as a
spurious finding with identical text. Detection genuinely misses changes *and* genuinely invents
others; the F1 drop is not a filing error.

## Why the system uses geometry at all — the two alternatives, measured

The natural question is why zones are rectangles rather than something semantic.

**1. The DXF layer does not carry it.** Fitted as an upper bound on this corpus's 2,764 comparable
rows — assign each row its layer's dominant zone — layer predicts zone **53.1%** of the time, and
that is scored on the data it was fitted to. Two-thirds of rows sit on three catch-all layers:

| layer | rows | purity | spread |
| :--- | ---: | ---: | :--- |
| `NoLayerName_001` | 1343 | 51% | tolerance 684 · title 384 · bom 111 · title_upper_left 72 |
| `WAKU` | 678 | 50% | tolerance 342 · title 186 · none 96 · bom 42 |
| `RAHM2` | 414 | 41% | title 171 · none 76 · title_upper_left 62 · bom 61 |

Only small, specific layers are clean (`7A` → bom 100%, `RAHM3` → bom 100%). The draughtsman did
not separate content by layer, so no layer rule can recover the zones.

**2. The sheet's own ruled borders DO carry it, and nothing reads them.** Each sheet contains
28–49 long horizontal and 25–35 long vertical segments — the ruled boxes around the title block,
the BOM table and the notes. Distance from each hand-aligned edge to the nearest ruled line, in
drawing units:

| zone | top | bottom | left | right |
| :--- | ---: | ---: | ---: | ---: |
| `title` | 3.3 | **0.1** | **0.3** | **0.2** |
| `views` | 0.1 | 0.2 | **0.0** | **0.0** |
| `bom` | 0.2 | 1.0 | 3.5 | **0.5** |
| `title_upper_left` | 0.4 | 1.8 | **0.1** | **0.6** |
| `notes` | 1.4 | **13.5 / 27.3** | 3.2 | 3.0 |

**The hand-alignment is largely re-drawing by hand what the draughtsman already drew.** And the
single edge that is *not* on a ruled line — the `notes` bottom — is exactly the edge whose
mis-placement collapsed category attribution from 1.00 to 0.89 on the same day.

## The ruled-border spike — measured 2026-08-12, and it does not rescue the zone that matters

The obvious follow-on: if the borders are in the data, snap the zones to them and the manual step
disappears. Spiked by measuring the **ceiling** first — for every zone on every human side, the
best-IoU rectangle that is actually closed and drawn (four edges ≥80% covered by real segments,
axis-aligned within 0.6 units, collinear runs snapped at 1.5). Best-IoU is chosen *knowing the
answer*, so this is an upper bound on any selection rule, not a proposal.

| zone | mean IoU | min | max | ≥0.85 |
| :--- | ---: | ---: | ---: | ---: |
| `views` | **0.97** | 0.85 | 1.00 | **11/12** |
| `title` | **0.95** | 0.91 | 0.97 | **12/12** |
| `tolerance` | **0.85** | 0.45 | 0.98 | 9/12 |
| `title_upper_left` | 0.62 | 0.60 | 0.63 | 0/12 |
| `bom` | 0.37 | 0.07 | 0.71 | 0/12 |
| `notes` | **0.08** | 0.07 | 0.08 | 0/12 |
| `iso` | **0.06** | 0.05 | 0.06 | 0/12 |

**The technique recovers the sheet frame and nothing else.** `views`, `title` and `tolerance` are
frame structures and come back almost exactly. `notes` and `iso` score 0.06–0.08 — and the reason
is not a tuning failure: **their best candidate is the whole frame rectangle, because there is no
ruled box around them to find.** That is the same fact the edge-distance table above reported from
the other direction, where the `notes` bottom edge sat 13.5–27.3 units from any line while every
other edge sat within 3.5.

**So the zones ruled borders recover are the ones that already work without alignment**
(`title_block` is byte-identical detected vs templated), and the zone carrying 9 of the 10
detection-only false positives is the one with no border to snap to.

> [!WARNING] ⚠ **Correction, 2026-08-12 — that sentence over-reaches, and the exception is the
> biggest remaining gap.** It holds for `notes`, `iso` and `title_block`. It does **not** hold for
> `views`, which loses **R 0.93 → 0.68** under detection — nine findings — while scoring a **0.97**
> mean IoU ceiling against real ruled segments, ≥0.85 on **11 of 12** sides. So half the F1 gap
> *does* have a geometric answer that nothing reads yet. The `notes` half does not, and was closed
> instead by classifying per entity: see
> [[Gotcha - Adding a Note Destroys the Notes Zone]]. After that change the split is starker —
> detection-only `notes_section` is **P 0.93 / R 1.00** while `drawing_views` is still
> **P 1.00 / R 0.68**, so `views` recall is now essentially the whole remaining gap.

`bom` is **inconclusive rather than negative** and is the one loose end: 0.71 on reference sides,
0.07 on revisions. Diagnosed to the ruling level — on `M7452A0N01`'s revision the BOM band
(y 258–287) has good horizontal rulings (`y=286.5` covers 100% of the table width, `y=265.5` covers
89%) but **no vertical ruling at the table's left edge**; the nearest verticals at x=196.5 and
x=210.0 span y 10–51, which is the title block. Whether that border is inside a `block` (the
revision carries 10), below the 15-unit length floor, or genuinely absent was not resolved.

**Caveat 1 from the original write-up — can furniture be told from part outlines — is answered
"not fatal, but unsolved".** The ceiling above sidesteps it by peeking at the answer; a real
implementation faces **831–1831 closed rectangles per sheet**. For the frame zones the winners are
the outermost structures, which is a tractable selection rule. For `notes` and `iso` there is
nothing to select, so selection never becomes the binding problem.

### What this implies for `notes`

`notes` has no drawn boundary on these sheets. It is text floating inside the frame, and the
"notes zone" is a rectangle *we* impose on it. No geometric method — percentage grid, keyword
anchor cluster, ruled border, or a human with a mouse — can find an edge that the drawing does not
contain, which is why every approach tried so far has produced a different arbitrary box.

That points away from regions entirely for this category: **decide per text entity whether it is a
note, from its own content and context, rather than from where it sits.** Recorded as a direction,
not a decision — it is a different architecture from zone scoping, and it is not costed.

## The transferable rule

> **State the configuration a number was measured in, inside the number.** A baseline that omits
> it will be read as "the system's performance", and the omission survives precisely because the
> number is good.

And the narrower one: **a manual step that improves a metric is a loan against the metric, not a
fix.** It has to be repaid by automation or by shipping the step, and until one of those happens
the improvement is not the product's.

## What follows

- `tools/eval.py --baseline` now has a companion artifact: **`baseline-v45-detection.json`**, the
  same corpus and engine with every zone unpinned. Both are committed. Any future claim must say
  which one it rests on.
- **`current_rung` is unaffected** — it is 0 with `rung_evidence: none`, so nothing was claimed on
  the templated number. The rule this note adds is for the first rung claim, not a retraction.
- The gap is **0.15 F1, entirely in two zones**, and the ruled-border signal is unexploited. That
  is a scoped engineering target rather than an open-ended one. **Not started, and not decided —
  see [[00 - AI Maturity Status]]'s "What's next".**
