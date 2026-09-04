---
title: Gotcha - Fullwidth Callouts Were Never Classified
type: gotcha
tags: [gotcha, taxonomy, feature-classification, nfkc, japanese-cad, chamfer]
status: resolved
date: 2026-08-04
---

# 🔥 Gotcha — every FULLWIDTH callout fell into "Other / Unclassified"

`feature_classifier.py` matches ASCII patterns:

```python
_CHAMFER_RADIUS_RE = re.compile(r'\bC\s*\d+(\.\d+)?\b|\bR\s*\d+(\.\d+)?\b', re.IGNORECASE)
_DIMENSION_LIKE_RE = re.compile(r'^[\d.,\s±+\-/]+$')
```

It did **no NFKC folding**. This corpus is Japanese CAD and writes callouts in **fullwidth**, so
every one of them missed every rule and landed in `other`.

Measured on the M7452A1N01 pair — the same chamfer, written differently on each sheet:

| | text | classified as |
| :-- | :-- | :-- |
| reference | `C1` | `chamfer_radius` ✅ |
| revision | `Ｃ１` (U+FF23 U+FF11) | `other` ❌ |

The finding's `text_content` is the revision's, so the chamfer was filed under
**"Other / Unclassified"** rather than "Chamfer / Radius".

## Why this was invisible

`SpatialDiffer._normalize_text` **already** NFKC-folds, so the differ *paired* `C1` with `Ｃ１`
perfectly and reported a correct MATCHED. The comparison was right; only the label was wrong. A
finding in the wrong checklist bucket looks like a missing check rather than a broken rule, so
the failure reads as "the chamfer isn't being compared" — which it was.

The classifier was the one place in the pipeline that did not fold.

## Scope — it was never only chamfers

| fullwidth | before | after |
| :-- | :-- | :-- |
| `Ｃ１`, `Ｒ５` | `other` | `chamfer_radius` |
| `１２０` | `other` | `dimensions` |
| `２２．７±０．０２` | `other` | `geometric_tolerances` |
| `⌀１２０` | `other` | `hole_properties` |

Hole callouts like `６－６．６キリ１１ザグリ深サ６．５` were unaffected — they matched on the CJK
keyword `キリ`, which needs no folding. That is why the gap looked narrower than it was: the
rules keyed on Japanese words worked, and only the rules keyed on Latin letters and digits failed.

## Fix

A `_fold()` helper (`unicodedata.normalize("NFKC", ...)`) applied at the entry of
`classify_drawing_view_feature`, `classify_notes_feature` and `classify_title_ul_feature`.

## Guarded by

- `tests/test_taxonomy_and_classification.py::test_classify_drawing_view_feature_folds_fullwidth_callouts`
  — asserts fullwidth and halfwidth forms classify **identically**, not merely that fullwidth
  classifies to something.
- `tests/test_taxonomy_and_classification.py::test_bare_section_label_stays_unclassified` —
  folding must not make `Ａ－Ａ` start claiming a feature; it is a section-marker label, not an
  engineering callout. (`断面Ａ－Ａ`, with the 'section' keyword, correctly becomes
  `additional_views`.)

## ⚠️ Separate, still open: the same chamfer lands in two different zones

The reference's `C1` at (393.7, 520.7) falls inside the pinned **`notes`** box
(x 84.5–415.2, y 510.9–653.5) as well as `views`, so `views_exclusions` sends it to the
notes pool. The revision's `Ｃ１` at (145.2, 198.2) sits 6.2 units below that sheet's notes
floor (y 204.4) and stays in the views pool. The same callout is therefore diffed in **two
different categories**, producing `REMOVED notes_section 'C1'` + `ADDED drawing_views 'Ｃ１'`.

`reconcile_relocated_markings` merges that pair back into a single
`MATCHED drawing_views 'Ｃ１'`, so nothing is lost today — but the correct result depends on a
fallback rather than on the partition being right. The `notes` box overhangs the drawing area on
the reference; re-aligning it in the zone editor would fix the cause. See
[[Gotcha - Zone Detection Accuracy & Stability]].

## Related

- [[Gotcha - The Differ Compared Text Only]] — found in the same session; dimensions were being
  dropped from comparison entirely, which is what surfaced this classification gap.
- [[Gotcha - Full-Width Grid Labels Bridged Zones]] — the *other* fullwidth defect: `is_margin_grid_text`
  compared against ASCII `"A".."H"` without NFKC, so fullwidth sheet-frame labels were never
  excluded. Same root cause, different call site, found weeks apart. **When a rule keys on Latin
  letters or digits in this codebase, assume fullwidth input until proven otherwise.**
