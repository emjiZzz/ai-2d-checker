---
title: Gotcha - The Engine Ignored the Section Callout but the Canvas Still Drew It
type: gotcha
tags: [gotcha, frontend, rendering, canvas, section-views, viewports, drafting-furniture]
status: resolved
date: 2026-08-14
cache-version: n/a — **no bump, deliberately.** Nothing about the comparison changed; this is the
  render path only. The engine's own exclusion of section callouts landed at v38 and is
  untouched. Bumping here would discard every valid cached audit to change what gets painted,
  which hard constraint 2 is not for.
related: [ADR-011 Vector as the Only Render Path, Gotcha - Clipped Model Geometry Still Gets a Coordinate, Gotcha - Fullwidth Callouts Were Never Classified]
---

# Gotcha — the engine ignored the section callout but the canvas still drew it

**Class:** two subsystems, one decision, only one of them told · **Found:** 2026-08-14, from a
user pointing at `Ａ` and `Ａ－Ａ` on screen

---

## Symptom

M745221N01's revision carries a section view. Its identifiers — the `Ａ－Ａ` that titles the
section and the lone `Ａ` at the cut arrow — are painted on the sheet, and they produce no
finding, no checkmark, nothing in the checklist. Label present, verdict absent.

## Cause

The comparison engine had already excluded them, in two independent ways, and neither one reaches
the renderer:

- `DROP_SECTION_CALLOUT_LABELS = True` (`orchestrator.py`) removes the labels from the
  `drawing_views` checklist, using `feature_classifier.refine_view_labels`. Landed at cache
  **v38**; current is v48.
- The cut-plane line and the `JZB_*` arrow blocks were never eligible at all —
  `COMPARABLE_ENTITY_TYPES` is `("text", "dimension")`, so a LINE or an INSERT is invisible to the
  differ, and the `diff_geometry` pass that once looked at bare shapes was deliberately removed.

`renderEntities` knows none of that. It draws the extracted payload, and the payload still holds
the labels, so the two subsystems disagreed about whether a section identifier is content.

**The reason to fix the canvas rather than the engine: the engine was right.** Which letter names
a cut says nothing about the part, and it re-letters freely between revisions. The section's
*contents* — the dimensions and callouts inside the view it names — are drawn and compared exactly
as before.

## The trap that makes this more than a one-line filter

**The sheet frame's border grid labels are lone letters too.** On this revision there are `A`
labels at both sheet edges, alongside `1`–`7` across. A rule that hides text equal to `A` erases
the drawing frame.

The backend hit the identical trap and records it — on M7452A1N01 the reference's "only `Ａ` texts
are two frame grid labels on layer WAKU". It escapes via a furniture-layer list and geometric zone
boxes. **Neither is available to the canvas**, and the furniture-layer list would not help anyway:
`is_furniture_layer` is documented as helping "only the AutoCAD side", and these iCAD/SolidWorks
sheets put the entire drawing on `NoLayerName_001`.

## The rule

**Provenance separates drawing content from sheet furniture when layer names cannot.** Model-space
geometry is projected onto the sheet through a paper-space viewport and carries
`properties.viewport_index >= 0`. Native paper-space furniture — frame, title block, tolerance
table, border grid labels — is left alone by the projector and keeps `NO_VIEWPORT` (`-1`).

Measured on M745221N01's revision:

| text | `viewport_index` | what it is |
|---|---|---|
| `A` (18.4, 271.7) | −1 | border grid label, left edge |
| `A` (411.4, 271.7) | −1 | border grid label, right edge |
| `A` (187.7, 98.8) | 0 | the cut arrow |
| `A` (142.6, 236.3) | 0 | cut arrow, already culled as `outside_viewport` |
| `A-A` (257.2, 100.5) | 1 | the section title |

Every tolerance-table number and every `1`–`7` grid label also sits at −1. The split is clean and
needs **no tuned constant** — which was the alternative, a "within N% of the sheet edge" margin
band fitted to one drawing.

Corollary worth keeping: `space` looks like the field for this and is not. The parser sets
`props["space"] = "paper"` *after* projecting, so model-space and paper-space entities both read
`paper`. It records the target space, not the origin. `viewport_index` is the one that remembers.

## Resolution

`apps/desktop/src/components/review/sectionCallouts.ts` identifies them, and `renderEntities`
skips them immediately after the existing `outside_viewport` cull — the same idiom, one line.
Two gates, mirroring `refine_view_labels` so the two implementations of one rule cannot drift:

1. A lone letter qualifies only when the same sheet carries the matching `X-X` designation. Both
   letters must match, so an `Ａ－Ａ` section does not sweep up an unrelated `Ｂ`. **A sheet with
   no designation hides nothing** — that is the property that makes it safe.
2. Only text projected through a viewport is eligible, including the designation scan itself, so a
   title-block string reading `A-A` cannot license hiding the border grid's `A`.

`HIDE_SECTION_CALLOUTS` turns it off, mirroring `DROP_SECTION_CALLOUT_LABELS`. Memoised on a
`WeakMap` keyed by the layers object, because the answer needs the whole sheet and
`renderEntities` reruns on every pan and zoom.

14 tests in `sectionCallouts.test.ts`. **Verified by removing the viewport gate: exactly the three
tests that depend on it fail** — the grid-label test, the paper-space-designation test, and the
missing-`viewport_index` test — so they guard the trap rather than restating the happy path.

### The census had to move, and how it moved matters

`tools/render_audit.py` reproduces the canvas HUD's `drawn/total`, so a renderer cull it does not
know about reads as **lost geometry** — the one thing the harness exists to detect. The port is
mirrored there, and the two culled entities go in their **own `section-callout` bucket** rather
than quietly shrinking `drawn`:

```
495 drawn + 2 section-callout + 3 outside-viewport + 18 not-drawable = 518
```

CLAUDE.md's pinned number moves 497/518 → 495/518 with that breakdown. *Folding a deliberate cull
into the denominator's shortfall is how a harness that detects missing geometry stops being able
to.* Any future cull gets a bucket.

## Second pass — the cut plane and its arrows

The labels went first; the cut-plane line and the arrow ticks followed the same day, on the same
gate. Getting there needed one more measurement, because **position does not separate a cut plane
from a part axis.** Both are `CENTER` linetype. On this sheet the cut segment sits **5.1** units
from its label and an axis centreline sits **7.3** from the *same* label — a 2.2-unit margin, and
any threshold inside it would be fitted to one drawing rather than derived from anything.

**The drafter already separates them, by colour.** Measured across every drawing in
`storage/uploads` carrying an `X-X` designation — **9 of 9** — the cut segments are a strict
minority of that sheet's `CENTER` lines (1–2 of them) in a colour distinct from the majority, and
the majority is the axis-centreline colour. So the rule reads the majority off the sheet itself
and treats the minority as the cut plane: **self-calibrating, no ACI index hardcoded**, and a tie
or a single-colour sheet yields nothing. On M745221N01 that is colour 8 against colour 4, which is
visibly grey against cyan on the canvas.

The apparatus hanging off the cut path is then pure coincidence, no classifier needed. In
projected paper units the arrow ticks straddle a cut vertex (midpoints **0.05** and **0.07** away)
and the label tails start on one (**0.28**, **0.3**), while the nearest thing that must survive —
the `6-9キリ` callout leader — is **46.9** away. Two orders of magnitude of daylight, so the 1.0
tolerance is a "these are the same point" epsilon, not a tuned threshold; anything from 0.5 to 40
gives the same answer. A vertex cap of 3 stops a long polyline that merely begins on the cut path
from being swallowed.

**The sweep is the real test, and it is not a unit test.** Across all 32 uploaded drawings: 23
cull nothing, 9 cull 8–10 entities each — always 2–3 text, 1–2 cut lines, 2 ticks, 2 tails — and
the maximum on any sheet is **10**. The two that would have been most dangerous both cull zero:
`c04d4a7c` has 1249 entities, 61 `CENTER` lines and dozens of lone letters, and `123d7dfc` has
2269 entities and a minority-colour `CENTER` line — neither carries an `X-X`, so the designation
gate holds them at zero. *A rule this shape cannot be trusted on the sheet it was written for; run
the sweep.*

⚠ The earlier concern that culling centrelines would disturb `viewDatums.ts` **was wrong, and is
worth recording as wrong**: the cull lives inside `renderEntities` and skips only painting.
`viewDatumsFromTransform` is fed separately from `entitiesFromLayers(layers)`, so it still sees
every centreline. Hiding ink and removing an entity from the payload are different operations, and
conflating them is what made the risk look bigger than it was.

## Deliberately not done

- **No backend property.** Stamping `section_callout` at extraction would let `render_audit` and
  the canvas share one source of truth, but it needs a re-ingest to reach existing drawings and
  there is no re-extract endpoint — only `upload_drawing`. The duplicated rule is the cheaper
  trade today; if a third consumer appears, move it.
- **No label-proximity gate on the cut line.** Colour already separates it, and the only honest
  constant available was the 2.2-unit margin above. If a minority-colour `CENTER` line that is not
  a cut plane ever appears on a sheet with a section designation, that gate is what to add — the
  hook is marked in `findCutPlaneLines`.
