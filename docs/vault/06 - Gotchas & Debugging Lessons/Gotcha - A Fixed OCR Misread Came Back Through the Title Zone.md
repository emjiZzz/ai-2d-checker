---
title: Gotcha - A Fixed OCR Misread Came Back Through the Title Zone
type: gotcha
tags: [gotcha, ocr, title-block, grounding, eval-corpus, regression, ruled-cells]
status: fixed 2026-08-17 — cache v49 → v50; the first hypothesis was measured and refuted, see below
date: 2026-08-17
cache-version: v49 → v50 — title-block fields resolved through the grounding-miss branch can
  change value, which changes findings.
related: [Gotcha - Mislocated OCR Crop and Ungrounded Misreads, Gotcha - The Pinned Template Has No Shim Zone, Gotcha - Title Read the Drawing Number and Was Never Compared, Gotcha - SCALE Field Read the Date Column]
---

# Gotcha — a fixed OCR misread came back, because the fix needed evidence the sheet would not give

**Class:** a guard that trusts a value precisely when nothing corroborates it · **Found:**
2026-08-17, from the first eval run over `M745227N01`'s human labels

---

## Symptom

`tools/eval.py --explain M745227N01` reported a false positive:

```
SPURIOUS   -   REMOVED  'me17227n24'  [title_block]
```

**That string exists nowhere in either drawing.** Both sides carry `M745227N01` as a text entity,
identically. The reference's title-block OCR invented `ME17227N24`; the revision's returned
`DWG_NO: null`; the engine diffed the two and published the misread as a removed field.

## Why this is not a new bug

[[Gotcha - Mislocated OCR Crop and Ungrounded Misreads]] documented **this exact string on this
exact pair** on 2026-07-30, fixed it, and is marked `status: resolved`. Its fix:
`title_block_extractor.resolve_field` *grounds* an OCR value by finding a CAD text run that matches
it, and on a grounding miss lets the spatial reading arbitrate — keep the OCR value when the
spatial reading is a *fragment* of it (a split value, `MI511` + `0A01` → `MI51100A01`), prefer the
spatial value when it is unrelated real drawing text (a misread).

**That fix is intact and its guards pass.** Handed the reference's text entities it resolves
`DWG NO` → `M745227N01`, correctly.

## The first hypothesis was wrong, and measuring it is what found the real cause

The obvious explanation was that the grounding run never reached the extractor: the engine passes a
`keep_for_title_extraction`-filtered list, that filter drops an entity in the tolerance or
upper-left box **and not in the title box**, and this sheet's drawing number sits *below* the pinned
`title` box by fraction (y-down 0.957 against `yMax` 0.9247). Clean story, and **false.**

Measured by wrapping `keep_for_title_extraction` around a real engine run:

```
text          : M745227N01
insert        : [950.37, 38.02]
KEPT          : True
in_tolerance  : False   box (75.26, 28.74, 455.68, 153.04)
in_title_ul   : False   box (75.22, 762.99, 313.71, 862.25)
in_title      : True    box (455.25, 29.29, 1229.46, 157.57)
```

The **engine's** `title` box is not the template fraction — it is `ref_title_bbox`, which reaches
down to y=29.3 and contains the drawing number. `in_title` is `True`, and the entity is kept.
*A fraction computed off the template is not the box the engine uses; measure the box, do not
derive it.*

## The real cause, isolated by entity type

With the entity present, resolution still returned the misread. Bisecting the entity list by type:

| input | resolved `DWG NO` |
| :--- | :--- |
| 172 text entities | `M745227N01` ✅ |
| text + 5 dimensions | `M745227N01` ✅ |
| text + 15 polyline / 8 block / 6 circle / 5 arc / 21 layer / 1 leader | `M745227N01` ✅ |
| **text + 156 LINE** | **`ME17227N24`** ❌ |

LINEs are the trigger, and they have exactly one consumer here: `_collect_vertical_rules`, feeding
`_separated_by_rule`. That guard exists for a real defect of its own — it stops the proximity
search reading a value out of a neighbouring ruled column. **On this sheet the reference's
`DWG.No.` label at (916.23, 44.88) and its own value `M745227N01` at (1084.68, 51.48) are separated
by a ruled cell divider**, so the guard rejects the correct value, `extract_proximity_value` returns
`("NONE", label_coords)` — and control reaches this, in `resolve_field`:

```python
sv = str(spatial_val).strip()
if not sv or sv.upper() == "NONE":
    return ocr_val_str, spatial_coords     # <-- publishes the ungrounded misread
```

**The OCR string is trusted in the one case where nothing corroborates it at all**: it matched no
text run *and* the spatial search found no value. Both of the 2026-07-30 fix's branches need a
spatial reading to exist; neither one covers its absence, and the fall-through kept the pre-fix
behaviour.

## The rule

**A guard conditioned on corroborating evidence cannot fire when the evidence is missing — which is
the case it exists for.** Exactly the shape recorded in
[[Gotcha - One Unplaceable Finding Became a Checkmark on Every Matching Cell]] (*"a guard
conditioned on the evidence being present cannot fire when the evidence is missing"*), one
subsystem over. When a check has two branches for *disagreement*, ask what it does on *silence* —
silence is not agreement, and here it was treated as licence.

Corollary: **an unverifiable value must not become a field.** A title-block field is diffed against
the other drawing, so anything published there can become a finding. `NONE` costs a comparison;
a fabricated string costs the user's trust in every finding on the sheet.

## Fix

`resolve_field`'s grounding-miss branch now returns `"NONE"` when the spatial reading is also
empty, letting the spatial path own the field instead of publishing an uncorroborated OCR string.
Cache **v49 → v50**.

⛔ **Not fixed by relaxing `_separated_by_rule`.** It is doing its job — the label and value really
are in different ruled cells on this sheet — and loosening it re-opens the neighbouring-column
defect it was written for ("Previous Dwg. No." reading `1` out of the tolerance table). The right
place to absorb a sheet whose label and value are cell-separated is the proximity search's own
geometry, and that is a larger change than this one; it is **not** attempted here.

⛔ **Not fixed by trusting OCR less generally.** The split-value case is real and pinned by
`test_ocr_value_retention_on_grounding_miss`; it is decided by the substring branch, which requires
a spatial reading to exist, so it is untouched by this change.

## Measured effect

**A/B'd at the same commit, fix off vs on, per pair** — the only honest way to attribute it:

- `M745227N01`: exactly one line removed from the findings, the `me17227n24` false positive.
  Nothing else moved.
- `M7452A0N01`: **no difference at all.**
- Mutation invariant unchanged: `--provenance mutation` still reproduces `baseline-v48.json` at
  **P 0.9796 / R 0.8727 / F1 0.9231**.
- Human pairs, templated: macro F1 **0.51 → 0.53**; detection-only precision **0.34 → 0.35**
  (predictions 38 → 37). Recall unmoved at 0.60 / 0.65 — this removes a fabrication, it finds
  nothing new.
- `pytest` 1171 passed, 3 skipped. ⚠ 5 failures exist in `test_label_status`,
  `test_lessons_index_write_path` and `test_matcher_feedback` — **verified byte-identical with this
  fix reverted**, so they are pre-existing and unrelated (they contradict CLAUDE.md's "both suites
  green" claim, which is stale).

## Guarded by

`tests/test_extraction_logic.py::test_uncorroborated_ocr_value_is_dropped_not_published` —
**verified non-vacuous**: against the old code it fails with `assert 'ME17227N24' == 'NONE'`, the
real string, not a synthetic one.

⚠ **The eval corpus found this and nothing else could have.** It is invisible to mutation pairs
(they edit text on one drawing family and never touch OCR) and to the review queue (a supervisor
sees a plausible removed drawing number, not a fabricated one). It surfaced because a human label
said what the title block should contain.

## Open — investigated 2026-08-17, not closed

**The observation.** The first `--explain` run of this pair listed `REV-2E2` / `REV-2E3` (the
roll-count lines) as spurious and no `271`/`279` dimension rows; every run since lists the reverse,
same total of 12. **Not reproduced, and not attributed.** What was ruled out, each by measurement:

| hypothesis | verdict |
| :--- | :--- |
| Run-to-run nondeterminism | **No** — 3 consecutive `--explain` runs byte-identical |
| The v50 fix | **No** — its A/B changes exactly one line, on one pair |
| The installed label file (edited between runs) | **No** — labels feed the *scorer*; the raw engine predictions are 18 with `271`/`279` and no roll-count rows, and no label can change those |
| The three new vault notes | **No** — `vault_sync` reads only `CLIENT_RULES_DIR` = `08 - Client Domain & CAD Rules`; the notes are in `06` |
| The live rules folder mutating | **No** — `08 - …` unmodified, mtimes 2026-07-28 / 2026-08-05 |
| Corpus payload drift | **No** — the runner asserts sha256 and fails loudly |
| A stale OCR cache entry | **Mechanism is real (below), but inert here** — planting a corrupted entry changes nothing, verified **cross-process**; and the cache entries for these pairs date to 2026-08-05 |

**Cause still unknown.** Recorded as unknown rather than closed with a plausible story.

### What the investigation did find, and it is worth more than the original question

🔴 **`CorpusPair.restore_ocr_cache` cannot repair a stale entry, and the harness depends on it
being able to.** The write is guarded:

```python
target = base / side.ocr_cache_filename()
if not target.exists():          # <-- only ever fills a GAP
    write_text_stable(target, text)
```

Its own docstring says restoring *"is what makes a score reproducible"*, and `run_corpus`'s comment
says restoring first *"makes the score a function of the corpus alone."* **Both claims are false
whenever an entry already exists with different content** — which is the normal state of
`storage/cache/` on any machine that has ever run a live comparison. Proven: planting
`{"DWG_NO": "STALE9999", "SCALE": "9:9"}` and calling `restore_ocr_cache()` reports restoring
**nothing** and leaves `STALE9999` in place.

**Severity today is low and that is an accident of the v50 fix**, not of the harness: an
uncorroborated OCR value is now discarded, so the planted `STALE9999` never reaches a field and the
score is unchanged cross-process. **Before v50 that same branch would have published it.** The hole
remains live for any field where a stale value *does* ground, or where the spatial reading agrees.

✅ **Fixed 2026-08-17.** `restore_ocr_cache` now replaces a differing entry and reports it
distinctly (`"<name> (replaced a differing entry)"`); `tools/eval.py` prints those, because
`RunResult.ocr_restored` had been recorded and **never surfaced anywhere**. Verified end to end:
planting a `STALE9999` DWG_NO and running the real CLI prints
`OCR cache: replaced 1 differing entr(y/ies) from the corpus` and repairs it. Mutation invariant
unchanged throughout — `baseline-v48.json` still reproduces at P 0.9796 / R 0.8727 / F1 0.9231, so
no published number was resting on a stale entry.

### The fix's first version was wrong, and finding out why produced the better finding

Comparing **bytes** reported *4 replacements on every run* against a clean cache. The cause is a
key collision nobody had recorded:

> **19 corpus pair-sides share one OCR cache filename.** The key is
> `(drawing_id, file_hash)`, and every mutation pair derives from a base drawing and reuses its
> id and hash — so `M7452A0N01/ref` and 18 mutation-pair sides all map to the same file, as do
> `M7452A0N01/rev` and 18 more.

Each of those pair-sides carries its own captured `ocr.json`, exported at different times. **All
the collisions in this corpus are formatting-only — byte-different, identical after JSON parse**
(measured across every colliding key). So a byte comparison called them all stale and rewrote them
every run: churn that reports drift where there is none, and would bury a real stale entry in
noise. The comparison is now on the parsed reading. Consecutive clean runs report nothing;
a genuinely different reading is still caught by name.

⚠ **The collision itself is benign today and is not fixed** — it is benign only because the
competing payloads happen to agree. Nothing enforces that. If a mutation pair were ever re-exported
with a *different* reading for a shared key, the pair scored would depend on manifest iteration
order, and this note's repair would churn between two readings every run instead of settling.
**Worth a residual check**: assert that all pair-sides sharing a cache key carry the same parsed
reading. Recorded rather than built, because no number moves today.
