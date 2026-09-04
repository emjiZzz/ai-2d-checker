# Matcher Feedback — Making the Parked Corpus Count

> Plan, written 2026-08-19. Every figure below was **measured on that date**, not quoted, and
> each carries the command that reproduces it. Re-run them before acting on this: the corpus
> moves without a commit, and a plan built on a stale number is the failure mode this repo
> keeps paying for.

---

## 1. What is true today

### 1.1 The verdict head is trained and working

```
services/backend/.venv/Scripts/python.exe tools/label_status.py
```

```
verdict labels     127 / 40    threshold met
  class 0           73
  class 1           54
negative share      57%
majority baseline   57.5%
live bundle         trained 2026-08-19T01:43:37Z
  cv accuracy       77.1%  =  +19.6% of skill over baseline
```

This is no longer the constraint. The ledger's row on the learned model still describes a head
"four corrections from switching itself on" at 36/40 — that was true on 2026-08-10 and is stale
by 91 labels. **Update that row as part of this work.**

### 1.2 The loudest signal in the corpus trains nothing

Same command:

```
mispaired_missing_counterpart   58    matcher (parked)
mispaired_wrong_match           44    matcher (parked)
                               ---
                               102    trains nothing today
```

`trainer.MATCHER_FEEDBACK` captures both verbs and deliberately maps neither to a verdict label.
The restraint is correct and documented at `trainer.py:38-51`: label 0 would suppress a finding
that may be genuine, label 1 would affirm a pairing the human just rejected. Neither is a
defensible lie, so the rows are parked.

The ledger already names this as the strongest evidence of where the defect is. It has since got
louder: 102 rows, against a verdict head that is 87 labels *past* its threshold.

### 1.3 ⚠ The parked data is negative-only, and therefore not trainable as captured

This is the finding that reframes the whole problem, and it is **not** in the ledger.

```
mispaired rows carrying a human_comment:  3 / 106
```

`CorrectionControls.tsx:329-334` offers the correct counterpart as an **optional free-text
input** — *"Optional: which one should it pair with?"*. It is skipped 97% of the time, which is
the rational response to an optional typing task.

So each parked row says *"this pairing is wrong"* and almost never *"here is the right one"*.

**A matcher cannot be trained on negatives alone.** There is no target to learn toward. Building
the Stage 3 matcher today would find 102 rows that can tell it what not to do and nothing that
tells it what to do. The data is not merely waiting for a consumer — as captured, no consumer
can use it for training.

### 1.4 ~~Three snapshot features are never populated~~ — RETRACTED 2026-08-19

```
finding_snapshot.text_similarity   non-null in 0 / 249
finding_snapshot.match_distance    non-null in 0 / 249
finding_snapshot.is_numericish     non-null in 0 / 249
```

The measurement is right. **The conclusion drawn from it was wrong**, and it is left here rather
than deleted because the error is instructive: the stored documents were checked and the
CONSUMER was not.

`feature_extractor.build_feature_row` derives all three whenever they arrive as `None`, and
`features_from_snapshot` routes every stored snapshot through it on the training path. So the
nulls are deliberate and the `ChecklistPanel` comment describing them as recomputed server-side
is accurate.

Populating them client-side would be train/serve skew: the inference path does not supply them
either, and there is no `SequenceMatcher` or `SpatialDiffer._normalize_text` in TypeScript.
`tests/test_stage_0a_measurement_unblocking.py` already pins the derivation, having been written
after a previous version of exactly this mistake.

`_distance` returns `-1.0` for the 142 rows carrying one coordinate, which is an explicit
sentinel rather than a silent zero.

### 1.5 Supervisor verdicts are almost absent

```
audit_violations   2899 total, 2665 with no supervisor verdict
```

92% of violations have never been reviewed. Not addressed by this plan; recorded so it is not
mistaken for something this plan improves.

---

## 2. The problem, stated precisely

Three separate stores collect human judgement, and only one of them gates the ladder:

| Store | Written by | Answers | Feeds |
| :--- | :--- | :--- | :--- |
| `audit_feedback` | Comparison Results panel | "was this finding right?" | learned model |
| `ground_truth_markings` | manual-check mode | "what is on these sheets?" | nothing yet — see §3.4 |
| `storage/eval` manifest | `eval_corpus.py label` | "what did the engine miss?" | Stage 0b, the rung gate |

Reviewing engine output **cannot** reveal a false negative: a missed finding has no row to
dismiss. That is why `eval_corpus.py worksheet` refuses to pre-fill from engine output, and why
`showViolations` is forced off in a manual-check room. The three stores are not substitutes and
none of them is redundant.

**The specific problem this plan addresses:** 102 rows of the loudest human signal in the system
are unusable, and will remain unusable even after Stage 3 arrives, because they record a
rejection without a correction.

---

## 3. The plan

Ordered by cost-to-value. Each step is independently shippable and independently useful.

### Step 1 — Measure the matcher with the data as it stands *(no new components)*

**What.** A report that scores the deterministic matcher's pairing accuracy from the 102 parked
rows: how often a pairing is rejected, broken down by category and by feature.

**Why first.** It needs no model, no schema change and no new labelling. It converts "parked" into
the first number anyone has for how often the engine pairs wrongly — and a negative-only corpus
is *sufficient* for a precision measurement even though it is insufficient for training.

**Deliverable.** `tools/matcher_status.py`, modelled on `tools/label_status.py`: read-only,
offline, reports rather than writes.

**Reports.**
- rejection count by `finding_snapshot.category` and `.feature`
- split by verb (`wrong_match` = paired the wrong two; `missing_counterpart` = failed to pair)
- how many carry both coordinates (the subset where a distance can be recomputed)
- how many carry a `human_comment` (the trainable subset — 3 today)

**Explicitly does not.** Compute a rate. There is no denominator: `audit_feedback` records
rejections, not the total pairings attempted. Reporting "N rejections in category C" is honest;
"X% wrong" would require the pairing count from an engine run and must not be invented.

**Verify.** Numbers reconcile with `label_status.py`'s 102, and with a direct Mongo count.

---

### Step 2 — Capture the correction, not just the rejection

**What.** Replace the optional free-text *"which one should it pair with?"* with the
counterpart-picking gesture that already exists.

**Why.** This is the step that makes every *future* row trainable. It is also the cheapest
possible build, because the gesture is already written, tested and in use: `SelectionMenu`'s
`pendingPairRef` / `pendingPairTool` flow — pick a half, click the counterpart on the other
sheet, done. It was generalised beyond CHANGED on 2026-08-18 and already carries its own verb.

**Changes.**
- `CorrectionControls` — on `mispaired_wrong_match` / `mispaired_missing_counterpart`, start a
  counterpart pick instead of showing a text box.
- `AuditFeedbackDocument` — a structured `corrected_counterpart` (handle + side + text +
  coordinate), alongside `human_comment` rather than replacing it. Optional, defaulting to null:
  the 249 existing rows stay valid and unmigrated.
- `trainer.py` — **no change yet.** The verbs stay in `MATCHER_FEEDBACK` and stay unlabelled.
  This step only improves what is recorded.

**Explicitly does not.** Retrofit the 102 existing rows. There is no way to recover an answer
that was never given; re-deriving one from the engine would reintroduce exactly the circularity
that makes the row worthless.

**Verify.** A new mispair correction round-trips a resolvable counterpart address. Existing rows
load unchanged.

---

### Step 3 — Decide what the matcher defect actually is *(owner's judgement, blocking Step 4)*

**What.** Read the Step 1 report with the owner and answer one question: are the 102 rejections
**one repeated shape** or many different ones?

**Why this is a step and not an assumption.** If the rejections concentrate in one category or
one feature, this is likely a threshold or a scoping rule, fixable deterministically for a
fraction of the cost of a learned matcher — and `MIN_STRUCTURED_VALUE_LENGTH`, the zone
precedence rules and `line_attribute_differ` are all live candidates with a history of exactly
this. If they are diffuse, the learned matcher is justified.

**Do not skip.** Building Stage 3 because the data is labelled "matcher" would be choosing the
expensive answer without looking at the question.

---

### Step 4 — Stage 3, only if Step 3 says so

Deliberately unspecified here. It depends on Step 3's answer, and needs a corpus that Step 2 has
been filling for long enough to have positives. Writing its design now would be guessing.

**Precondition:** enough rows carrying `corrected_counterpart` to train on. That number is not
knowable yet; `MIN_TRAIN = 40` is the existing precedent for the verdict head.

---

### Step 5 — ~~Fix the snapshot claim~~ — NOT NEEDED

Struck 2026-08-19 on the evidence in §1.4. There is no defect: the fields are computed on the
training path and storing them would introduce the skew the existing test guards against.

The only thing this step leaves behind is a warning. `0 / 249 non-null` looks damning and is not,
so the next reader who measures the collection will reach the same wrong conclusion. If anything
is worth doing here it is a comment on `FindingSnapshot` pointing at `build_feature_row` — a
sentence, not a step.

---

## 4. What this plan does NOT do, and why

- **It does not merge the three stores.** They answer different questions and the separation is
  what keeps the corpus able to measure the engine. See §2.
- **It does not make `audit_feedback` count toward Stage 0b.** Structurally impossible: reviewing
  engine output cannot reveal what the engine missed. Stage 0b advances only via
  `eval_corpus.py worksheet` → fill → `label`.
- **It does not change `MATCHER_FEEDBACK`'s unlabelled status.** Until there are positives, both
  available mappings still teach something false. `trainer.py:38-51` stands.
- **It does not touch the verdict head.** It is trained, at 77.1% cv accuracy, and out of scope.

---

## 5. Open questions

1. **Is the pairing error one shape or many?** Blocks Step 4. Only the owner can answer, from
   the Step 1 report plus memory of what was rejected.
2. **Should `ground_truth_markings` feed anything today?** `tools/export_manual_labels.py`
   (2026-08-19) bridges it to the eval corpus. Nothing else consumes it.
3. **Is the corpus mixing extraction schema versions?** `M7452A2N01` was re-exported on
   2026-08-19 from `schema_v=7` extractions, having previously been built from `schema_v=2`. The
   other six pairs are unaudited. A corpus spanning five schema bumps compares findings derived
   from different geometry.

---

## 6. Related

- [[AI Maturity Ladder — Staged Plan]] — the ladder this feeds
- `00 - AI Maturity Status.md` — the ledger; §1.1 above supersedes its learned-model row
- [[Gotcha - A Verdict Mapping That Contradicted Its Own Comment]] — the last time
  `MATCHER_FEEDBACK` was mishandled
- [[Gotcha - Learned Corrections Model and Post-Cache Inference]]
