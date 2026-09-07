---
title: Gotcha - The Worksheet Cannot Place a Dimension
type: gotcha
tags: [gotcha, eval-corpus, annotation, tooling, dimensions, presentation]
status: open — found 2026-08-17 while labelling; the safety net held, the display did not
date: 2026-08-17
cache-version: n/a — annotation tooling only, no comparison behaviour. No bump.
related: [Eval Corpus Annotation Guideline, Gotcha - drawing_views Was the Residual, Not the Views Box, Gotcha - The Differ Compared Text Only]
---

# Gotcha — the worksheet cannot place a DIMENSION, and prints it as out of scope

**Class:** a display that contradicts the rule it is displayed under · **Found:** 2026-08-17, while
labelling `M745227N01`

---

## Symptom

One row of the revision-only section reads:

```
| `REV-11C` | dimension | NoLayerName_001 | — | @? | ｔ |
```

No position, no zone. Under [[Eval Corpus Annotation Guideline]] a row belonging to no zone is
**out of scope and must not be labelled** — *"Anything outside the `views` box that belongs to no
zone… If you believe a real change sits there, that is a zone-detection bug: record it in notes and
file it, do not label it as a comparison finding."* Read at face value, this row says *skip me*.

It is not out of scope. `REV-11C` is a `ｔ` = 5.0 thickness dimension, present on the revision and
absent from the reference, whose `def_point` (226.9, 86.5) is **inside the views polygon** — and
DIMENSION is one of the two members of `COMPARABLE_ENTITY_TYPES`. It was labelled `ADDED` /
`drawing_views`, and the engine misses it.

## Cause

`tools/eval_corpus.py` resolves an entity's position from two keys:

```python
def anchor_of(entity: "EvalEntity") -> list[float]:
    return entity.geometry.get("insert") or entity.geometry.get("location") or []
```

A DIMENSION carries neither. Its geometry is `def_point` / `ext1_point` / `ext2_point` /
`text_point`, so `anchor_of` returns `[]`, and both consumers degrade:

- `describe()` prints `@?` for position and `—` for zone (`cmd_worksheet`, ~line 968);
- `zone_of()` → `zone_containing(..., [])` → `None`.

## What did NOT go wrong, and it matters

**The row was not hidden, and that is by design.** `triage_row` refuses to exclude on missing
information, and says so:

> *"The only rule that matters here: **this never excludes on uncertainty.** With no template, or
> an entity carrying no usable coordinate, the row goes to `review`. Grouping a row as 'not a
> finding' is a claim that the guideline covers it, and a guess is not that claim — a wrongly
> excluded row is a miss the annotator never sees, which is precisely the quantity the whole corpus
> exists to measure."*

`len(anchor) < 2` returns `BUCKET_REVIEW` explicitly. So the safety net worked exactly as written:
the row reached the annotator's to-review list rather than being grouped away.

**The defect is entirely presentational, and it is still a real defect**, because the columns the
annotator reads say the opposite of what the bucket decided. The tool put the row in front of a
human *and* labelled it with the two marks the guideline treats as "ignore this". Getting it right
required opening the payload — which is not a workflow, it is a rescue.

⚠ This is worth stating precisely because the first reading of this bug was wrong: it is **not**
"the worksheet hides a comparable entity". The row is shown. What fails is that its display invites
a judgement the triage logic deliberately declined to make.

## The rule

**A safety net that routes an item to a human is only as good as what the human is shown about
it.** `triage_row` refuses to guess and then hands the annotator a row that *looks* like a settled
"out of scope" — the caution is discarded at the presentation layer. When a system deliberately
represents uncertainty, the uncertainty has to survive to the surface: `—` should read
*"zone unknown"*, not be indistinguishable from *"no zone"*.

## Fix directions, none taken

- **Teach `anchor_of` about dimensions**: fall back to `def_point`, then `text_point`. One line,
  fixes position and zone together, and makes the triage bucketing *more* accurate rather than only
  the display. ⚠ Check it against the engine's own scoping first — `SpatialDiffer` and
  [[Gotcha - Dimension Scoped by Its Span Midpoint]] use a **span midpoint** for dimensions, not
  `def_point`, and the worksheet showing a different point than the engine scopes by is its own
  small drift.
- **Distinguish the two blanks in the display**: an entity with no resolvable anchor should print
  something other than the `—` used for "resolved, and in no zone".

## The wider point about this worksheet

It is a *naive text-set difference*, deliberately — that is what keeps the engine's own misses
visible. But annotators should know its blind spots, because they are structural and there are now
three, all found in two days of labelling:

1. **Geometry-only changes.** Both labelled pairs added an isometric view carrying **no text**;
   neither appears in any text section. Only the entity-count delta hints at them.
2. **NFKC-equal content that moved.** Grid labels and `Ｇ` markers are equal after normalisation, so
   a relocation never prints.
3. **OCR-derived title-block fields.** The worksheet diffs *entity* text; title-block fields come
   partly from OCR, so a field difference with no entity behind it can never appear — see
   [[Gotcha - A Fixed OCR Misread Came Back Through the Title Zone]].

**Read the entity-count delta table and open the payload when a row looks odd.** Both labelled
pairs produced a finding that existed only there.

## Guarded by

Nothing. A test asserting that a DIMENSION row renders a real position and zone would pin the fix;
`tests/test_eval_corpus.py` is the home.
