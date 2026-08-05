---
title: Gotcha - Unrelated Text Paired as CHANGED
type: gotcha
tags: [gotcha, spatial-differ, comparison, false-changed, notes]
status: resolved
date: 2026-07-30
---

# CHANGED needs the two strings to actually be related

`SpatialDiffer.diff_views` matches ref↔rev text by proximity. Its greedy pass (pass 1,
`same_text_only=False`) accepted **any** two entities within the distance threshold as a pair
and, for anything but identical text, labelled the pair `CHANGED` with only a `score += 1000`
penalty. There was no check that the two strings were remotely alike.

On dimensions (dense, short, co-located) proximity is a fair signal. On **notes** — sentences
that move around the sheet — it is not. Measured on the KEMCO pair:

- `2 ロール： 4 (2x2台)` reported as **CHANGED** into `タップ、キリ穴は面取り仕上げのこと` (char
  similarity **0.00** — completely unrelated).
- `4 ロール：12 (2x6台)` reported as CHANGED into `１` (**0.14**).

A `CHANGED` is supposed to mean "the same element, edited". Two unrelated strings that merely
sit close together are a **removal and an addition**, not an edit.

## Fix

`spatial_differ.py`: a cross-text pair is now kept only if `_plausible_edit(ref, rev)` — the
normalized strings are `>= CHANGED_SIMILARITY_FLOOR` (0.40) similar (`difflib.SequenceMatcher`
ratio), OR both are numeric/dimensional (`_NUMERICISH_RE`). Otherwise the pair is skipped and
both entities fall through to the REMOVED + ADDED sweep.

**0.40 is calibrated, not guessed.** On the same corpus the genuine edit `シム表` → `Ｌ　シム表　
ｌ` scores 0.75 and the false pairs score 0.00 / 0.14 — 0.40 sits in the gap. The numeric
bypass is what keeps a real dimension change (`130` → `125`, similarity 0.33) a `CHANGED`
rather than splitting it.

## Second-order benefit: correct pairs form

Removing the bad options let the greedy matcher find the *right* ones. After the gate, the
`ロール` production-count texts pair with their own half-width↔full-width counterparts
(`4 ロール：12` ↔ `４ロール：１２`, sim 0.92) instead of being consumed by a wrong pairing. So the
fix both removes false CHANGEDs and recovers true ones.

## Scope — diff_views only, NOT the title block

This gate lives in `diff_views`, which handles `notes` / `iso` / `drawing_views` / `shim`.
Title-block field changes (`橋本` → `津田`, similarity 0.00 but a real DESIGNED-field edit) come
from `inject_title_block_markings`, which pairs by **field identity**, not proximity — a
different code path the gate never touches. Do not add a similarity gate there: a name change
between two unrelated names is exactly what that path is meant to report.

## Guarded by / cache

`tests/test_spatial_differ.py` — `test_diff_views_does_not_pair_unrelated_text_as_changed`
(the fix) plus `..._keeps_a_plausible_in_place_edit_as_changed` and
`..._keeps_numeric_value_change_as_changed` (guard against over-suppression). Cache **v20→v21**.
Verified live through `POST /audits/physical-comparison`: 0 sub-0.40-similarity CHANGEDs
remain in the diff path.
