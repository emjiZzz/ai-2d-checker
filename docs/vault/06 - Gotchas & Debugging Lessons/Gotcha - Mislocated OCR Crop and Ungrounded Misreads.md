---
title: Gotcha - Mislocated OCR Crop and Ungrounded Misreads
type: gotcha
tags: [gotcha, ocr, title-block, gemini, zone-template, crop]
status: resolved
date: 2026-07-30
---

# The reference title block OCR'd to nulls + a misread DWG number

On the KEMCO pair, Gemini title-block OCR returned **all null except a misread DWG_NO** on
the reference (`ME17227N24` for the real `M745227N01`), while the revision OCR'd perfectly.
That made every reference title field either NONE (→ fell back to spatial) or, for DWG_NO,
**actively wrong** — because `resolve_field` trusts any non-null OCR value.

## Root cause: the crop is mislocated, because the template is aspect-keyed

The OCR crop is the detected `title` zone rendered to an image (`crop_title_block_image` →
`crop_region_image`). Both drawings match the **same** `aspect-1.414` zone template, so both
use the same title-zone *fractions*. But the reference's title block sits at a **different
fractional position** than the revision's, so the shared fractions fit the revision and not
the reference. Rendered out, the reference crop showed the **shim table** at the top, a large
empty middle, and the real title block cut off at the very bottom edge. Gemini could not see
the fields → nulls, and read the sliver of DWG number wrong.

This is the coarse-aspect-keying limitation (`zone_signature` buckets by aspect ratio; every
A-series sheet is 1.414). A proper crop fix needs **per-layout** templates, not a global fix
here — recorded, not attempted.

## Fix (the harm, not the crop): reject ungrounded OCR misreads

`title_block_extractor.resolve_field`: an OCR value is *grounded* by finding a CAD text run
that matches it. On a grounding **miss** the old code kept the OCR string anyway. It now asks
the spatial reading to arbitrate, because a grounding miss has two opposite causes:

1. **Correct value split across runs** — OCR merged `MI511` + `0A01` into `MI51100A01`. The
   spatial reading is a *fragment* (substring) of the OCR value → the OCR value is the right,
   fuller form → **keep it**. (Pinned by `test_ocr_value_retention_on_grounding_miss`.)
2. **Misread** — `ME17227N24` vs the real `M745227N01`. The spatial reading is unrelated real
   drawing text → **prefer the spatial value**.

The discriminator is substring-either-way after `_normalize_for_match`. A **grounded** OCR
value (matched to an actual run) is still trusted unchanged.

Result: reference title block now resolves fully via the grounded/spatial path — DWG_NO
`M745227N01`, SCALE `1:3`, DESIGNED `橋本`, DRAWN `中川`. The mislocated crop still wastes an OCR
call returning nulls, but no longer produces a wrong value.

## Why this matters generally

The spatial fallback was already made reliable (coord_scale + multiline opt-in, see
[[Gotcha - SCALE Field Read the Date Column]]), so *null* OCR fields were already covered. The
gap was the **non-null misread**: `resolve_field` short-circuits on any non-null OCR value, so
the fallback never ran for DWG_NO. An OCR value that grounds to nothing on the drawing is the
tell.

## Guarded by / cache

`tests/test_extraction_logic.py::test_ungrounded_ocr_value_defers_to_spatial_reading` and
`::test_grounded_ocr_value_is_still_trusted`, plus the retained split-value test. Cache
**v22→v23**. `tests/test_vision_ocr_grounding.py` has 2 unrelated pre-existing failures
(`MockEntity` lacks `layer`) — not this.
