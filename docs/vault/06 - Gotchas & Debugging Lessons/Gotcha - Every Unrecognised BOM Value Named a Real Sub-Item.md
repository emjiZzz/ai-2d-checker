---
title: Gotcha - Every Unrecognised BOM Value Named a Real Sub-Item
type: gotcha
tags: [gotcha, checklist, taxonomy, bill-of-materials, manual-check, classification, false-confidence]
status: fixed
date: 2026-09-01
---

# 🔥 Gotcha — every BOM value the rules could not place was labelled "Material Specification"

Reported from a live Manual Check panel on a parts drawing. The Bill of Materials card read:

| Sub-item | Contents |
| :--- | :--- |
| Material Type | `SS400` → `SS400` ✓ |
| **Material Specification** | `6×⌀145` → `6×⌀145`, **`0.78` → `0.78`**, **`0.41` → `0.39`** |
| Quantity | ⚪ Pending |
| **Material Weight** | ⚪ **Pending** |

`0.78` and `0.41`/`0.39` are **weights** — the `素材重量Kg / Material Wt(kg)` and
`仕上重量Kg / Finished Wt(kg)` cells. The one sub-item that should have held them reported
*Pending*, meaning nothing had been checked there, while the values themselves sat one row up
wearing a heading no human had chosen.

---

## 🎯 The cause: a catch-all that named a real bucket

`comparisonTaxonomy.inferFeatureKey`'s `bill_of_materials` branch ended:

```ts
    return 'material_specification';
```

Every one of the six sibling branches has a default too, and every other one is defensible —
`notes_section` defaults to `standard_notes` because a note-zone finding **is** some kind of
note, and `feature_classifier.classify_notes_feature` argues exactly that in its docstring. The
BOM branch's default was not of that kind. A BOM cell is not "a kind of specification"; the
column set is `No. / 材質 / 材料寸法 / Q'ty / 素材重量 / 仕上重量 / Remark`, and
*Material Specification* is one column among seven.

> [!IMPORTANT] The rule.
> A classifier's fallback may name a real category only when membership in that category is
> **implied by reaching the fallback at all**. Otherwise the fallback is `other`. The backend
> counterpart already said so and had said so all along:
>
> > Every function here degrades to `taxonomy.OTHER_FEATURE_KEY` on no confident match — never
> > guesses past what the pattern actually supports. — `feature_classifier.py`
>
> `normalize_feature` repeats it: *"never guesses, never raises… a near-miss intentionally falls
> to `other` rather than risking a wrong bucket silently pretending to be confident."*

**This is the expensive failure shape, not a cosmetic one.** A missing row is visible. A wrong
row is not: it renders identically to a right one, so the engineer has no signal that the
classification failed, and the panel's whole job is to tell them what was checked and where.

---

## 🎯 The second cause: the weight rule could never fire

Moving the default to `other` is only half a fix — it stops the lie, it does not put the weights
anywhere. They had no rule that could match them:

```ts
if (/\b(kg|g|weight|wt)\b/i.test(clean) || /重量|素材重量|仕上重量/i.test(clean)) …
```

**A BOM weight cell contains `0.78` and nothing else.** The unit lives in the column *header*
(`素材重量Kg / Material Wt(kg)`), never in the cell, so no cell this rule was written for exists
in the corpus. It was also broken for the case it *was* written for: `\bkg\b` does not match
`0.78kg`, because there is no word boundary between `8` and `k`. Simultaneously too loose and
too tight.

The signal that does exist is the shape of the value, and the backend was already reading it —
`marking_builder.inject_bom_markings` normalises those two columns with `float()` and a
`\.\d{2}$` match. A **bare decimal** is a weight; a bare integer is not. Anchored (`^\d*\.\d+$`,
not a search), so a specification like `6×145.5` cannot be claimed by it.

### ⚠ What is still unresolvable from text, and is left alone

A bare **integer** is equally the `No.` column and the `Q'ty` column. Both are small counting
numbers and nothing in the string separates them — only the cell's *column* does, and a manual
marking has no column. It is left on `quantity`, which is where it already went, with the
ambiguity written down rather than quietly re-decided. **The backend does not have this problem
and should not be made to guess like the frontend:** it tags from the column directly.

---

## 🔴 The same defect on the backend, in the mirror image

`marking_builder.bom_feature_map` tags each BOM column, and its comment explained itself in good
faith:

> DWG_NO/TITLE/CODE/DIMENSION have no dedicated taxonomy feature for their exact meaning and
> fall to OTHER except CODE, which maps to `material_specification` as the closest real match.

Both halves were wrong, and `table_extractor.py` is where you can read that off:

| col_key | built from | header on the sheet | holds | was tagged | is now |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `CODE` | `MATERIAL` / `材質` | `材質 / Code` | `SS400` | `material_specification` | **`material_type`** |
| `DIMENSION` | `SIZE` / `寸法` / `型式` | `材料寸法/型式 / Dimension` | `6×⌀145` | *(unmapped → `other`)* | **`material_specification`** |

So the taxonomy had an exact item for each column and the map named neither. The consequences
are the two shapes this vault keeps recording:

1. **`material_type` had no producer anywhere in the backend.** Nothing could assign it, so it
   rendered *"No changes detected."* on every audit this system has ever run — a check that
   never ran, reporting clean. That is exactly
   [[Gotcha - A Checklist Item With No Producer Reported Clean]], except this one was not
   declared in `taxonomy.DEFERRED_FEATURES`, so it did not even get the *"Not yet supported"*
   treatment that tells a reviewer not to trust the card.
2. **The material name and the material size were one bucket apart and one bucket adrift** — the
   two columns an engineer checks against each other.

⚠ The frontend's text heuristic happened to put `SS400` under Material Type, so the *manual*
panel looked right for that row while the AI checklist did not. Two paths, two rules, one of
which had learned something — the drift shape from `CLAUDE.md`'s DRY section, arriving in the
one place where the two vocabularies (columns vs. text) genuinely cannot share an implementation.

---

## 🔍 Found while fixing it: `⌀` was in none of the character classes

The regression test for `6×⌀145` failed the moment the catch-all stopped covering for
everything, and it failed for an unrelated reason.

`cleanCadText` / `normalizeEntityValue` transcode the DXF escape `%%c` to **U+2300 ⌀**, and that
is the character that reaches every classifier. Three of them were written against `[ØøφΦ]` —
U+00D8, U+00F8, U+03C6, U+03A6 — which contains **none** of it:

- `inferFeatureKey`, BOM branch — `6×⌀145` did not read as a material size;
- `inferFeatureKey`, `drawing_views` branch — `⌀145` did not read as a hole property, and fell
  through to `dimensions`;
- `manualCheckCategories.inferCategoryForEntity` — both gaps again.

Every one of them still returned a plausible answer from its own catch-all, which is why none of
this had ever been reported. `entityPicking.ts` had the complete set the whole time
(`DIAMETER_MARKS = /[⌀øØφϕф]/g`) because comparing two spellings of one dimension is its entire
job — **one module had already paid for this and the others restated a shorter list.**

Now `utils/cadGlyphs.ts` holds `DIAMETER_CHARS` and all four sites derive from it.

> [!IMPORTANT] The general rule, and it is the DRY one.
> A character class describing how a sheet *spells* something is a rule, not a literal. Four
> copies of it do not fail loudly when they disagree — they classify the same string into
> different buckets and keep rendering.

---

## ⚠️ Making a classifier honest can DELETE rows — check every consumer first

`other` is a real answer, so every consumer must have somewhere to put it. Before this change
`inferFeatureKey` could not return `other` for any of the six known categories — every branch
had a naming default — so no caller had ever been exercised on it:

| consumer | before | now |
| :--- | :--- | :--- |
| `useComplianceReportExport` (PDF detail) | already had a `· Other` section for leftovers | unchanged |
| `ManualMarkingList` (the panel in the screenshot) | rendered `COMPARISON_TAXONOMY[key]` only — **would have dropped the row silently** | renders the Other bucket once it is populated |
| `computeEngineeringMatrix` (PDF summary + tallies) | walked named sub-items only — **`other` was in no row and no total** | scores an Other item when one is populated |

The matrix hole was **pre-existing and independent**: the backend has always tagged `DWG_NO` and
`TITLE` as `other`, so an assembly-drawing discrepancy in either column was already missing from
the summary, and a discrepancy missing from the summary reads as a clean audit.

Both new buckets appear **only when something lands in them**, so an audit with nothing
unclassified reports the same item count and the same coverage percentage as before. Pinned by
`comparisonTaxonomy.test.ts`.

This is the mirror of the warning on `DEFERRED_FEATURE_KEYS` — *"membership here HIDES rows"* —
arriving from the other direction: there, a declared item swallows findings; here, an
*undeclared* one would.

---

---

## 🔴 The real cause of the `6×⌀145` row — the panel classifies text nobody is looking at

Everything above is true and none of it was enough. With the catch-all removed, `6×⌀145` moved
out of Material Specification and into **Other / Unclassified** — and the `⌀` fix, which had a
passing test, did not prevent it.

**The test was written against the string the CARD shows.** `FindingCard` renders
`cleanCadText(m.ref_text)` / `cleanCadText(m.rev_text)`; `ManualMarkingList` and
`useComplianceReportExport` hand `inferFeatureKey` the **raw** `m.rev_text`. Two readings of one
value, and only one of them is on screen. Real `text_content` out of `storage/cache/`:

```
'SS400 6×%%c145'   'S45C %%c265×25'   'SS400 %%c55-15'   '0.28'   '10.81'   '表ニヨル'
```

So the classifier saw `6×%%c145` while the engineer saw `6×⌀145`. `MATERIAL_SIZE_RE` needs
digits on both sides of the separator and the raw form puts `%%c` there, so it did not match.

> [!IMPORTANT] Classify what the user sees.
> A rule that decides where a value is *displayed* must run on the *displayed* form. Any rule
> reading marking or finding text runs on `cleanCadText` output, never on `ref_text`/`rev_text`.

**It was positional, which is the tell.** `%%c55×15` matched on its `55×15` and `6×%%c145` did
not, so the same column classified two ways depending on where the escape happened to sit. A
rule that works on half a column's values is not a rule, it is a coincidence.

`cleanCadText` moved from `renderEntities.ts` to `utils/cadGlyphs.ts` so `utils/` can reach it
without importing the canvas renderer; `renderEntities` re-exports it, so no importer changed.
`inferFeatureKey`, `isTitleBlockText` and `inferCategoryForEntity` normalise their input at the
top — **inside**, not at the four call sites, because the fifth call site will not remember.

### ⚠ And the duplicate immediately proved the point

`manualCheckCategories.ts` held a **byte-identical copy** of `isTitleBlockText`, used only by its
own `inferCategoryForEntity` while every other caller imported the original. Fixing the original
to normalise its input made the two disagree **within the same change** — one copy classifying
the displayed form, the other still reading MTEXT markup. The copy is now a re-export. This is
`CLAUDE.md`'s DRY section happening live: *duplication here does not announce itself by breaking;
the copies keep working while they slowly disagree.*

### The separator, found by sweeping instead of choosing

`SS400 ⌀55-15` and `SS400 ⌀55×15` are **the same cell on the two sides of one pair** — the
reference writes the separator as a hyphen. The size rule caught the `×` side and the `-` side
fell through to Material Type, which would have split one finding's ORIGINAL and REVISION across
two headings. Now a cell naming a diameter is a size whatever follows it, checked before Material
Type because on these sheets the material and its size **share one text run**.

The separator class also comes from `MULTIPLY_CHARS` now — the hardcoded `[*x×]` missed
`✕ ✖ ⨯ ⨉` and full-width `ｘ`, the same shortfall as the diameter class.

> [!IMPORTANT] Sweep the corpus; do not pick examples.
> Chosen examples proved nothing here — the first `⌀` test passed while the panel was visibly
> wrong. Running **all 15 distinct BOM values in `storage/cache/`** through the classifier is what
> found both remaining defects. They are pinned as a table in `comparisonTaxonomy.test.ts`.

---

## 🔴 Open, found while sweeping: the parts-BOM columns look shifted by one

Not fixed, not fully diagnosed, and **independent of everything above** — it affects the AI
checklist (which groups on the backend's `feature`), not the manual panel. Recorded because the
evidence is unambiguous and it will otherwise be rediscovered.

`details` strings on real BOM markings say which column each value came from:

| Reported column | Values it actually holds | What that is |
| :--- | :--- | :--- |
| `/ Code` | `SS400 6×⌀145`, `S45C ⌀265×25` | 材質 **and** 材料寸法, merged into one |
| `/ / Dimension` | `10.81`, `0.28`, `0.78`, `1.42`, `15.13` | these are **weights** |
| `/ Q'ty` | `5.31`, `0.07`, `0.41 → 0.39`, `0.67 → 0.71` | these are **weights** too |
| `MATERIAL_WEIGHT`, `FINISHED_WEIGHT` | never appear in any cached marking | empty |

`bom_cols` for a parts drawing is `NO, CODE, DIMENSION, QTY, MATERIAL_WEIGHT, FINISHED_WEIGHT,
REMARK`. If `table_extractor` merges 材質 + 材料寸法 into `CODE`, every column after it shifts
left by one: `DIMENSION` receives 素材重量, `QTY` receives 仕上重量, and the two weight columns
receive nothing. That is exactly the pattern above, and it explains why `0.41 → 0.39` — a
**finished weight** — was tagged `quantity` by the engine.

⚠ **The column→sub-item map fixed above is correct and is not the bug here.** A correct map over
a shifted assignment still produces wrong sub-items. Diagnosing it needs the sheet's own header
row against `table_extractor`'s header matching, which needs the DXF, not the cache.

⚠ **The manual panel is unaffected**, because a manual marking carries no `feature` and
`inferFeatureKey` reads the text. That is why the screenshot's weights are now correct while the
AI checklist's would not be — the two paths disagree, and this is the reason.

## Guarded by

`apps/desktop/src/utils/comparisonTaxonomy.test.ts` — the bare-decimal weight, the anchoring that
keeps `6×145.5` a specification, the `⌀` cases in both branches, `other` as the honest default,
and the two matrix assertions (Other absent when empty, counted when populated).

`tests/test_taxonomy_and_classification.py::test_every_bom_column_lands_on_the_sub_item_its_header_names`
— asserted per column against the header each is extracted from, not by comparing the map to a
copy of itself.

`tests/test_taxonomy_and_classification.py::test_material_type_has_a_producer` — the item is
assignable and is not in `DEFERRED_FEATURES`, so it cannot return to reporting clean by default.

`tests/test_bom_row_granularity.py::test_the_finding_anchors_on_the_first_changed_column_in_bom_cols_order`
— updated: CODE's feature is `material_type`.

Cache invalidated at **v54**. Cached audits carry the old tags in their markings and the
checklist groups straight off them, so a hit would have shown the old layout in ~0.14s and
bypassed the fix entirely — see [[Gotcha - Comparison Cache Invalidation]].

⚠ `tools/eval.py` cannot see any of this: neither `scorer.py` nor `corpus.py` reads `feature`.
The baselines are unchanged and this change is **not** attributable in them, by construction.

## 🔗 Related Notes
- See [[Gotcha - A Checklist Item With No Producer Reported Clean]] — the same "a sub-item's empty state is a claim" rule, and the `DEFERRED_FEATURES` treatment `material_type` should have had
- See [[Gotcha - Comparison Cache Invalidation]]
- Return to [[00 - Map of Content (MOC)]]
