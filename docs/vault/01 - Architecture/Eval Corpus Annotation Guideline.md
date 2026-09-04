---
title: Eval Corpus Annotation Guideline
type: architecture
tags: [evaluation, ground-truth, annotation, corpus, ai-architecture]
status: active
guideline_version: 2026-08-06
date: 2026-08-06
verified-against: schema enforced by `infrastructure/eval/corpus.py`, whose `GUIDELINE_VERSION`
  constant must equal the `guideline_version` above or every label file is rejected. Re-measured
  2026-08-27 with `tools/eval_corpus.py status`: **8 pairs registered, 5 labelled, 1 of 3 held
  out** (it read "7 registered, 0 labelled" until then). ⚠ The MATCHED / `not_findings` section
  added 2026-08-27 deliberately did NOT bump `guideline_version` — the scorer never reads
  `not_findings`, so no score and no existing label could move; a bump would have invalidated all
  five.
---

# 📏 Eval Corpus Annotation Guideline

Part of Stage 0b in [[AI Maturity Ladder — Staged Plan]]. Status: [[00 - AI Maturity Status]].

> [!IMPORTANT]
> **This document is written before the first label, deliberately.** A corpus labelled under a
> shifting definition is worthless — you cannot tell a scoring change from a definition change after
> the fact. **Version this note. If a rule changes, re-label every affected pair or discard them.**

> [!NOTE] `status: active` as of 2026-08-06 — `guideline_version: 2026-08-06`
> The four open questions are resolved and folded into the rules below. Promotion happened
> **before** the first label rather than after two, which reverses the original plan
> deliberately: the corpus reached 7 registered pairs with 0 labelled, so resolving the
> questions first costs nothing, while labelling under a draft would have meant re-labelling
> every pair once they were settled.
>
> Three of the four had a **de facto answer already in the code**, which is what made them
> settleable without labelling experience — the resolutions are largely descriptive of
> behaviour the engine already has, and each is traced to the bug that produced it. The one
> genuinely free choice is the bulk threshold, and it is marked as a convention.
>
> `corpus.py` rejects a label file authored under a different `guideline_version`, so any
> later change to these rules is a re-label, not an edit.

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
| A title field whose cell holds two ruled rows, one changed | **1 CHANGED for that row** | See "Ruled rows" below — the rows are independent fields. |
| A value split across ruled sub-cells (DWG No.) | **1 CHANGED** for the whole value | The segments cannot change independently. |

### Ruled rows: independent fields, or one value?

A ruled cell divided into rows is **two findings or one, depending on whether the rows can
change independently.** The discriminator is the information, not the ruling.

| Case | Label | Why |
| :--- | :--- | :--- |
| 名称 / TITLE — machine name over part name | **one finding per changed row** | Different facts, changed by different edits. The engine agrees: it emits `TITLE` and `TITLE SUB` separately, precisely so "a change confined to one row cannot be told apart from a change to both". Measured on M7452A1N01 the upper row changed while the lower was byte-identical. See [[Gotcha - Title Read the Drawing Number and Was Never Compared]]. |
| DWG No. sub-cells — `M745203N01` = `M745` + `203` + `N01` | **one finding for the identifier** | Three segments of one number; none can change without the DWG No. changing. Reporting them separately gave four checklist items for one identifier. See [[Gotcha - Drawing Number Segments Reported as Separate Fields]]. |

Both halves were paid for with production bugs in opposite directions — merging hid a real
change, splitting invented three fake ones — so this rule describes behaviour the engine
already has rather than imposing a new one.

**Caveat on bulk additions.** Anchoring a 40-entity view addition to one handle means the engine
finds it if it reports *any* of those 40. That is generous, and it is the right generosity for
recall: an inspection tool that flags the view once has done its job. But it means recall on
bulk-add cases is easier than it looks — report those cases' counts separately so the aggregate is
not read as harder than it is.

### How large is "bulk", and what does it anchor to?

**The rule is semantic: if a checker would describe it in one sentence, it is one finding.**
"Iso view added." "Detail B added." The entity count is evidence for that, not the definition
of it.

**Set `is_bulk: true` when the change spans ≥ 5 comparable entities.**

> [!NOTE] Five is a convention, not a measured threshold — and that is fine.
> Its job is to be applied *uniformly*, not to be correct. Because bulk cases' counts are
> reported separately, anyone can recompute the aggregate under a different cut without
> re-labelling, which is exactly the property that makes the precise number cheap. Stated
> plainly rather than dressed up as a finding, per this vault's rule about keeping the
> reasoned and the measured apart.

**Anchor deterministically**, so two annotators pick the same entity and a re-label does not
move the address:

1. the view's own label or callout — `Ａ－Ａ`, `詳細B`, a section designation;
2. failing that, the largest text by height;
3. failing that, the lowest payload index (`REF#`/`REV#`).

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
- **A newly added revision / amendment row.** See below — it is present on every revised
  drawing by construction.

### Revision-table rows

**A *new* revision row is not a finding. A *missing* one is. An edit to an *existing* row is.**

A revision entry appearing on a revised drawing is the drawing correctly documenting itself; it
is true of every pair in this corpus, so flagging it tells a checker nothing. The two carve-outs
are where the real defects live: a revision that documents nothing, and a rewritten history row.

| Situation | Label |
| :--- | :--- |
| New revision row on the revision side | **not a finding** |
| Revision side has no new row at all | **1 finding**, `title_block`, status `REMOVED` — record the reasoning in `notes` |
| An existing revision row's text edited | **1 CHANGED**, `title_block` |

> [!WARNING] This rule will produce false positives, deliberately, and the number is the point.
> The engine reports these today. `amendment_table_bboxes` is used *"ONLY to reclassify
> drawing_views findings to title_block, never to exclude entities from comparison"* — only the
> column **headers** are dropped from the pool. So every human pair will show at least one
> title_block false positive from its new revision row.
>
> That is the correct outcome, and it follows this document's own precedent for shifted BOM
> rows: *"those are false positives and the number is real."* It converts an invisible product
> behaviour into a measured one. Expect it to motivate suppressing new revision rows in the
> engine — and when that decision is made it will have evidence behind it instead of taste.

---

## Recording MATCHED — the confirmed non-changes

> [!NOTE] Added 2026-08-27. **`guideline_version` is deliberately NOT bumped.**
> This changes nothing about what a *finding* is, so no existing label is now wrong and nothing
> needs re-labelling. Verified rather than assumed: `MATCHED` maps to `not_findings`
> (`manual_check_bridge.py`), `VALID_STATUSES` for a finding stays `{ADDED, REMOVED, CHANGED}`,
> and **the scorer never reads `not_findings`** — no reference to them in `scorer.py` or
> `tools/eval.py`. P / R / F1 cannot move because of anything in this section. A bump would
> invalidate the five pairs already labelled, which is exactly the cost this document warns about
> at the top; adding guidance that cannot change a score is not that.

A `MATCHED` marking is an engineer saying **"I looked at this and it did not change."** It becomes
a `not_findings` entry, which is what makes a false positive there *attributable* rather than
merely counted — the difference between "the engine reported 24 things that were not findings" and
"the engine reported this, and a human had already examined this exact entity and cleared it."

### The rule

> **Record MATCHED where you looked hard at something that could have been a discrepancy and
> concluded it was not.**

Not on everything that is fine. A reference sheet carries **~528 entities** (measured with
`tools/address_audit.py`), so exhaustive MATCHED is neither achievable nor asked for — and a
corpus padded with hundreds of trivially-identical entities buries the few rows that carry
information.

**What to record:**

- A value you had to compare digit by digit before deciding it was the same.
- Something that moved, or re-flowed, or re-wrapped, where the *text* turned out identical.
- An entity you expected to have changed with the revision and it had not.
- Anything you found yourself checking twice.

**What not to record:**

- Entities you never actually examined.
- Obviously identical geometry you skimmed past.
- Anything in a safe zone (`tolerance`, シム表) — those are never compared, so a MATCHED there is a
  statement about something no engine will ever look at.

### Why the hard cases and not the easy ones

These are the rows nearest the decision boundary — where the engine is most likely to fire wrongly,
and therefore the only place a `not_findings` entry is likely to ever be read. A MATCHED on two
manifestly identical strings documents a decision nobody would have questioned.

⚠ **This also matters for whatever trains on this corpus later, and in a way that is easy to get
backwards.** `GroundTruthMarking` records `MATCHED` as a first-class status precisely so these rows
survive — its docstring says the fields are *"a superset on purpose"* so that deciding how they
become training rows *"must not require re-labelling"*. But an explicitly recorded MATCHED and an
entity that simply went unmarked are **not the same claim**:

- an explicit `MATCHED` is a human asserting a negative;
- an unmarked entity means only that nobody said anything about it.

Treating "unmarked" as a confirmed negative assumes the engineer inspected all ~528 entities on the
sheet, which no one does. **The negatives in this corpus are sparse and non-random by construction**
— they are what someone chose to check — and any future training over them has to model that, not
assume a complete sweep. Recording the *hard* negatives is what makes the sparse set worth having.

### What the UI offers

`SelectionMenu` offers **MATCHED, ADDED, REMOVED**; CHANGED is the two-click pairing flow. MATCHED
records **both sheets** when the counterpart resolves unambiguously, and records one side — drawing
the badge on one sheet only — when several candidates tie, because a pair is never guessed.

⚠ **`NOT_A_FINDING` is not offered** (owner's call, 2026-08-18; see `SelectionMenu.tsx`). The status
still exists end to end and older markings still convert. In a manual-check pass its absence costs
nothing, because no engine has run and there is no engine finding to dismiss — `MATCHED` carries the
whole "I checked this and it is fine" signal. If a later phase shows engine output to a reviewer,
that gap reopens and the file notes restoring it is one line.

---

## Choosing the category

**Label by what the change is *about*, not by where it is drawn.**

That principle decides the cases that look ambiguous:

| Change | Category | Why |
| :--- | :--- | :--- |
| Amendment / revision-table content | `title_block` | The amendment table is title-block furniture; a checker reads it as metadata, not as drawing geometry. The engine reclassifies it the same way, so following the checker here happens to agree — the feared mismatch does not arise. See [[Gotcha - Full-Width Grid Labels Bridged Zones]]. |
| A balloon whose item number no longer resolves to a BOM row | `bill_of_materials` | It is a parts-list error that happens to be drawn on a view. The engine agrees: `reconcile_bom_with_balloons` emits `bom_balloon_mismatch`. |
| A balloon that appears because a view gained a component | *part of that view's ADDED finding* | Not a separate finding. One editorial act. |

> [!IMPORTANT] Do not bend a label toward the engine's category to avoid a mismatch.
> Category attribution is scored **independently** of detection, and since the mutator was made
> template-aware, attribution on mutation pairs is a tautology that measures nothing — the
> mutator and the engine now derive the category from identical zone boxes, so they agree by
> construction. **Human labels are the only place category attribution can be measured at all.**
> Matching the engine on purpose would destroy the last independent signal. See
> [[Gotcha - Mutation Labels Predate the Zone Template]].

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

## Resolved questions — 2026-08-06

All four are folded into the rules above; this is the record of *why*, so the reasoning is not
re-derived. Resolved **before** the first label rather than after two pairs, reversing the
original plan: with 7 pairs registered and 0 labelled, settling first cost nothing while
labelling under a draft would have meant re-labelling everything.

| # | Question | Resolution | Basis |
| :--- | :--- | :--- | :--- |
| 1 | Two ruled rows — one finding or one per row? | **One per changed row when the rows carry independent facts** (名称/TITLE); **one for the whole value** when they are segments of one identifier (DWG No.). | Descriptive: the engine already emits `TITLE`/`TITLE SUB` separately and already suppresses DWG No. segments. Both behaviours were bug fixes in **opposite** directions — merging hid a real change, splitting invented three fake fields. |
| 2 | Revision-table rows — finding or metadata? | **New row: not a finding. Missing row: a finding. Edited existing row: a finding.** | The original lean was right, sharpened by the two carve-outs. Accepts a deliberate, systematic false positive because the engine reports these today — the number is the point. |
| 3 | Amendment / balloon markers — follow the engine or the checker? | **Follow the checker, always.** Amendment content → `title_block` (which happens to agree with the engine); balloon-vs-BOM → `bill_of_materials`; a balloon riding an added view → part of that view's finding. | The question conflated two different objects. Also: human labels are now the **only** independent measure of attribution, so bending them toward the engine would destroy the signal. |
| 4 | How large is "bulk"? | **Semantic rule** (one checker sentence = one finding), with `is_bulk: true` at **≥ 5 comparable entities**, plus a deterministic anchor order. | The only genuinely free choice of the four, and marked as a convention rather than a finding. Bulk counts are reported separately, so the cut can be revisited without re-labelling. |

**What is still open, and is deliberately not a labelling question:** whether the engine should
*stop* reporting new revision rows. Question 2 makes that measurable rather than arguable; the
decision belongs to the engine, after the first pairs are scored.
