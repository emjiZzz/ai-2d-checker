---
title: Eval Corpus Annotation Guideline
type: architecture
tags: [evaluation, ground-truth, annotation, corpus, ai-architecture]
status: draft
date: 2026-08-05
verified-against: schema enforced by `infrastructure/eval/corpus.py`; still zero labels written
---

# 📏 Eval Corpus Annotation Guideline

Part of Stage 0b in [[AI Maturity Ladder — Staged Plan]]. Status: [[00 - AI Maturity Status]].

> [!IMPORTANT]
> **This document is written before the first label, deliberately.** A corpus labelled under a
> shifting definition is worthless — you cannot tell a scoring change from a definition change after
> the fact. **Version this note. If a rule changes, re-label every affected pair or discard them.**

> [!WARNING] `status: draft`
> The rules below are reasoned, not yet validated against real labelling. Expect them to change once
> the first two pairs are annotated. Promote to `status: active` only after ≥2 pairs have been
> labelled by hand and the ambiguities recorded at the bottom have been resolved.

---

## What a label is

One `ExpectedFinding` per **change a human checker would flag**, carrying:

| Field | Meaning |
| :--- | :--- |
| `entity_handle` | The **address** of the entity, on the revision side, or the reference side for a REMOVED. Primary matching key — the scorer resolves this before falling back to spatial or text similarity. Two forms; see below. |
| `category` | One of the six canonical categories. Must come from `taxonomy.py`, never invented. |
| `status` | `CHANGED` / `ADDED` / `REMOVED` |
| `ref_text` / `rev_text` | What it said before and after. Empty on the absent side. |
| `notes` | Free text for the annotator's reasoning. Not scored, but read when a disagreement is investigated. |
| `is_bulk` | `true` on a bulk addition anchored to one entity (see the caveat below). Scored counts are reported separately for these. |

### The address has two forms — copy it, do not type it

This guideline originally assumed every finding could name a DXF handle. It cannot. Measured
over 3615 entities in the first six exported drawings, **handle and `parent_handle` are perfectly
mutually exclusive**: anything exploded out of a block carries no handle, and this client's
*reference* sheets keep almost everything inside blocks. Text-entity handle coverage is 92% on a
re-traced revision sheet and **0.8–13% on a reference sheet** — the side a REMOVED must anchor to.
See [[Gotcha - Exploded Block Children Have No Handle]].

So an address is either:

| form | example | when |
| :--- | :--- | :--- |
| DXF handle | `REV-1B2A` | whenever the entity has one |
| payload address | `REF#412` — line 412 of `ref.entities.jsonl` | when it does not; always available |

`tools/eval_corpus.py worksheet --pair-id <ID>` prints the right one per entity in its `address`
column. **Copy that column verbatim.** An unprefixed address is read as the revision side, except
on a REMOVED — but write the prefix anyway; the worksheet already does.

A payload address is only stable because the payload is frozen by sha256 in the committed
manifest. If a pair is ever re-exported, its labels must be re-checked — the loader will not
silently accept the new bytes.

The scorer treats a *found but mis-statused* finding as a **downgrade**, not a miss — it reports a
status-confusion matrix separately from recall. Category attribution is likewise scored
independently of detection. So a label being slightly wrong on `status` or `category` degrades one
metric rather than corrupting all of them.

---

## The core question: one finding, or two?

This is the hardest rule and the one that will drift. It is also exactly what
`marking_reconciler.py` answers heuristically at runtime (`SIMILARITY_THRESHOLD = 0.82`,
`MAX_NORMALIZED_MOVE = 0.25`) — see [[Gotcha - Title Upper-Left Double-Reported by Scale]] for what
happens when the engine gets it wrong in both directions at once.

**Rule: label by author intent, not by entity count.**

| Situation | Label as | Why |
| :--- | :--- | :--- |
| A note's text edited in place | **1 CHANGED** | One editorial act. |
| A note **moved and edited** | **1 CHANGED** | Still one editorial act. The engine may emit REMOVED+ADDED; that is the engine's reconciliation problem, not a labelling one. |
| A note **moved, text identical** | **not a finding** | Pure relocation with no semantic change. Record it in `notes` so the false-positive is attributable. |
| One dimension value changed | **1 CHANGED** | |
| A whole view added, carrying 40 entities | **1 ADDED**, anchored at the view's most identifying text | Not 40. A checker writes "iso view added" once. Note the caveat below. |
| Two independent notes both edited | **2 CHANGED** | Two acts. |
| A BOM row edited | **1 CHANGED** per row, not per cell | Unless two cells changed for unrelated reasons — then use judgement and record it. |
| A BOM row inserted, shifting all rows below | **1 ADDED** | The shift is a consequence, not a change. If the engine reports the shifted rows, those are false positives and the number is real. |

**Caveat on bulk additions.** Anchoring a 40-entity view addition to one handle means the engine
finds it if it reports *any* of those 40. That is generous, and it is the right generosity for
recall: an inspection tool that flags the view once has done its job. But it means recall on
bulk-add cases is easier than it looks — report those cases' counts separately so the aggregate is
not read as harder than it is.

---

## What is *not* a finding

Do not label these. Getting this list wrong inflates recall by making the engine's misses invisible.

- **Safe zones are never compared.** `tolerance` and the shim table (シム表) are detected, alignable,
  and deliberately excluded — reference data that does not change between revisions. See
  [[Gotcha - Optional Zones and the Shim Table]]. A difference inside one is not a finding.
- **Sheet frame, margin grid labels** (`Ａ`, `１`, fullwidth or ASCII) — see
  [[Gotcha - Full-Width Grid Labels Bridged Zones]].
- **Pure relocation with identical text** (above).
- **Rendering or encoding artefacts.** If `%%c120` on one sheet and a dimension-style default on the
  other denote the *same* measurement, that is not a change — see
  [[Gotcha - The Differ Compared Text Only]], which is why dimensions compare on numeric
  `measurement` rather than display text.
- **Anything outside the `views` box that belongs to no zone.** `drawing_views` is now scoped
  strictly to the views box, so out-of-zone content is genuinely out of scope — see
  [[Gotcha - drawing_views Was the Residual, Not the Views Box]]. If you believe a real change sits
  there, that is a **zone-detection bug**: record it in `notes` and file it, do not label it as a
  comparison finding.

---

## Normalisation — what counts as "the same text"

Follow the engine's own definition so labels and inference cannot drift apart. The canonical
normaliser is `SpatialDiffer._normalize_text`, reused by `learning/feature_extractor.py` for exactly
this reason.

- **NFKC-fold before comparing.** `Ｃ１` and `C1` are the same text. This corpus is Japanese CAD and
  writes callouts fullwidth; two separate production bugs came from forgetting it
  ([[Gotcha - Fullwidth Callouts Were Never Classified]],
  [[Gotcha - Full-Width Grid Labels Bridged Zones]]). **When a rule keys on Latin letters or digits
  here, assume fullwidth input.**
- **`%%c` → `Ø`, `%%d` → `°`, `%%p` → `±`** are transcodings, not changes.
- **Whitespace and line-break differences inside an MTEXT** are not changes.
- **`22.7` vs `22.70`** — not a change. Numeric equality wins over string equality.
- **`22.7±0.02` vs `22.7±0.05`** — **a change.** The tolerance is the point.

---

## Mutation pairs label themselves

Pairs from `eval/mutator.py` are labelled **by construction** — the operator knows which handle it
touched and what category that implies. Do not hand-label them. Two rules:

1. **`provenance` must be recorded** on every pair (`human` | `mutation`). Several exit criteria in
   the plan turn on the distinction — the Stage 3 learned matcher is trained on mutation pairs, so
   only **human** pairs can gate it.
2. **A mutation that produces no visible change is a bug in the mutator**, not a zero-finding pair.
   The only legitimate zero-finding pair is `null_mutation`, which re-saves without editing.

---

## Held-out discipline

- **3 human pairs are held out permanently.** They are touched exactly once, at the end of Stage 0.5,
  to validate the swept constants. Never during a sweep, never for debugging.
- **Coarse sweeps run on mutation pairs**; human pairs validate.
- If a held-out pair is ever accidentally used for tuning, it is **burned** — mark it in the manifest
  and replace it. Do not quietly keep using it.

---

## Provenance and confidentiality

Entity payloads carry the customer's Japanese text and are the same confidentiality class as the
source DXFs, which are already gitignored.

| | Location | Contents |
| :--- | :--- | :--- |
| Committed | `tests/fixtures/eval/` | `manifest.json` (pair ids, per-payload sha256, category counts) + label files |
| Gitignored | `storage/eval/pairs/` | Entity payloads |

The runner asserts payload sha256 against the manifest and **fails loudly on drift**. A silently
edited fixture is the one failure mode that would invalidate every historical number at once.

## The workflow, end to end

```
tools/eval_corpus.py export    --pair-id <ID> --ref <file_name|_id> --rev <file_name|_id> [--held-out]
tools/eval_corpus.py worksheet --pair-id <ID>      # neutral annotation aid + empty label draft
#   ... fill in the draft against this document ...
tools/eval_corpus.py label     --pair-id <ID> --from <draft.json>
tools/eval_corpus.py verify                        # digests + offline readiness
tools/eval_corpus.py status                        # progress against Stage 0b's exit criteria
```

The worksheet is a naive, deliberately high-recall text-set difference over the engine's own
*normaliser* — **not** its differ. That distinction is the point: normalising the same way keeps
labels and inference on one definition of "the same text" (the rule above), while staying clear of
the differ keeps the engine's own misses visible to you. A worksheet pre-filled from engine output
would make false negatives invisible, and false negatives are the gap this corpus exists to close.

Three things the tooling enforces so you do not have to remember them: an invented category is
rejected, a label file authored under a different `guideline_version` is rejected, and held-out
pairs are unreachable without a written reason that is logged.

---

## Open questions — resolve before promoting to `active`

Recorded rather than guessed, per this vault's directive to keep the reasoned and the measured apart.

1. **Title-block fields with two ruled rows** — when only the upper row changes, is that one finding
   or one per row? [[Gotcha - Title Read the Drawing Number and Was Never Compared]] shows the
   extractor merged them and hid a real change, so the answer affects what "correct" means here.
2. **Revision-table rows.** A new revision entry is expected on every revised drawing. Is it a
   finding, or metadata? Leaning "not a finding", but it must be decided once and applied uniformly.
3. **Amendment/balloon markers.** Currently reclassified to `title_block`
   ([[Gotcha - Full-Width Grid Labels Bridged Zones]]). Should the label follow that engine choice,
   or describe what a checker would say? Labels should generally describe the checker, not the
   engine — but that would guarantee a category mismatch here.
4. **How large is "bulk"?** The one-label-per-added-view rule needs a threshold, or a stated
   judgement call, before the first multi-view pair is annotated.
