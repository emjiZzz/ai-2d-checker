---
title: Gotcha - The Title Block Panel Classified One Half of Each Finding
type: gotcha
tags: [gotcha, checklist, taxonomy, title-block, manual-check, classification, false-confidence]
status: fixed
date: 2026-09-01
---

# 🔥 Gotcha — a date filed under Scale, and a designer filed under Machine Name

Reported from the same live Manual Check panel as
[[Gotcha - Every Unrecognised BOM Value Named a Real Sub-Item]], one category down:

| Sub-item | Contents | Should be |
| :--- | :--- | :--- |
| **Machine Name** | `橋本` → `津田` | **Designed** — they are the 設計 signatures |
| Machine Name | `押ェ板`, `Roll Cassette 12"Mill` → `ロールカセット 12"ミル` | correct |
| **Scale** | `04/12/22` → `2026/07/03` | **Date of Creation** |
| Scale | `1:1.5` → `1/1.4` | correct |
| Date of Creation, Designed | ⚪ *Pending* | the two rows the misfiled data belonged to |

Both misfilings put a value under a heading while the heading it belonged to reported *Pending* —
"nothing recorded here" — which is the reading a checker acts on.

---

## 🎯 The scale rule was not a scale rule

```ts
if (/(SCALE|尺度)?\s*(\d+(\.\d+)?\s*[:/]\s*\d+(\.\d+)?)/i.test(clean)) return 'scale';
```

The keyword is **optional** and nothing is anchored, so what it actually matches is *"a number, a
colon or a slash, another number, anywhere in the string"*. Every date on every sheet satisfies
that: `2026/07/03` matches on its leading `2026/07`. Scale was tested before the date rule, so the
date rule never got a turn.

**Reordering alone does not fix it, which is the interesting part.** A date separator class has to
include `.` for `2026.07.03`, and `1/1.4` — a real scale — then reads as three parts. Each rule
claims the other's values.

> [!IMPORTANT] The fix is arity, and it makes the order irrelevant.
> A ratio is exactly **two** parts; a date is exactly **three**. Anchor both to a full match and
> neither can claim the other, whichever is tested first. An unanchored rule with an optional
> keyword is not a rule about scales — it is a rule about punctuation.

---

## 🎯 The panel was classifying one half of each finding

`橋本 → 津田` is the 設計 cell, and `橋本` is one of the names the code knows. So why Machine Name?

Because every caller passed **`m.rev_text || m.ref_text`** — the revision, always, and the
reference only when the revision was empty. `津田` matches nothing, so the pair fell to the
`title_block` branch's default, `machine_name`.

**The evidence that would have settled it was in the other half of the same finding.** A finding is
a pair; classifying one side of it throws away half the input for nothing.

`inferFeatureKeyForPair` asks the revision first and still prefers it whenever it identifies
anything. The reference is consulted only when the revision's answer was a non-identification.

> [!WARNING] Only `other` defers. Getting this wrong emptied a different category.
> The first implementation deferred on each category's **fallback** too — the branch's last
> `return` — on the theory that a fallback means "could not tell". For two categories it does
> not. `drawing_views` falls back to `dimensions` and `notes_section` to `standard_notes`, and
> both are **substantive**: a bare `145` *is* a plain dimension, which is the same argument
> `classify_notes_feature` makes for its own default on the backend.
>
> 🔴 **It was reported within the hour, from the same panel.** `⌀145 → 145` had the revision
> correctly reading `dimensions`; that was treated as a non-answer, the reference `⌀145` was
> consulted, it matched the diameter rule, and **Drawing Views emptied into Hole Properties with
> Dimensions left showing *Pending***. Three rows moved that nobody had asked to move, in a
> category the change was not supposed to touch.
>
> `other` alone is sufficient for the case this function was built for: `橋本 → 津田` defers
> because `津田` resolves to `other` through the personal-name rule — a specific key that
> explicitly means "no identification" — not because `machine_name` happens to be the title
> block's fallback. **The narrower rule was always the one that was needed.**
>
> ⚠ **A side with no text does not get a vote either.** An ADDED finding has an empty reference,
> and `inferFeatureKey('')` returns the branch fallback — so an unguarded empty half answered
> `machine_name` and overrode a revision that had correctly resolved to `other`, putting every
> drawing number back under Machine Name. Caught by the corpus agreement test, not by reasoning.

> [!IMPORTANT] The transferable lesson, and it is about scope rather than regexes.
> `inferFeatureKeyForPair` is shared by all six categories, so a change made to fix the title
> block altered `drawing_views` and `notes_section` too. **A fix applied at a shared seam is a
> change to every caller of that seam, and it has to be measured against every caller** — the
> corpus sweep that would have caught this was run for `title_block` only, on the assumption that
> the other categories were not affected. They were. The sweep is now run per category.

---

## ⚠️ The signature cells cannot be resolved from text, and the code pretended otherwise

```ts
if (/design|設計|橋本|増田/i.test(clean)) return 'designed';
if (/draw|製図|ZHR/i.test(clean))        return 'drawn';
```

Two customer surnames and one set of initials, inline, reading like a pattern. They are a
**lookup**, and the corpus shows it incomplete on its own data: the four signatures on record are
`橋本` and `津田` on 設計, `中川` and `ZHR` on 製図 — the list holds two. It cannot be completed
either, because the next revision is signed by whoever signs it.

Kept, in a named `KNOWN_SIGNATORIES` constant that says exactly what it is, because when it
matches the answer is right and the pair resolver only needs it to match **one** side. What
changed is what happens when it misses: a bare surname now answers `other` instead of falling into
Machine Name.

The name shape is **measured**: all three signatories in the corpus are exactly two CJK
ideographs, and none of the seven TITLE-2nd-line part names are (`押ェ板` is three and mixed,
`廻リ止メ` four, the rest katakana). ⚠ A two-kanji part name would be misread by it. None has
appeared, and the trade is worth it because the alternative files a person as the machine.

> [!IMPORTANT] 設計 and 製図 are the title block's version of the BOM's `No.` vs `Q'ty`.
> Both hold a bare surname and **nothing in the string says which**. Only the field label does,
> and a manual marking carries no field. The engine has no such problem — `title_feature_map`
> tags from the field key it read — which is exactly why the two paths disagree, and why the real
> fix is to carry the field onto the marking rather than to sharpen the guess.

---

## ✅ The Machine Name default stayed, because it was measured rather than assumed

The instinct after the BOM note is to make this fallback `other` too. **Measured, it is right for
12 of the 15 corpus values that reach it** — the TITLE / TITLE (2nd line) part name (`押ェ板`,
`カラ－`, `シム`, `基準スペーサー：3`, `ライナ－`, `バランスビ－ム`, `廻リ止メ`) and the upper-left
Part No. / Unit No. codes (`45`, `2A1`, `206`), all of which `title_feature_map` and
`classify_title_ul_feature` also call `machine_name`. The three it got wrong were the signatures,
and the personal-name rule takes those out of its way.

**That is the difference from the BOM branch, and it is a measurement, not a preference.** There
the catch-all was wrong for the values that mattered; here it is the honest reading of "a title
block's remaining free text is the title".

---

## 🔍 Two more disagreements the sweep turned up

**The panel claimed a drawing number it had no item for.**
`/^[A-Z]\d{5,}/ → previous_drawing_number` fired on `M745221N01` — the sheet's **own** number, not
a previous one. `title_feature_map` sends `DWG NO` to `other` deliberately, because the taxonomy
has no item for the current drawing number. So one value present on every sheet was filed two ways
depending on which room you opened. `previous_drawing_number` now needs the word *previous*; a
bare drawing number answers `other`, matching the engine.

**`\d{5,}` never matched half the corpus's drawing numbers.** `M7452A2N01` is `M` + a **four**-digit
job block + an alphanumeric tail, so the pattern matched `M745221N01` and missed `M7452A1N01`,
`M7452A2N01` and `M745230A01` — including the two pairs currently queued for labelling. It is one
`DRAWING_NUMBER_RE` now, because `isTitleBlockText` uses it to decide a marking belongs to the
title block at all and `inferFeatureKey` uses it to decide which sub-item: the two disagreeing
would reroute a drawing number into the title block and then fail to recognise it there.

---

## ⛔ `line_name` is no longer assigned from text

`/押工板|line|part|品名|ライン/ → line_name` was removed, on three independent grounds:

1. **`line_name` is in `DEFERRED_FEATURE_KEYS`**, which declares that nothing can assign it — and
   `ChecklistPanel` renders the deferred notice *before* checking for rows, so anything filed
   there is **dropped**. The rule and the declaration contradicted each other.
2. **`押工板` is not a string in this corpus.** The value is `押ェ板` (ェ, not 工), and the backend
   files the TITLE 2nd line as `machine_name` — so the rule was both misspelled and pointing away
   from the right answer.
3. **`ライン` cannot match cleaned text at all.** `cleanCadText` folds `ラ` → `x` (the CP932
   mis-decode of `×`), so the token becomes `xイン` after normalisation. ⚠ The same dead token is
   still in two `isTitleBlockText` alternations — harmless there because other rules cover those
   strings, but do not add a third.

---

## Guarded by

`apps/desktop/src/utils/comparisonTaxonomy.test.ts` — every distinct title-block pair in
`storage/cache/`, with the expected column taken from **the feature the backend assigns from the
field key**, so it is an agreement test between the two paths rather than a restatement of the
rules. Plus the four combination cases for `inferFeatureKeyForPair`, and a test that drives each
category with an unmatchable string to pin `CATEGORY_FALLBACK_FEATURE` against the branches it
claims to describe — the pair resolver decides "could not tell" by comparing against that map, so
a branch whose default moved without the map moving would silently stop deferring.

⚠ **No cache bump.** Nothing here changes what the engine writes: the backend's title-block
tagging was already correct and is untouched. This is the frontend agreeing with it.

## 🔗 Related Notes
- See [[Gotcha - Every Unrecognised BOM Value Named a Real Sub-Item]] — the same panel, the same day, and the `cleanCadText` normalisation both depend on
- See [[Gotcha - A Checklist Item With No Producer Reported Clean]] — `DEFERRED_FEATURE_KEYS`, and why a rule that assigns a deferred key drops rows
- Return to [[00 - Map of Content (MOC)]]
