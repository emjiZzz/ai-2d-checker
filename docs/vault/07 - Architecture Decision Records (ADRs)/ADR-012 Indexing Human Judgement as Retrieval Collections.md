---
title: ADR-012 Indexing Human Judgement as Retrieval Collections
type: adr
tags: [adr, architecture, retrieval, knowledge, rag, measurement, ai-architecture]
status: accepted
date: 2026-08-17
supersedes: none
amends: none
related: [ADR-008 The Second Brain — Retrieval-Only Local Knowledge, ADR-009 Retiring the Standards Knowledge Track, Retrieval Annotation Guideline, 00 - AI Maturity Status]
---

# ADR-012 — Index the judgement we already have, so retrieval can be measured at all

**Status:** accepted · **Date:** 2026-08-17 · **Stage A** of the knowledge-corpus widening

---

## Context

The owner asked for *"our own AI that gathers all the knowledge in the system, so we can build a
better RAG."* Investigating what stood in the way produced a result that reframes
[[ADR-009 Retiring the Standards Knowledge Track]].

ADR-009 retired R3/R4 with the reasoning *"until `standard_chunks > 0`, no amount of engineering
moves any number"*, and set a reopening condition of ≥30 human-labelled query→chunk pairs clearing
a **chance floor ≤ 0.25**. That reads like annotation work. It is not. `metrics.chance_recall_at_k`
is, for the single-relevant case, exactly **`k/N`** over **one collection's own record count**:

| collection | N (before) | chance@5 | informative? |
| :--- | ---: | ---: | :--- |
| `standards` | 16 | 0.3125 | no |
| `domain_rules` | 6 | 0.8333 | no |
| `lessons` | 17 | 0.2941 | no |

**Every collection in this system was too small to be measured, and no encoder work could change
that.** Labelling 30 queries against a 16-record corpus would have produced a number the guideline
is obliged to reject. The binding constraint was never the labels and never the encoder — it was
corpus size, and it is per-collection, so growing one collection does nothing for another.

Meanwhile the database held human judgement that nothing indexed: **108 `AuditFeedbackDocument`
corrections** and **2,091 `AuditViolation`s**, against a `lessons` collection restricted to the 17
APPROVED violations that happened to carry usable text.

## Decision

**Index the human judgement the system already collects, as two new collections.**

| Collection | Source | Trust level |
| :--- | :--- | :--- |
| `corrections` | every non-retracted `AuditFeedbackDocument` | a human corrected this |
| `findings` | **every** `AuditViolation`, reviewed or not | mostly unreviewed engine output |
| `vault` | `docs/vault/**/*.md`, chunked by heading | engineering knowledge |
| `entities` | `ExtractedEntity` text | raw drawing content |

`vault` and `entities` landed in a second pass the same day, on the owner's instruction. Two
things about them are worth stating rather than assuming:

⚠ **`vault` is knowledge about the *system*, not about a drawing.** It answers *"why is this built
this way"* — which serves an agent or the copilot, and is the largest collection by some margin —
but it does not answer *"what does this tolerance mean"*. Its 989 records are **not** coverage of
the checker's domain, and reading them as such would be the most natural misuse of this work.

⚠ **`entities` is customer drawing content**, so it is client-local and carries the same privacy
constraint as `checker_remarks`. Its text is read as `properties["text"] or properties["value"]`
through `strip_mtext` — the same two rules `candidate_generator.py:462` uses — because a
collection that disagreed with the engine about what an entity *says* would be the drift shape
this codebase keeps paying for. Entities below `MIN_ENTITY_TEXT_CHARS = 3` are skipped; that
threshold is **a convention, not a measured optimum**, and is recorded as arbitrary.

`vault` excludes two directories, and both exclusions are load-bearing: the client-rules directory
is already the `domain_rules` collection (indexing it twice would put identical text in two
collections with different trust levels), and the learned-models directory is a gitignored
generated artifact (including it would make an otherwise reproducible collection vary per
install). The names are derived from `VaultSyncManager.CLIENT_RULES_DIR` and
`learning.config.MODEL_DIRNAME` rather than restated.

`vault` is deliberately **not** client-local: it is git-tracked and identical on every install at
a given commit, so a committed baseline value for it is valid. It does churn with ordinary
documentation work, which is a baseline-regeneration nuisance and not the property that set is
about.

### 1. `findings` is a strict superset of `lessons`, and they stay separate collections

The obvious simplification — widen `lessons` to all violations and filter by `resolution_type` at
query time — is **rejected**, because the chance floor is per-collection. Merging destroys the one
collection whose trust level is unambiguous, in exchange for nothing: `findings` can be measured
either way. They answer different questions (*"what has a human confirmed"* vs *"has this system
ever reported anything like this"*) and are scored independently.

They share `service.violation_record` so the two can never disagree about how a violation becomes
text. **The generalisation was proven byte-identical on the `lessons` text first** — pinned by
`test_an_approved_violation_indexes_exactly_the_text_it_did_before`, which writes the expected join
out literally. `index_builder._digest` hashes texts only, so `resolution_type` could be added to
*metadata* without drifting any label authored against `lessons`.

### 2. Review state is carried in `Record.source`, not only in metadata

`"Confirmed finding"` / `"Rejected finding"` / `"Unreviewed finding"`. `source` is what
`Record.citation()` renders, so a consumer cannot show an unreviewed finding without saying it is
unreviewed. An unrecognised `resolution_type` reads as **unreviewed**, never as confirmed — the
safe direction, pinned by test.

This is [[ADR-008 The Second Brain — Retrieval-Only Local Knowledge]]'s named hazard arriving
through a new door: *"surfacing near-miss rules as authoritative is a recall attack."* 1,953 of
2,091 violations have no supervisor verdict. A collection that size is only safe if every hit
declares what it is.

### 3. A correction's verb goes in the indexed text, not only in metadata

`_collapse_duplicate_texts` drops byte-identical texts to protect the chance floor's denominator.
With the verb in metadata alone, two corrections that reached **opposite** verdicts on the same
entity text are byte-identical, and the net silently keeps one — discarding the most informative
row in the corpus. **Verified, not reasoned about:** simulating the metadata-only design collapses
the pair to a single record.

### 4. Retracted corrections are never indexed

Same rule `trainer.build_bundle` applies for training. The row survives in Mongo as the audit trail
of who taught the model what; indexing it would let a withdrawn judgement be cited back at the next
checker as though it still stood. Implemented in `feedback_record`, so the retrieval side has one
implementation of the rule rather than a filter that can fall out of step with the query.

### 5. Both collections are client-local and must not be pinned in the committed baseline

They are sourced from the local MongoDB, so their counts and digests vary per install. Pinning them
would make every other machine read a normal difference as a regression — the reason `domain_rules`
was already excluded. ⚠ `standards` and `lessons` are **also** Mongo-sourced and are **not**
excluded; the committed `retrieval-baseline.json` pins both at 0 and both are now non-zero here.
Recorded as a pre-existing defect rather than fixed in this change, so the two are not conflated.

## Consequences

**Two collections are measurable, for the first time in this system's history.**

| collection | N | duplicates dropped | chance@5 | informative? |
| :--- | ---: | ---: | ---: | :--- |
| `vault` | **989** | 1 | **0.0051** | **yes** |
| `findings` | **410** | 1,681 | **0.0122** | **yes** |
| `entities` | **433** | 6,483 | **0.0115** | **yes** |
| `corrections` | **84** | 24 | **0.0595** | **yes** |
| `lessons` | 17 | 67 | 0.2941 | no (unchanged — the refactor is inert) |
| `standards` | 16 | — | 0.3125 | no (untouched) |
| `domain_rules` | 6 | — | 0.8333 | no (untouched) |

**Four of seven collections are measurable. Before this change, none were.**

**The duplicate rate is a finding about the data, not a detail: 1,681 of 2,091 violations are
byte-identical to another.** The violation corpus is 410 distinct texts wearing 2,091 badges. Any
plan that budgeted on "2,000 records" was wrong by 5×, and `_collapse_duplicate_texts`'s docstring
already said where that belongs: *"a non-zero count here is a fact about the source, and the source
is where it should be fixed."* Whether re-audits are duplicating violation rows is **not
investigated here** and is left open rather than guessed at.

**This does NOT reopen ADR-009, and the distinction matters.** That ADR's condition is about the
**`standards`** collection, which is untouched — still 16 chunks, still a 0.3125 floor, still
unmeasurable. What changed is that the *system* now has collections worth measuring. Anyone citing
this ADR as having reopened the standards knowledge track is misreading it.

**A latent defect was found and fixed because this work made it load-bearing.** Chunk ids are
`sha256(f"{file}::{heading}")`, and a heading is not unique within a note — the staged plan carries
six `Exit criterion` sections. Twelve of the vault's 990 chunks shared four ids. Inert today
(nothing reads a chunk id) and about to become a **silently generous retrieval metric** at Stage C,
where `RetrievalLabel.relevant_ids` names exactly those ids. Fixed by suffixing repeats only, so
no existing collection's ids move; 990 chunks now yield 990 ids. See
[[Gotcha - One Heading Twice in a Note Is One Retrieval Record]].

**Nothing leaked onto the comparison engine.** The cross-track invariant holds byte-identical:
**P 0.98 (48/49) / R 0.87 (48/55) / F1 0.92, macro 0.88** under `--provenance mutation`.
`pytest` 1,210 passed / 3 skipped / 0 failed; ruff clean on every changed file. No cache bump —
neither spatial matching nor zone extraction is touched.

**No rung moved, and none was claimed.** Rung 1 is per-category P/R/F1 over ≥8 human-labelled
*comparison* pairs; the corpus is 2/8 and this work does not touch it. Labelling `M745230A01`
remains the comparison engine's critical path.

> [!WARNING] **Known limitation, recorded rather than hidden: both new indexes are built once and
> then frozen.**
> `bootstrap_retrieval_indexes` builds only collections whose index is not already `OK`, so after
> the first build nothing refreshes them. `lessons` does not have this problem because
> `review_violation` calls `rebuild_lessons_index` on every supervisor verdict; **there is no
> equivalent call on the correction path**, so a `corrections` index goes stale the moment the next
> correction is clicked.
>
> Deliberately **not** wired in this change. The obvious fix — rebuild on every correction — puts a
> full TF-IDF refit over the whole corpus on a hot user-facing click, and TF-IDF's idf term is a
> property of the corpus so there is no cheap incremental append (see `service.py`'s module
> docstring). That is a real design decision about latency, and it should be taken deliberately
> rather than inherited from `lessons`, whose corpus is 24× smaller.
>
> Until it is taken, treat both collections as **a snapshot with a build date**, not a live view.
> `manifest.source_digest` is what detects the staleness; nothing consumes it yet.

## What this unblocks, and the order it must happen in

⚠ **Corpus growth invalidates relevance labels** — `LabelSet.source_digest` pins the index a label
was authored against and `LabelDriftError` refuses to score on a mismatch. So:

1. **Stage A (this ADR) — widen the corpus.** Done for `corrections`, `findings`, `vault` and
   `entities`. **Adding any further source belongs here, before Stage C, not after.**
2. **Stage B — collect real queries. Landed 2026-08-17.** `retrieval/queries.py` holds a query
   store that records **neither `source_digest` nor `guideline_version`** — that absence is the
   design, and is what lets this stage run ahead of Stage C and in parallel with more sources.
   Origin is required (`production` / `checker` / `finding`), mirroring `labels.Provenance`.
   Stored under gitignored `storage/retrieval/queries/`: a harvested query embeds the drawing
   file name.

   **Harvest result: 44 drawings yield 19 distinct production queries — below the
   `MIN_QUERIES_FOR_VERDICT = 30` gate.** The production path alone cannot supply a scoreable
   query set, so checker-asked questions remain required and cannot be generated. The tool
   reports this rather than leaving it to be inferred from the origin column.

   🔴 **Reading those 19 exposed a dead branch in the production query itself**: it reads
   `drawing.metadata["layers"]`, a key nothing writes, on all 44 drawings — so the "strongest
   signal" its own comment names has never contributed, and a production query is the file name
   plus constant entity-type noise. Found, not fixed: the repair changes what the audit
   retrieves *and* what "the production query" is, so it must move together with a re-harvest.
   See [[Gotcha - The Strongest Signal in the Audit Query Was Never Written]].
3. **Stage C — label ≥30 pairs, once the corpus has stopped moving. Dry run landed 2026-08-17;
   the labelling itself is blocked on human input and cannot be tooled around.**

   `labels.synthetic_label_set` + `retrieval_eval.py smoke` generate a deliberately **circular**
   label set — each chunk's own heading as the query, its own id as the answer — and score it.
   The guideline had described this smoke test since 2026-08-07 with **no implementation**, so
   the one cheap check available before an annotator commits hours could not be run.

   **The gates behave exactly as designed.** On `vault`: chance 0.01, lift +0.67, 40 queries —
   three of four gates pass and the verdict is still withheld, naming `labels are synthetic` as
   the sole failure. Before Stage A **no collection could clear the chance floor**; that was the
   gate this ADR existed to move, and it moved.

   | collection | records | chance@5 | queries stored | what is missing |
   | :--- | ---: | ---: | ---: | :--- |
   | `standards` | 16 | 0.3125 ✗ | 19 | a bigger corpus **and** 11 more queries |
   | `vault` | 989 | 0.0051 ✓ | 0 | queries, then labels |
   | `findings` | 410 | 0.0122 ✓ | 0 | queries, then labels |
   | `entities` | 433 | 0.0115 ✓ | 0 | queries, then labels |
   | `corrections` | 84 | 0.0595 ✓ | 0 | queries, then labels |

   ⚠ **Note what this table says: the collection with queries cannot be measured, and the
   collections that can be measured have no queries.** The 19 harvested queries are `standards`
   queries because that is what the audit pipeline searches. Stage C cannot complete on any
   collection today, and no amount of tooling changes that — the missing input is a person
   saying what they would ask and which chunk answers it.
4. **Stage D — the encoder bake-off.** `retrieval/encoder.py` exists as a seam so a dense encoder
   must *win* against lexical rather than be assumed better. Stage C is what makes that judgeable.

Doing any of it after labelling means re-labelling.

## Alternatives rejected

| Alternative | Why not |
| :--- | :--- |
| **Widen `lessons` to all violations, filter at query time** | Destroys the only collection with an unambiguous trust level, and buys nothing — the chance floor is per-collection, so `findings` is measurable as its own collection regardless. |
| **Index only *reviewed* violations (≈107)** | Chance floor 0.047, so it would clear the gate. Rejected because it discards the "has this system ever reported anything like this" question entirely, and the review queue's coverage (107 of 2,091) is an artifact of nobody having worked it, not a judgement about relevance. |
| **Improve the encoder first** | The wasted instinct ADR-009 recorded as a negative result, and it was right: with no measurable collection, a dense encoder would have been tuned against nothing. Stage A is what makes Stage D judgeable. |
| **Deduplicate violations at the source before indexing** | Correct eventually, and out of scope here: it changes product data on a hypothesis about re-audits that has not been tested. The net already reports the duplication loudly, per record and in aggregate. |
| **One "everything" collection** | A single index over standards, rules, corrections and findings would have a healthy N and a meaningless trust model — every hit would need its provenance re-derived, and the recall attack in decision 2 would apply to all of it at once. |

## Related

- [[ADR-009 Retiring the Standards Knowledge Track]] — the reopening condition this does *not* meet
- [[ADR-008 The Second Brain — Retrieval-Only Local Knowledge]] — decision 1 (retrieval-only) holds:
  nothing here generates prose
- [[Retrieval Annotation Guideline]] — the four gates, and why labels expire
- [[00 - AI Maturity Status]] — the work log entry and the unchanged rung
