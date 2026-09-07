---
title: Gotcha - Drawing Number Segments Reported as Separate Fields
type: gotcha
tags: [gotcha, title-block, checklist-noise, dwg-no, false-negative-risk, name-collision]
status: resolved
date: 2026-08-05
---

# 🔥 Gotcha — Four checklist items for one drawing number

Reported from the same live review session as
[[Gotcha - Title Block QTY Reads the Upper-Left Table]] (2026-08-05). The `title_block`
checklist carried four separate items for one identifier:

```
| MACHINE CODE / UNIT CODE        | NONE       | NONE | MATCHED    |
| DWG NO (Drawing Number)         | M745203N01 | NONE | MISMATCHED |
| UNIT NO (Unit Number)           | NONE       | NONE | MATCHED    |
| PART NO (Part Number)           | NONE       | NONE | MATCHED    |
```

The bottom title block's DWG No. cell is **ruled into sub-cells, each with its own header**, and
the number is their concatenation:

| segment | header on the sheet | in `M745203N01` |
| :-- | :-- | :-- |
| `M745` | Machine Type / Mach. code | prefix |
| `203` | Unit No. / Unit Code | middle |
| `N01` | Part No. | suffix |

So three of the four items cannot change without the fourth changing too. On the live pair all
three read `NONE` on both sides — three permanently-empty rows plus a card label that advertised
five field names (` DWG. No. /  Machine Type /  Unit No. /  Part No. /   Branch`) for one value.

## The name collision that makes this dangerous

**The upper-left metadata table has its own `Unit No.` and `Part No.` columns, and those are
genuine standalone fields.** They are not segments of anything and they keep their own items.

The trap is concrete rather than theoretical: on the live KEMCO sheet the upper-left `Part No.`
reads **`203`** — which really *is* the middle segment of `M745203N01`. Point the suppression at
the upper-left table and it will call that field corroborated and delete it.

The two are kept apart structurally. Upper-left rows are built by `extract_title_ul_kv` into the
separate `title_ul_table`, tagged `zone: 'title_upper_left'` and prefixed
`Title Block (Upper-Left)` in their details; they never pass through `build_title_block_table`
or `inject_title_block_markings`. The suppression is keyed on `extract_title_block`'s own dict
keys (`MACHINE CODE` / `UNIT NO` / `PART NO`), which the upper-left path never produces.

## Fix

`utils/text.py` gains `COMPONENT_OF_DWG_NO_FIELDS` (field → expected position) and
`is_component_of_dwg_no(value, dwg_no, position)`. A component row is dropped only when the
DWG No. is shown to account for it, on both sides. `marking_builder` applies the same rule to
the canvas cards and imports it rather than restating it, so the card list and the checklist
table can never disagree about what was dropped. The DWG No. card's label is shortened to
` DWG. No.` — leaving the sub-header list in place would name rows the reviewer can no longer
find.

### Two things that are deliberately *not* unconditional

**1. Corroboration is checked, not assumed.** Suppressing a component outright would mean that
on any sheet where the DWG No. fails to extract, a changed segment is reported by nothing at
all. That is not hypothetical — **the live KEMCO revision reads `DWG NO: NONE`.** A component
the DWG No. cannot vouch for keeps its row. This project's largest known measurement gap is
that false negatives have never been measured (see the gap analysis), so the default is to keep
a row that cannot be *shown* redundant.

**2. Matching is positional, not containment.** The first implementation used `value in dwg_no`
and its own test caught it: `45` is a substring of `M745`203N01 without being a segment of
anything. That is the identical failure mode as
[[Gotcha - Title Field Read Across a Ruled Cell Boundary]], where a `Previous Dwg. No.` of `1`
was corroborated against the `1` inside `M7452A1N01` and shipped as a green tick. So
`MACHINE CODE` must be a **prefix**, `PART NO` a **suffix**, and `UNIT NO` strictly interior.
The infix test is the weakest of the three — the middle segment has no anchor of its own — and
is acceptable only because `MACHINE CODE` is the sole one of the three the spatial extractor
ever populates: `UNIT NO` and `PART NO` are not in `extract_title_block`'s returned dict at all
and reach it only via the block-attribute path.

## Measured effect

Bottom title-block checklist: **11 rows → 8**, on both the live KEMCO pair and the eval pair.
The four upper-left rows are untouched (`Unit No.`, `Part No.`, `T. Q'ty`, `Stock Q'ty` all
still present). Eval over 36 pairs: **every metric byte-identical to the v38 baseline** —
precision 0.78, recall 0.65, F1 0.713, macro 0.750, attribution 0.806.

As with the QTY duplicate, that equality is evidence of **no regression** and not evidence about
the noise reduction, for the same structural reason: these rows were `MATCHED`, and `runner.py`
drops every `MATCHED` candidate before scoring. See the eval blind-spot section of
[[Gotcha - Title Block QTY Reads the Upper-Left Table]].

## Guarded by

`tests/test_dwg_no_component_rows.py` (18 tests), notably:
- `test_position_rejects_a_match_that_straddles_a_segment_boundary` — the `45` case that a
  containment test gets wrong.
- `test_an_uncorroborated_component_keeps_its_row` and
  `test_a_component_that_disagrees_with_the_drawing_number_keeps_its_row` — the false-negative
  guards.
- `test_a_value_that_is_a_dwg_segment_is_still_a_real_upper_left_field` and
  `test_upper_left_fields_are_produced_by_a_different_path` — the name collision.
- `test_card_and_table_agree_about_what_was_dropped` — the two suppressions share one rule.

## Traps

- Cache **v40 → v41**. A v40 entry still shows the three component rows and the long card label.
- The DWG No. now carries these segments alone, and **it is the field that fails to extract on
  the live revision**. Fixing that read is separate work; until it lands, a sheet whose DWG No.
  is NONE falls back to showing whichever components did extract, which is the intended
  behaviour but is not the same as reporting the number.
- `Dir.` appears in the sheet's own sub-cell headers but nowhere in this codebase; the engine's
  label enumerated `Branch` instead. Do not go looking for a `Dir.` field.
