---
tags: [gotcha, title-block, upper-left, field-extraction, zone-scoping, guards, comparison-engine]
status: fixed
cache-version: v45 -> v46
date: 2026-08-12
---

# Gotcha — The Lowest Row Is Not the Values Row

> [!WARNING] Reported from a live review of `M745227N01`:
> **`[CHANGED] Title Block (Upper-Left) T. Q'ty / 総製作個数: 4 ロール：12 (2x6台) vs 16組`** — a
> production-count note compared against a quantity, with the owner's summary of it:
> *"why would you pair a value that doesn't match?"* The answer is that **nothing in the path
> ever asked.** The extractor took the lowest row of the table and called it the values.

## The chain, every link measured

1. **The zone box over-reaches.** The only stored zone template is `aspect-1.374` flagged
   `is_default`; this sheet is **1.414**, so the fallback's fractions scale onto a
   differently-shaped sheet — precisely the caveat in
   [[Gotcha - Global Default Zone Template & the Aspect Caveat]]. The reference's
   `title_upper_left` box lands at **(75.22, 762.99, 313.71, 862.25)**: its bottom edge is at
   **y=762.99** while the table's value row sits at **y=822**.
2. **A note falls inside it.** `4 ロール：12 (2x6台)` at y=767.5 becomes the lowest band.
3. **`extract_title_ul_kv` takes `bands[-1]` as the values row.** So the note *is* the values
   row, and the real values — `45 / 227 / 16組 / 0` at y=822 — are demoted to a **header** band.
4. **The note inherits a field name by 2.4 units.** Its x=179.23 sits between two columns:
   28.27 from `総製作個数`/`T. Q'ty` at 207.50, and 30.66 from `コードNo.`/`Part No.` at 148.57.
   The nearer one wins, so a note about roll counts becomes the quantity field.
5. **`match_title_ul_pairs` pairs it across the sheets** on the shared `T. Q'ty` token, and
   `compare_values` calls it CHANGED.

The reference and revision boxes for the same table, side by side, are the whole story:

| | box | bands inside it |
| :-- | :-- | :-- |
| reference | (75.22, **762.99**, 313.71, 862.25) | headers ×2, **values**, *a note* |
| revision | (25.07, **254.33**, 104.57, 287.42) | headers ×1, **values** |

## What the report was the visible corner of

The finding named one field. The A/B — same pair, same engine, `UL_BAND_GAP_OUTLIER_FACTOR`
raised so high the cut can never fire — shows the reference side of the **entire** upper-left
table was blank:

```
- [CHANGED] Title Block (Upper-Left) T. Q'ty / 総製作個数: 4 ロール：12 (2x6台) vs 16組
- [ADDED]   New element traced/added: ４ロール：１２（２×６台）
- [MATCHED] Title Block (Upper-Left) Unit No.:   NONE vs 45
- [MATCHED] Title Block (Upper-Left) Part No.:   NONE vs 227
- [MATCHED] Title Block (Upper-Left) 在庫棚入庫:  NONE vs 0
+ [CHANGED] Edited and relocated: '4 ロール：12 (2x6台)' -> '４ロール：１２（２×６台）'
+ [MATCHED] Title Block (Upper-Left) Unit No. / ユニットNo.:  45 vs 45
+ [MATCHED] Title Block (Upper-Left) Part No. / コードNo.:    227 vs 227
+ [MATCHED] Title Block (Upper-Left) T. Q'ty / 総製作個数:     16組 vs 16組
+ [MATCHED] Title Block (Upper-Left) Stock Q'ty / 在庫棚入庫:  0 vs 0
```

**Three of the four fields read `NONE` on the reference and still displayed as MATCHED**, because
the bilateral corroboration guard (`orchestrator.py`, added for a different failure) searched the
other side's UL region, found the value, and upgraded them. The guard did its job and, in doing
it, **hid a totally broken extraction behind three green rows**. Only the fourth field surfaced,
and only because the note happened to land nearest that column.

**Rule: a guard that rescues a value tells you the extractor failed. Count the rescues.** Three
`NONE`-on-one-side corroborations in one small table is not a set of near-misses, it is a
diagnosis — and nothing was counting.

The bogus `[ADDED] ４ロール：１２（２×６台）` came from the same root: the reference's copy of that
line had been consumed as a "structured value" (`_collect_structured_text_values` suppresses those
from the spatial pool), so the differ saw the revision's copy alone. With the fix it pairs with
its own counterpart and reports what actually changed — half-width to full-width — exactly as the
neighbouring `2 ロール` line already did.

## The fix: two structural signals, both required

`ul_value_band_index` (module-level and pure, like `match_title_ul_pairs` before it) replaces
`bands[-1]`. A band is dropped only when it **both**:

1. **fails to fill the table's columns** — a values row covers ≥ half of them; the real one
   covers 4 of 4, the note 1 of 4; and
2. **sits at an outlying row gap** — the table's own rows are 9.9 and 19.9 apart, the note 54.5
   below.

Requiring both is what protects a legitimately **sparse** values row — one cell filled, three
empty — which fails (1) but sits at the table's own pitch. Dropping that would promote a header
row to being the values row, which is worse than the defect being fixed. At least two bands
always remain, because a table with no header above its values is not one this extractor reads.

**Three things worth not rediscovering:**

- **The factor window is narrow and was measured, not chosen.** The stray note is 2.74× the
  table's largest row gap; the gap from the stacked bilingual header to the values row is 2.01×
  the gap between the two header labels. Anything in (2.01, 2.74) separates them —
  `UL_BAND_GAP_OUTLIER_FACTOR = 2.5`, with +9.5% / −19.6% of margin. The 2.01 is what makes it
  tight: 9.9 is two labels *inside one cell*, not two rows, so it understates the real pitch.
- **Columns are found by the shape of the gaps, not a distance.** The two exporters differ ~3×
  in coordinate scale: the reference's four columns are ~60 apart, the revision's ~20, and the
  revision stacks two labels ~1 apart inside each cell. `_ul_columns` splits wherever a step
  exceeds 25% of the largest step, and both resolve to 4 columns.
- **The walk goes top-down, and popping from the bottom was wrong.** Written first as "pop the
  last band while it looks stray", it let the yardstick eat itself: a second stray note 24.2
  below the first was judged against the first's own 54.5 gap and kept. Caught by a test, not by
  inspection.

## Measured

- **Eval baseline byte-identical to v45** apart from the version stamp — P 0.9796 (48/49),
  R 0.8727 (48/55), F1 0.9231, attribution 1.00 (48/48). Committed as `baseline-v46.json`.
  It has to be inert there: swept across every stored sheet, **the value band moves on
  `M745227N01`'s reference and on no other side of any other drawing** — and `M745227N01` is one
  of the six pairs skipped for having no labels.
- On the affected pair: reported findings **19 → 18**, two false ones removed, one real one
  gained, four fields restored.
- `pytest` **1005 passed, 3 skipped** (11 new in `tests/test_title_ul_value_band.py`).
- Cache **v45 → v46**.

## Two more rules, from the owner's follow-up

> *"zone box isn't a feature we could rely on in the future… If that value was inside the zone box
> but no another value to compare then leave it, some zone box view might be the one who needs
> it."*

Both landed under the same cache bump, both aimed at the same root, and both leave the templated
eval byte-identical.

### 1. Claim only what can be compared — `partition_ul_pairs`

A value with **nothing on the other side to compare it against** is released: dropped from this
extractor's output *and* from the suppression net, leaving it to whichever zone covers it. That
second half matters as much as the first — claiming a value feeds
`_collect_structured_text_values`, which suppresses that text sheet-wide, which is how one
over-reaching box produced both a false CHANGED *and* a false ADDED for the same line.

⚠ **Release is conditional, and the condition is the whole safety of it.**
`title_upper_left` is in `VIEWS_EXCLUDED_ZONES`, so content in that box is subtracted from the
`views` pool and no other pass is scoped to it. Releasing with no catcher would delete the value
from the comparison entirely — a silent false negative. So release happens only when another
zone's shape actually covers the value's own coordinates. **Zones overlap, and that is what makes
it possible at all**: the released roll-count line lands inside `notes` on the reference and comes
back as a real CHANGED against its revision counterpart. With no catcher, the one-sided report
stands: a wrong finding is visible, a missing one is not.

### 2. Content that belongs to another zone is not this table's data

The value band is now chosen after subtracting the shapes of the zones that own their content
outright — `notes`, `bom`, `title`, `tolerance`, `iso`, `shim`. **Never `views`**: it is the
drawing *area*, it legitimately overlaps every other zone, and including it emptied the table
completely on all three pairs tested.

This is the only signal that separates a notes line from a sparse table cell, and it is needed
because neither geometric signal can. Measured on `M745227N01`'s revision with detection and no
template: the box swallows the whole notes block, whose lines are **9.6 to 17.0 apart against the
table's own 10.9 pitch** — so no gap is an outlier and the row-pitch test is blind — while their
left margin at x=55.0 sits **6.0** from the `コードNo.` column centre, so column alignment reads
them as cells. The result was `[CHANGED] Part No. / コードNo.: 227 vs 完成時、バリ、キリ粉はなきこと`
— a sentence about deburring compared against a part number.

⚠ **And the subtraction needed its own guard, added after the unguarded version was measured
doing real damage.** On the same sheet's *reference*, detection puts the `tolerance` box over the
entire upper-left table, so every entity was dropped as "owned by tolerance" and the table
produced **no fields at all** — silently, on a checklist whose whole purpose is to show those
fields were checked. **Correcting one wrong box with another wrong box compounds the error.** The
subtraction is now allowed only when what survives it still spans two rows; when it does not, the
foreign claim was the wrong one and the unfiltered set stands.

### Measured, detection-only — the configuration a new pair actually gets

| pair | before | after |
| :-- | :-- | :-- |
| M7452A0N01 | 2 false CHANGEDs (`2A0 vs 完成時…`, `0 vs Ｃ１`) + 2 fields reading NONE | **4 fields, all MATCHED on real values** |
| M745203N01 | UL rows built from notes lines | clean; 2 notes released to their zone |
| M745227N01 | 4 bogus/NONE rows | 1 bogus row left (below) |

## What is still not fixed

**The zone box is still wrong.** Making the extractor robust to an over-reaching box is not the
same as the box being right, and a template stretched onto a different aspect ratio will keep
producing boxes like this one. See
[[Gotcha - Every Published Baseline Measures a Configuration Users Do Not Get]] for why
hand-alignment is not the answer either.

**One bogus row survives on `M745227N01` detection-only:**
`Stock Q'ty / 在庫棚入庫: 0 vs ２ロール：　４（２×２台）`. **Geometry is exhausted on it** — that line
sits inside no other zone (it is to the *right* of the notes block), at the table's own row pitch,
and within `max_pair_dist` of a column. Every signal used here says "table cell".

What separates it is **content**: across the whole corpus every upper-left value is ≤3 characters
(`45`, `227`, `16組`, `2A0`, `0`, `4`, `24`) while the intruders are 9–17 characters carrying a
full-width `：`. That is a **value-plausibility** rule, and it is deliberately not added here
without a decision, because [[Gotcha - Unrelated Text Paired as CHANGED]] applied exactly this
class of fix (a 0.40 similarity floor) to `diff_views` and **explicitly excluded the field-paired
title block** — fields pair by label, and a genuine change can be arbitrary. A length ceiling
would also be the first rule in this extractor keyed on how a value *looks* rather than where it
sits. Worth doing, worth deciding on purpose.

## See also

- [[Gotcha - Title Block QTY Reads the Upper-Left Table]] — the same table, the opposite
  direction: the *bottom* title block reaching *up* into this one. Both are unbounded searches
  that never asked whether what they found belonged to them.
- [[Gotcha - Title Upper-Left Double-Reported by Scale]] — why `match_title_ul_pairs` matches on
  a shared header token, which is what carried this note across to the revision's field.
- [[Gotcha - Unrelated Text Paired as CHANGED]] — the same species in `diff_views`, fixed there
  with a similarity floor. That fix explicitly excluded the field-paired title block, which is
  this path; the floor would not have caught this one either, because the pairing happened
  before any text comparison.
- [[Gotcha - Global Default Zone Template & the Aspect Caveat]] — the box that made it possible.
- [[Gotcha - A Swallowed AttributeError Made a Write Path a Permanent No-Op]] — the other
  recorded case of a defensive mechanism turning a defect into silence.
