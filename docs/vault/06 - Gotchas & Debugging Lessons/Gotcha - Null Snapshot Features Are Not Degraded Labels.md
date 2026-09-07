---
tags: [gotcha, learning, feedback, negative-result, false-alarm]
status: not-a-bug
cache-version: n/a — the learned model runs post-cache
date: 2026-08-05
---

# Gotcha — Null Snapshot Features Are Not Degraded Labels

> [!WARNING] This note exists to stop a "fix", not to describe one.
> The reported defect was not real. Acting on it would have introduced a worse bug than the
> one it claimed to fix. Recorded per `CLAUDE.md` constraint 4 — a measured-and-rejected idea
> is worth as much as one that worked.

## The report

[[00 - AI Maturity Status]] listed, as one of three bugs "actively poisoning measurement":

> `CorrectionControls.tsx:89-91` — hardcodes `text_similarity`, `match_distance` and
> `is_numericish` to `null`. **Fix before collecting another label** — degraded labels cannot
> be retroactively repaired.

It reads convincingly. Three of a `FindingSnapshot`'s ten fields are literal `null` at the only
place a human correction is captured, and the snapshot exists specifically to be training data.
The natural reading is that every label collected so far is missing a third of its features.

## Why it is wrong

`infrastructure/learning/feature_extractor.py::build_feature_row` **derives all three whenever
they arrive as `None`**:

```python
if text_similarity is None:
    text_similarity = _similarity(nref, nrev)
if match_distance is None:
    match_distance = _distance(ref_coord, rev_coord)
if is_numericish is None:
    is_numericish = _is_numericish(ref_text, rev_text)
```

The inputs it derives them from — `ref_text`, `rev_text`, `ref_coord`, `rev_coord` — are all
populated by the client. Nothing is lost, and nothing needs retroactive repair.

## Why "fixing" it would be worse

The inference path does not supply the three fields **either**. `features_from_marking` calls
`build_feature_row` without them, so a live finding's features are always server-derived.

That symmetry is the whole point. Send a client-computed `text_similarity` and only the
**training** side changes:

| | training (`features_from_snapshot`) | inference (`features_from_marking`) |
| :--- | :--- | :--- |
| today | Python `SequenceMatcher` over `SpatialDiffer._normalize_text` | *identical* |
| after the "fix" | some TypeScript similarity function | Python, unchanged |

That is textbook train/serve skew, and JS has neither `SequenceMatcher` nor
`SpatialDiffer._normalize_text` — reimplementing the differ's fullwidth/CAD-escape normalization
in a second language is precisely what `feature_extractor.py`'s module docstring says it exists
to avoid ("rather than drifting into a second definition").

## Why it looked like a bug

`ChecklistPanel.tsx` — the *other* place a snapshot is built — already carried the explanation:

> *"…recomputed server-side from the texts/coords with the runtime differ's own normalization,
> so null here is fine…"*

`CorrectionControls.tsx` had the identical three lines with **no comment**. Two call sites, one
documented and one bare, and the bare one is the one that got audited. The asymmetry, not the
code, produced the false alarm.

## Resolution

- The comment now appears at both call sites.
- `tests/test_stage_0a_measurement_unblocking.py::test_training_and_inference_agree_on_the_derived_features`
  pins the equality directly: a marking and its snapshot must produce the same feature row.
  A future client-side computation breaks that test rather than silently skewing the model.
- The ledger's Stage 0a item 3 is corrected, and the claim appears in its Negative Results table.

## The transferable lesson

A `null` in a payload is not evidence of missing data — it is evidence of a **contract**, and the
contract lives at the consumer. Before recording a data-quality defect, read the consumer.

The related failure mode is that this was written into the ledger as fact and would have been
inherited by every later agent as a settled finding. Same class of error as the "four V2 gaps"
phantom the ledger's own evidence rule exists to prevent — a plausible claim about system state
with nothing behind it.

## See also

- [[Gotcha - Learned Corrections Model and Post-Cache Inference]] — the rest of this model's
  wiring, including why it is never cached
- [[Continuous Learning & Human-in-the-Loop Feedback]] — how corrections are captured
- [[00 - AI Maturity Status]] — the ledger this corrects
