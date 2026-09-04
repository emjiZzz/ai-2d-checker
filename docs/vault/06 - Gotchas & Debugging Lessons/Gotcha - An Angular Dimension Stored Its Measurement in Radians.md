---
tags: [gotcha, extraction, dimensions, ground-truth]
date: 2026-08-18
status: fixed
---

# Gotcha — An Angular Dimension Stored Its Measurement in Radians

`M745204N01` prints `60°`, `50°` and `80°` around its flange. The extracted entities stored
`1.05`, `0.87` and `1.4` — numbers that appear nowhere on the drawing.

## Cause

`EntityMapper.map_dimension` substitutes the measurement when the DXF carries no override text
(empty, or the `<>` placeholder):

```python
if (not text or "<>" in text) and measurement is not None:
    meas_str = f"{measurement:.2f}".rstrip('0').rstrip('.')
```

**`actual_measurement` (group 42) is in RADIANS for an angular dimension** and in drawing units
for every other kind. 1.0472 rad is 60°, 0.8727 is 50°, 1.3963 is 80°. The formatter did not
distinguish the kinds, so it printed the raw radian float.

Fixed by masking `dim_type` to its low 3 bits — the kind, where **2 and 5 are the angular
forms** — and converting those to degrees with a degree sign. The mask is the same one
`spatial_differ._dimension_key` already used, so the extractor and the engine cannot disagree
about what kind of dimension something is. `EXTRACTION_SCHEMA_VERSION` **6 → 7**.

## Why it survived this long

Two independent reasons, and both are the interesting part:

1. **The deterministic engine never reads this string.** `spatial_differ` keys a dimension on
   its numeric `measurement` plus its kind, deliberately — `cache_manager` records the same
   choice. So comparison was completely unaffected, every eval number was unmoved, and no test
   over the engine could have caught it. Confirmed after the fix: `tools/eval.py --provenance
   mutation` reads **P 0.96 (48/50) / R 0.87 (48/55) / F1 0.91**, the standing control exactly.

2. **On a linear dimension the substitution is correct** — and most dimensions are linear. The
   bug lived in the minority branch of a function whose majority behaviour was right.

It surfaced only when the manual-check overlay began **showing the stored text to a human**, who
could see the sheet said `60°` while the label said `1.05`. Nothing in the system had ever
compared the stored string to the drawing before, because nothing had ever needed to.

⚠ **By then it was reaching ground truth.** `useEntityPicking.toPicked` copies this string into
`EntityAddress.text`, so a marking stamped on an angular dimension recorded `1.05` as the
entity's verbatim text — poisoning both the dataset and the address resolver's text tier, which
is the fallback that matters most on the reference side where handle coverage is 0.8–13%
([[Gotcha - A Marking Cannot Store an Entity Id]]).

## A smaller thing worth knowing

The same sheet stores `50°` **two different ways**: one dimension carries an explicit text
override with a real U+00B0, the other carried the substituted `0.87`. After the fix both read
`50°`, so same-sheet values are now self-consistent too — which matters for anything grouping by
value, such as the cross-sheet matcher in
[[Gotcha - A Cross-Sheet Hint That Cancelled Itself Out]].

## Migration

v6 rows still hold the wrong string. `POST /api/v1/drawings/{id}/reextract` re-parses from the
stored file and keeps the drawing's id, room slot and audit history. Until a drawing is
re-extracted its angular dimensions still read in radians.

## Lesson

**A substitution that is right for the common case is not right.** The branch was correct for
linear, aligned, diameter, radius and ordinate dimensions and wrong for the two angular kinds —
so it looked correct in every casual check. When a field's meaning depends on a type code, read
the type code; do not let the majority reading stand in for all of them.

The second lesson is about coverage of a different sort: this value was extracted, stored,
cached, compared against and rendered for months without one consumer ever holding it up against
the drawing. **A field nothing reads is a field nothing validates.** Its first human reader found
the bug immediately.

Related: [[Gotcha - A Cross-Sheet Hint That Cancelled Itself Out]],
[[Gotcha - A Marking Cannot Store an Entity Id]],
[[Gotcha - The Differ Compared Text Only]]
