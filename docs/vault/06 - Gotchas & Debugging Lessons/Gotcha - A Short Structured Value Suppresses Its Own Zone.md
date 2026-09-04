---
title: Gotcha - A Short Structured Value Suppresses Its Own Zone
type: gotcha
tags: [gotcha, comparison-engine, false-negatives, scoping, orchestrator, evaluation]
status: active
date: 2026-08-07
cache-version: v43
related: [Gotcha - Title Block QTY Reads the Upper-Left Table, Gotcha - Mutation Pairs Cannot Exercise a Spatial Constant]
---

# Gotcha — A short structured value suppresses its own zone

**Cache:** fixed in **v43** · **Class:** false negative · **Found:** 2026-08-07, by hand-auditing
the eval's recall misses

---

## Symptom

A single character deleted from a drawing produced **no finding at all**. Not a mis-categorised
finding, not a downgraded status — silence.

The ledger had carried this for two days as an open item with a named suspect:

> *A single-character deletion goes unreported (confirmed by the scorer hand-audit: `G` removed
> from the notes zone produced no finding). Prime suspect:
> `marking_reconciler.MIN_FUZZY_LENGTH = 4`.*

**Both halves of that were wrong**, and the way they were wrong is the lesson.

## Why the stated suspect could not have been the cause

`MIN_FUZZY_LENGTH` gates `_fuzzy_pairs`, which **merges** a REMOVED and an ADDED into one
CHANGED. A string too short to clear that gate is not suppressed — it is left as a separate
REMOVED *and* a separate ADDED. Failing that gate produces **more** findings, never zero.

Any hypothesis for a *zero-finding* symptom has to be upstream of matching entirely: the entity
never entered a comparison pool. That single observation would have redirected the search on day
one, and it is available without running anything.

Two other length gates look plausible and are also not it:

- `orchestrator.is_in_margin` / `zone_detector.is_margin_grid_text` — real, and they do drop
  single characters, but only within 9% of the sheet edge. Measured on the failing entity:
  `False` under both computed and render bounds.
- `spatial_differ` `len(txt) > 2` at `:229` / `:245` — this only chooses which texts anchor the
  **global offset estimate**. It never builds the finding pool.

## The actual cause

`generate_deterministic_candidates` collects every value captured by structured title-block and
BOM extraction into one flat set (`_collect_structured_text_values`) and excludes any entity
whose normalized text is in it. The intent is sound and documented: a title-block value can sit
outside its detected zone bbox, and would otherwise be reported twice — once correctly by
`inject_title_block_markings`, once again as a generic finding under whatever category the
differ tags it.

But the net is **keyed on text alone and applied sheet-wide**, with no check that the entity
being suppressed is anywhere near the structured region the value came from. So:

> The BOM row was numbered `1`. The notes zone contained a standalone full-width `１`, which
> NFKC-folds to `1`. That glyph was therefore excluded from the notes pool **on both sides**.
> Deleting it changed a pool it was never in, and nothing could report it.

Both sides is what makes this invisible rather than merely wrong. The ref and rev notes pools
came back the same size (6 and 6) on a pair where one entity had been deleted, and equal pool
sizes look like a correctly-differing drawing.

### The proof

Not inferred — measured, by changing only the collision:

```
BASELINE (BOM NO=1)          : predictions=3  "1"-findings=0
BOM NO renumbered 1 -> 999   : predictions=3  "1"-findings=1
                                      1 REMOVED notes_section
```

Nothing about the notes zone, the deleted glyph, or the differ changed between those two runs.
The engine's only reason for silence was the string collision.

## Why `G` was found and `１` was not

The ledger's example (`G`, on `M7452A0N01-ref-mut008`) is **reported correctly today** and may
always have been — `G` is not a BOM or title-block value on that sheet, so it never entered the
net. The item had gone stale and nobody re-checked it. The genuinely missing one was `１`, on a
different pair, for the reason above.

Two lessons, and the second is the expensive one:

1. **A suspect recorded without its mechanism rots into a fact.** "Prime suspect:
   `MIN_FUZZY_LENGTH`" was a guess, correctly hedged, that was read twice afterwards as the
   explanation. Write down *why* a suspect could produce the symptom, or the hedge is lost.
2. **Re-derive the symptom before fixing it.** The example in the ledger no longer reproduced.

## The fix

`ComparisonParams.min_structured_value_length = 3`. A structured value shorter than this does not
enter the suppression net. It is still reported by the structured extractor that produced it —
this only stops it silencing an unrelated twin elsewhere on the sheet.

Bound into `params._BINDINGS` as `orchestrator.MIN_STRUCTURED_VALUE_LENGTH` so Stage 0.5 can
sweep it, and swept **in both directions**: raise it far enough and a genuine title-block value
(`8.65`) stops being suppressed and gets double-reported. 3 is a convention — the shortest length
at which the corpus's real structured values are all still caught — not a measured optimum.

### Measured effect

| | before | after |
| :--- | :--- | :--- |
| recall | 0.85 (47/55) | **0.87 (48/55)** |
| precision | 0.98 (48/49) | 0.98 (48/49) |
| F1 | 0.91 | **0.92** |
| `notes_section` recall | 0.92 (12/13) | **1.00 (13/13)** |
| duplicates | 0 | 0 |
| zero-finding false positives | 0 | 0 |

**No new false positives and no new duplicates** — which was the real risk, given this project's
history of duplicate-row defects (v13/v16, v39, v40) and that the fix loosens a
duplicate-suppression net.

## The general shape

This is the same defect as the learned dismissal pattern `8` and the same reasoning
`vault_sync.get_learned_dismissals` had already written down for itself:

> *"several are short (`1`, `2A0`); substring matching would silently suppress unrelated
> content, which is the one failure mode this system cannot detect, because nothing measures its
> false-negative rate."*

That warning was correct, was written in the right place, and did not stop the identical defect
appearing one module away in a net that is not a substring match. **A short string is not an
identifier.** Any filter that suppresses content by matching text alone needs a length floor and
a scope, and this system now has three such filters: structured values (floor added here),
learned dismissals (floor and category scope added the same day — see the ledger's Stage 1a
entry), and `exclude_values` in `extract_zone_entities`, which shares the first one's set.

## Why the eval could not have caught this on its own

It did, in the sense that the miss was in the baseline all along as one of eight FNs. What it
could not do is **say which of them mattered** — the report gives counts, not causes, and the
categories all looked plausible. It took a hand-audit of the eight misses to see that two were
single characters, one of which reproduced.

The remaining misses, characterised in the same pass:

| Miss | Cause | Verdict |
| :--- | :--- | :--- |
| 4 × inserted text (`追加注記`, `追加3-m8`) | ADDED text not reported | genuine, uninvestigated |
| `Ａ`, `a-a` | section designations | **by design** — `DROP_SECTION_CALLOUT_LABELS` |
| `１` | this gotcha | **fixed in v43** |
| `zhrb` CHANGED | uninvestigated | — |

This is what [[00 - AI Agent Navigation & System Gap Analysis]] means by false negatives never
having been measured. Counting them is not the same as reading them.

---

## Related

- [[Gotcha - Title Block QTY Reads the Upper-Left Table]] — the same "one physical cell, two
  extractors" family, in the false-*positive* direction
- [[Gotcha - Mutation Pairs Cannot Exercise a Spatial Constant]] — the other limit found by
  reading what the corpus structurally cannot show
- [[Gotcha - Comparison Cache Invalidation]] — why this needed v43
- [[00 - AI Maturity Status]] — the ledger entry with the full measurement
