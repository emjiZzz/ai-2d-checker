---
title: Gotcha - The Two Sides of a Comparison Come From Different Exporters
type: gotcha
tags: [gotcha, toolchain, extraction, comparison, dxf, dwg, icad, layers, provenance]
status: measured — constraint, one latent trap recorded
cache-version: n/a — nothing changed; this is a property of the corpus
date: 2026-08-11
verified-against: M745221N01 pair (reference DWG->DXF, revision iCAD SX .icd->DXF), read directly from the DXF headers and tables
related: [Gotcha - Exploded Block Children Have No Handle, Gotcha - BYBLOCK Is Not BYLAYER, ADR-011 Vector as the Only Render Path]
---

# The two sides of a comparison come from different exporters

> [!IMPORTANT] The reference and the revision are not two versions of one file. They are two
> **different programs' idea of the same drawing**, and almost every structural difference
> between them is the exporter talking, not the designer.

Provenance, which the vault had never recorded and which explains a pile of previously-loose
observations:

| side | route |
| :--- | :--- |
| reference | **DWG → DXF** |
| revision | **iCAD SX `.icd` → DXF** |

## What actually differs

Measured on the `M745221N01` pair, straight from the DXF headers and tables:

| | reference (DWG → DXF) | revision (iCAD `.icd` → DXF) |
| :--- | :--- | :--- |
| layers | `0,1,2,3,4,7A,8,9,RAHM2/3/5,CLIN,INFO,TITLE,…` — a real scheme | `0, NoLayerName_001…003, Defpoints, VIEWPORTS` |
| structure | everything in **model space**; `Layout1` empty | 28 model + **396 in `ICADSX Layout`**, 4 viewports |
| top-level MTEXT | **6** — the rest nested in blocks | **231** — written straight into the layout |
| lineweights | uniform **0.25 mm** ×320 | **1.00** ×136, **0.50** ×330, **0.25** ×34 |
| `$EXTMIN/$EXTMAX` | `0,0` → `630, 458.53` | `-112.94,-87.5` → `50.72, 87.5` |
| origin (WCS 0,0) | the sheet's **bottom-left corner** | **on the part**, interior to the extents |
| `SX_FinishSymbol_1` | absent | present |

Neither file defines a UCS: the table is empty and `$UCSORG`/`$UCSXDIR`/`$UCSYDIR` are plain
identity on both. Both are DXF R2000 (`AC1015`), both `ANSI_932`. So none of the above is a
format-version difference — it is two exporters making different choices.

`NoLayerName_001` is the tell. It is not a drawing convention; it is the iCAD exporter inventing
names because `.icd` carries no DXF-compatible layer table.

## What this explains

- **[[Gotcha - Exploded Block Children Have No Handle]]** — the 0.8–13% vs 83–92% handle split is
  this. DWG nests text in blocks, so the parser explodes it and the children get `parent_handle`
  and no handle; iCAD writes MTEXT at top level, so it keeps its own. **Handle coverage tracks the
  exporter, not the reference/revision role.** That note has been amended.
- **[[Gotcha - BYBLOCK Is Not BYLAYER]]** — the surface-finish symbol is `SX_FinishSymbol_1`, an
  iCAD-specific block. The reference has zero BYBLOCK entities, which is why a colour defect
  affecting one entity presented as *"the revised drawing looks wrong"*.
- **The lineweight asymmetry** recorded in [[Gotcha - A Blurry CAD Canvas and Its Four Causes]] —
  *"a defect that only one of two open drawings can express"*. The reference is uniform 0.25 mm
  because the DWG route flattened the weights; the iCAD side kept three.
- **The origin question** — iCAD SX's on-screen `ORIGIN` markers are viewer overlays with no DXF
  entity type, and neither exporter wrote a UCS. Nothing was dropped in translation; there was
  never an entity to drop.

  What *is* recoverable, and this took a correction to get right: the revision has **three**
  origins, not one — **one per paper-space viewport**, each at that view's own anchor
  (正面図, sectA, isome1). They are recoverable from the stored `viewport_transform` and are now
  drawn behind the "Show View Origins" toggle. The **global** model origin is a fourth, separate
  thing (`グローバル` in iCAD's tree) and behaves completely differently: projected through this
  sheet's viewports it lands *outside* two of the three, visible only in the front view.

  The reference has **zero** viewports — everything is in model space — so it has no per-view
  origins at all, and its global origin sits at the sheet's bottom-left corner rather than on the
  part. So origin is **not a shared reference between the pair**, and comparing it across them
  would fire on every drawing. Any origin check has to be *within* one drawing.

## Why the comparison survives it

Deliberately, and it is load-bearing:

- `COMPARABLE_ENTITY_TYPES = ("text", "dimension")` (`spatial_differ.py:52`) — layer names,
  lineweights, block nesting and origin conventions never reach the differ.
- `SpatialDiffer` matches in a frame normalised by **each drawing's own `render_bounds`**, so two
  files with unrelated coordinate origins are still comparable.

That is why a DWG sheet and an iCAD sheet can be diffed at all. Do not "simplify" either property
without knowing this is what it is holding up.

## ⚠ The latent trap: anything keyed on layer name is one-sided

`context_builder.build_structured_context` selects title-block text by layer name:

```python
if txt.layer.lower() in ("am_bor", "border", "title", "title_block"):
```

The DWG reference has a layer literally named `TITLE`. The iCAD side has `NoLayerName_001…003`.
So this filter can populate `title_block_annotations` for one side of a pair and **never** for the
other — a silent asymmetry that would look like "the revision has no title block".

**Not a live defect as of 2026-08-11, and that was checked before writing it down.** The function
is reached only from `ai_engine` (which hardcodes `gemini-2.0-flash`, retired 2026-06-01) and
`summarization_pipeline`. ADR-010's `infrastructure/audit/summary/` module does not import it, and
`settings.ENABLE_LLM_SUMMARY` defaults off. It is recorded because it is a trap for whoever turns
that on, not because it is biting now.

**The general rule: never key comparison logic on layer name.** One of the two exporters in this
corpus destroys them.

## Lessons

1. **Provenance is data, and it was missing.** Half a dozen separate observations —
   handle coverage, layer naming, lineweight uniformity, layout structure, the missing origin —
   were each recorded as a property of *a drawing* when they were properties of *a toolchain*.
   Nothing in the pipeline captures how a file was exported, so nothing could have connected them.
2. **"Reference" and "revision" are roles, not file types.** Every asymmetry in this note is
   currently correlated with the role and caused by the exporter. The correlation holds only while
   the convention does.
3. **A cross-toolchain pair makes exporter artifacts look like design changes.** The differ is
   narrow enough to be immune today. Anything that widens
   `COMPARABLE_ENTITY_TYPES` — comparing `block` entities so the ▽ symbols get checked, for
   instance, which is an open question — has to clear this first, because block structure is one
   of the things the two exporters most disagree about.
