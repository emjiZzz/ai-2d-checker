---
title: Gotcha - Title Block QTY Reads the Upper-Left Table
type: gotcha
tags: [gotcha, title-block, upper-left, field-extraction, duplicate-row, zone-scoping, eval-blind-spot]
status: resolved
date: 2026-08-05
---

# 🔥 Gotcha — One cell, two cards: the title block's QTY field reads the *upper-left* table

Reported from a live review session (2026-08-05). The `title_block` checklist showed **two
cards carrying the same value** `16組`, both MATCHED, while the canvas showed **one** marker:

```
QTY (QUANTITY)              16組   MATCHED
T. Q'TY / 総製作個数         16組   MATCHED
```

Both cards resolved to the same marker because they are the same physical cell, read twice by
two different extractors.

## Not the sibling defect — check which one you have

This looks like [[Gotcha - Title Upper-Left Double-Reported by Scale]] and is **not** it. That
one is a failure *within* one extractor (`extract_title_ul_kv` fails to pair a field across the
two drawings, so one value is reported on both sides). Telling them apart:

| | sibling defect | this defect |
| :-- | :-- | :-- |
| duplication is | within `extract_title_ul_kv` | across two extractors |
| both rows sit in | the upper-left table | one in the title block, one in the UL table |
| natural status | REMOVED + ADDED, flipped to MATCHED by the corroboration guard | MATCHED + MATCHED outright |
| row labels | the same field, two spellings (`コードNO.` / `PART NO.`) | two *different* field names (`QTY` / `T. Q'TY`) |

A duplicate MATCHED row is the shared signature. The label pair tells you which fix applies.

## Root cause: the bottom title block searches for the upper-left table's own header

`title_block_extractor.py` resolves QTY with:

```python
f_qty, qty_c = resolve_field("QTY", ["T. Q'ty", "T. Q’ty", "総製作個数"], "below", ...)
```

Those label patterns *are* the upper-left table's column header. `resolve_field` falls through
to a proximity search over whatever entity list it was handed — and it was handed nearly the
whole sheet, because `keep_for_title_extraction` (in `orchestrator.py`) excluded only the
**tolerance** box. So the search walked hundreds of units up the sheet, found the UL table's
header, and read that table's cell as the bottom title block's QTY.

Measured on the reference sheet of the `M7452A0N01` eval pair — the two zones are nowhere near
each other, which is what makes the reach so clearly wrong:

| | `title` bbox | `title_upper_left` bbox | `T. Q'ty` label insert |
| :-- | :-- | :-- | :-- |
| reference | y 39 – 299 | y 680 – 715 | (172.9, **702.4**) — in UL, not in title |
| revision | y −2.7 – 101 | y 201 – 289 | (69.2, **280.6**) — in UL, not in title |

Both extractors then reported it, and `build_title_block_table` concatenates the title-block
table and the UL table into one `title_block` checklist, so both rows land side by side.

## Fix — scope title extraction out of the zone that has its own extractor

`keep_for_title_extraction(entity, tolerance_bbox, title_bbox, title_ul_bbox=None)` now
excludes the upper-left box the same way it already excluded the tolerance box, and for the
same reason: **both zones are owned by another extractor, so anything the title-block field
search finds inside them is a second reading of an already-reported cell.**

The guard is unchanged and load-bearing: drop an entity only when it is in an excluded box
**AND NOT** in the title box. That is what stops an over-wide detected box from blanking the
whole title block (the original reason it exists — see
[[Gotcha - Title Field Read Across a Ruled Cell Boundary]]), and it also means a sheet whose
bottom title block genuinely carries its own quantity cell keeps it.

Preferred over deleting the QTY field from the title-block extractor, because it fixes the
*class*: any other UL header the title extractor happens to search for is now out of reach too.

### Measured effect

| | reference | revision |
| :-- | :-- | :-- |
| entities fed to title extraction | 434 → 422 | 444 → 419 |
| fields changed | **QTY only**, `'4'` → `'NONE'` | **QTY only**, `'4'` → `'NONE'` |
| other 15 title fields | byte-identical | byte-identical |

End to end through `generate_deterministic_candidates`: **28 candidates → 27**. The candidate
that disappeared was an exact twin of the one that remains — same status, same feature, same
text, *same coordinates* `[75.25, 273.0]`. Identical coordinates are the proof it was one cell.

No `QTY: NONE vs NONE` row is left behind: `marking_builder.py::inject_title_block_markings`
only emits a marking when at least one side is non-NONE, so the card is gone rather than
emptied. The fixed-shape markdown table in `utils/text.py` still prints a `NONE | NONE |
MATCHED` row, which is the pre-existing behaviour for every unread field (UNIT NO, PART NO,
STOCK QTY already do this) and does not affect the zone's status.

## Negative result — **the eval cannot see this defect**

Worth more than the fix. `tests/fixtures/eval/baseline-v38.json` reports `duplicates: 0`, and
it reported `duplicates: 0` while this bug was live. The scorer's duplicate counter is
**structurally blind** to this class:

```python
# runner.py
predictions = [Prediction.from_candidate(c) for c in candidates
               if str(getattr(c, "status", "")) != "MATCHED"]
```

A prediction is a candidate whose status is not MATCHED — correct for precision/recall, since
counting MATCHED checklist rows would put precision near zero on a clean run. But **both
duplicate cards here were MATCHED**, so neither ever reached the scorer. Every duplicate-row
defect found so far (cache v13/v16, v39, and this one) surfaced as a *MATCHED* pair, which is
exactly the population the eval discards.

So the eval run over 36 pairs — every metric byte-identical to the v38 baseline, F1 0.7129,
precision 0.7826, recall 0.6545 — is real evidence of **no regression** and is **not** evidence
that the duplicate is gone. That came from the candidate-level probe above.

Do not cite `duplicates: 0` as coverage for duplicate checklist rows. Measuring them needs a
check over the MATCHED population — two rows in one zone with the same normalized value and the
same coordinates — which does not exist yet.

## Guarded by

`tests/test_title_input_filter.py`:
- `test_upper_left_table_cell_is_dropped_from_title_extraction` — the `T. Q'ty` label at its
  measured insert `(172.9, 702.4)`, plus its value cell, are dropped.
- `test_upper_left_exclusion_never_blanks_the_title_block` — an over-wide UL box must not
  delete real title content.
- `test_upper_left_bbox_defaults_to_no_exclusion` — sheets with no detected UL table are
  unaffected.

## Traps

- Cache **v39 → v40**. A v39 entry still carries the duplicate QTY row.
- **The OCR path is not covered by this fix.** `resolve_field` prefers `ocr_results["QTY"]`
  when Gemini returns one, and on a grounding miss it *still returns the OCR value* with no
  coordinates. If a title-block crop overlaps the UL table, QTY can be repopulated from OCR and
  the duplicate returns — ungrounded, so it would show a card with no marker. QTY was `null` in
  the cached OCR for both sides of the measured pair, so this path is untested here. See
  [[Gotcha - Mislocated OCR Crop and Ungrounded Misreads]].
- n≈1 pair, one customer's sheet standard. The fix rests on `title` and `title_upper_left` not
  overlapping, which held with a wide margin on both sides here. On a standard where the bottom
  title block sits near the UL table, the "also in title" guard would preserve the duplicate.
