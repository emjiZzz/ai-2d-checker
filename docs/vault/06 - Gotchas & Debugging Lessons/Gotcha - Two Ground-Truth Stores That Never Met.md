# Gotcha - Two Ground-Truth Stores That Never Met

> Found 2026-08-20, from a user sentence: *"I labelled them yesterday."* `tools/eval_corpus.py
> status` said `M7452A1N01 UNLABELLED`. Both were true.

## The shape of it

This project has two places a human's judgement about a drawing can land, and until now
nothing connected them:

| | Manual Check | Eval corpus |
| :--- | :--- | :--- |
| Added | 2026-08-18 | ~2026-08-05 |
| Writes to | `ground_truth_markings` (Mongo) | `tests/fixtures/eval/labels/*.json` (committed) |
| Has a UI | **yes** | no — `worksheet` → hand-edit → `label` |
| Counted by Stage 0b and the rung gate | **no** | **yes** |

So the *only* path with a user interface fed the metric not at all, and the path that moves the
rung gate was the one with no UI. An engineer had spent two days marking up drawings in the app
and Stage 0b still read 4 / 8. Nothing was broken, nothing errored, and nothing anywhere said
the two were unrelated.

**The general shape: when a capability gets a UI later, check what the UI writes to.** The
ledger entry that introduced Manual Check called it *"ground-truth capture, additive"* — and
additive is exactly what it was, in a sense nobody intended.

## Three things that were nearly got wrong

### 1. A count without the retraction filter is not a count

The session stored `marking_count: 7`. `count_documents({"session_id": ...})` returned **38**.
I recorded that as a stale-denormalised-counter defect and filed it.

It was not a defect. **31 of the 38 markings carry `retracted_at`**; the stored counter counts
live ones and was right the whole time. The bug was in the measurement — my query had no
`retracted_at: None`, and a retracted marking is a statement the engineer *withdrew*.

Which makes the same mistake a live hazard for the bridge: a converter that ignored
`retracted_at` would have manufactured **31 findings a person had explicitly taken back**, and
they would have read as ordinary ground truth forever. The filter is now applied twice on
purpose — in the Mongo query and again in `build_labels` — and pinned by a test.

### 2. Identity is the file hash, not the drawing id

The obvious pairing check is "does this session name the same two drawings as the corpus
pair". It is wrong, and it fails closed, so it looks careful:

```
M745230A01 session : ref 6a829d45…  rev 6a829dd1…
M745230A01 pair    : ref 6a72ecba…  rev 6a72ecd0…
              hashes: ef0432233df6… / daabcba67d1d…  — identical on both sides
```

The same sheet uploaded twice gets a fresh `DrawingDocument` every time, so an id check refuses
precisely the case the bridge exists for. `EntityAddress.source_file_hash` had already written
down the principle — the hash *"proves the drawing is still the same drawing even when every
entity id has changed"* — and the check was built without reading its own codebase's answer.

A differing id with a matching hash is now a **note**, not a problem. A hash matching the
*other* side is reported as "this session's sides are swapped", because that is the wrong
pairing a person is most likely to produce by hand and the one whose output would look most
nearly correct.

### 3. The data is on Atlas; the tool defaults to localhost

`tools/eval_corpus.py` defaults `--mongo-uri` to `mongodb://127.0.0.1:27017`. Measured:

```
local : manual_check_sessions 0,  ground_truth_markings 0,  drawing_documents 59
atlas : manual_check_sessions 3,  ground_truth_markings 38, drawing_documents 59
```

Those two collections are **not in `sync_manager`'s synced set**, so against the tool's default
the bridge would have reported "no session covers this pair" — a true sentence with a false
implication. `from-manual-check` therefore defaults to the app's configured `MONGO_URI`
instead. `export` keeps the local default, correctly: it exports payloads from whatever store
you point it at, while this command only ever reads what the running app wrote.

## What was built

`infrastructure/eval/manual_check_bridge.py` — pure, no database, so it is testable against
literals — plus `tools/eval_corpus.py from-manual-check`.

It **emits a draft and stops.** Installing is still `label`, which still demands a named
annotator and a current guideline version. A corpus that a script can append to is a corpus
whose provenance is no longer "a human said so".

Addresses are **re-resolved, never copied**: a marking's stored handle is a claim about the
live drawing, while a label must address the *frozen payload*. Resolution goes through
`ground_truth.address_resolver` — called, not reimplemented, because a second opinion about
which entity a human meant would be invisible. Anything it declines to match is reported and
excluded, and by default the command **refuses to write a partial draft** rather than hand back
something silently short of the engineer's work.

⚠ **`category_source` has nowhere to go, and that is a real hole.** `GroundTruthMarking`
records whether a human chose the category or it was derived from the entity's zone, because
attribution measured over zone-derived categories compares `zone_detector` with itself — the
known tautology that makes the mutation corpus's 0.92 unreadable. `ExpectedFinding` has no such
field. The bridge tags those findings `[category:zone]` in their notes and counts them
separately, which keeps them *findable* but not *filterable*. The honest fix is a field on
`ExpectedFinding`, i.e. a corpus schema change.

## Verified

Dry-run over the real session (`6a83aeab…`, M745204N01), read-only:

```
ref payload 402 entities | rev payload 594 entities
live markings 7  ->  5 findings + 2 not_findings, 0 unresolved
resolved by: handle 7      handle-anchored 5/5      zone-derived 0
```

All seven resolved at the handle tier — worth noting against `ExpectedFinding`'s warning that
reference sheets are only 0.8–13% handle-addressable, because these markings were made on
*text the engineer clicked*, which is the addressable part. 21 unit tests cover the mapping,
the refusals and the identity check.

⚠ The three ADDED `notes_section` rows in that session are the same false-negative class the
maturity ledger calls its largest miss — added notes going entirely unreported. They are on
`M745204N01`, which **is not a corpus pair**, so this work cannot count toward Stage 0b until
that pair is exported. The bridge does not export pairs, deliberately: which sheets enter the
corpus is a decision about the measurement, not a conversion step.
