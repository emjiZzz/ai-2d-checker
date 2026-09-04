---
title: ADR-009 Retiring the Standards Knowledge Track
type: adr
tags: [adr, architecture, rag, retrieval, knowledge, second-brain, scope, ai-architecture]
status: accepted
date: 2026-08-10
supersedes: none
amends: ADR-008 The Second Brain — Retrieval-Only Local Knowledge
related: [ADR-008 The Second Brain — Retrieval-Only Local Knowledge, ADR-005 Local-Only Processing with Cloud Licensing, ADR-007 Re-scoping the Maturity Ladder, Standards Knowledge — Staged Plan, Retrieval Annotation Guideline]
---

# ADR-009 — Retiring the standards knowledge track: R3 and R4 stop before they start

**Status:** accepted · **Date:** 2026-08-10 · **Amends:** [[ADR-008 The Second Brain — Retrieval-Only Local Knowledge]]

Work retired: [[Standards Knowledge — Staged Plan]], stages R3 and R4 ·
Evidence: `tests/fixtures/retrieval/retrieval-baseline.json`

> [!NOTE] Renamed 2026-08-10 — this track was called **"the Second Brain"**
> That name collided with the vault itself, which the MOC titles *"AI-2D-Checker System Second
> Brain"* and which `vault_sync.py` and `auto_doc.py` both call *"the Obsidian Second Brain"*. So
> *"the Second Brain is retired"* read as *"the vault is retired"* — and this project has already
> been burned once by a phrase that meant nothing to the person who found it ("the four V2 gaps").
> **"Second Brain" now means the vault and only the vault.** The knowledge subsystem is the
> **standards knowledge track**.
>
> [[ADR-008 The Second Brain — Retrieval-Only Local Knowledge]] keeps its original title
> deliberately: an ADR records what was decided *and under what name*. Retitling a ratified decision
> erases that. Its banner carries the pointer instead.

---

> [!WARNING] **Amended 2026-08-10 — this ADR's central premise was false.**
> The decision below rests on the census: `standards` = 0, and the reading that *"the standards
> subsystem has simply never been used, by anyone, ever"* — therefore the track is **blocked on
> data, not engineering**, therefore retiring it is *"a scoping call, not an engineering one."*
>
> **The corpus was empty because the upload could not succeed.** The desktop app posted to
> `POST /api/v1/standards`, which is **GET-only**; the ingest endpoint is
> `POST /api/v1/standards/upload`. Every attempt returned **405 Method Not Allowed**, surfaced in
> the dialog as *"Ingestion Fault: Method Not Allowed."* Confirmed against the running server's
> own route table, and fixed at `createStandardsSlice.ts` (pinned by
> `createStandardsSlice.test.ts`, mutation-checked).
>
> So *"nobody has uploaded a standard"* was true, and *"nobody chose not to"* was the part nobody
> checked. **A count of zero is evidence about the system, not about the users, until you have
> shown the path works** — the same rule [[Gotcha - A Count You Could Not Take Is Not Evidence]]
> states for dismissals, applied to a census instead of a query. This is the fourth defect of the
> shape *"a working endpoint that nothing correctly reached"*; see
> [[Gotcha - A Tested Endpoint That Nothing Ever Called]].
>
> **What this does and does not change.** R3/R4 are machinery for *distributing* rules between
> machines, and that is still premature while the corpus is empty **today** — so the retirement
> stands for now and nothing is un-retired by this amendment. What changes is the **reopening
> condition**: it was written as a data question the business had implicitly already answered by
> never uploading anything. That answer was never given. The condition is now live, and cheap to
> test: with the upload fixed, ingest one real standard and see whether the corpus grows.
>
> Two ingest defects found while fixing this would have poisoned exactly that test, and are also
> fixed: a parse yielding **zero chunks** silently substituted a chunk containing only the typed
> title and returned 200 (so a scanned PDF ingested "successfully" and held nothing, permanently,
> because re-upload hits the duplicate-hash bypass); and `.xls` was advertised by three separate
> format lists and readable by none of them. See
> [[Gotcha - A Standard That Ingested Nothing Reported Success]].
>
> **Do not cite this ADR's census as evidence about demand.** Cite it as of 2026-08-07, when the
> only thing it could measure was a broken upload path.

## Context

[[ADR-008 The Second Brain — Retrieval-Only Local Knowledge]] planned five stages over the
standards-audit pipeline. R0 (delete the fakes), R1 (lexical retrieval) and R2 (the metric) all
landed on 2026-08-07. R2's exit criterion was a `recall@5` against a committed baseline.

**It produced a census instead of a score, because the corpus is empty.** Run against the live
database for the first time:

| Collection | Records | Why |
| :--- | ---: | :--- |
| `standards` | **0** | `standard_documents` = 0, `standard_chunks` = 0. No standard has ever been uploaded to this system. |
| `lessons` | **0** | 1,322 audit violations exist and **every one is unreviewed** — 0 approved, 0 rejected. |
| `domain_rules` | 6 | Two client rule notes in the gitignored vault folder. Client-local. |

The database is otherwise busy — 8,055 extracted entities, 108 rooms, 58 audit sessions. This is
not a fresh install. **The standards subsystem has simply never been used**, by anyone, ever.

R3 (two-tier bundles) and R4 (knowledge sync) are both machinery for *moving rules between
machines*. The binding constraint sits one level below that: the vendor baseline tier has no
content and the standards corpus has no documents. Building distribution for an empty payload is
the same error as building retrieval over an empty index, one stage later and considerably more
expensive to unwind.

The staged plan named that fork and refused to pick a side, correctly: *"either upload real
standards and label ~30 queries, or take the decision that the standards-audit pipeline is not the
product and stop the track here. That is a scoping call, not an engineering one."*

## Decision

**The standards-audit pipeline is not the product. The standards knowledge track stops at R2.**

This is a product decision, taken by the project owner on 2026-08-10, not a conclusion derived from
the measurement. The measurement establishes only that the corpus is empty; it does not say whether
filling it is worth doing. That question was put with four options and this is the answer.

R3 and R4 are **retired**, not deferred. R4 was already `⏸ DEFERRED to prod`; the difference matters
and is the point of writing this down — a deferred stage is waiting for a trigger, and a retired one
is not. Neither is now waiting for anything.

### What is retired

| ADR-008 decision | Status now |
| :--- | :--- |
| 2 — two tiers (vendor baseline + per-client overlay) | **Retired unbuilt.** Neither tier exists. **The hazard it was built for does not retire with it** — see *Re-homed*, below. |
| 3 — hosting deferred until production | **Moot.** There is nothing to host. |
| 3's obligation — *"two seams must exist before the fork arrives"* | **Half met, half lapsed.** The bundle *source* abstraction was built early in R1 (`RecordSource` is a function returning records, not a path) and survives. The **minimized feedback record as a first-class type was R3's and does not exist.** |
| 4 — the sync payload is fixed at `(pattern, category, count, client_id)` | **Lapses as a build item; retained as a constraint.** If sync is ever revisited, that payload is still the decision, and the reasoning in ADR-008 (minimization, not encryption) still holds. |
| 5 — the customer LAN server is rejected | **Unchanged.** Rejected on cost, independently of this. |

### What is kept, and why deleting it would be a mistake

- **`infrastructure/retrieval/`** — real char n-gram TF-IDF, exact brute-force cosine, 6–9 ms,
  offline, 34 tests. It replaced nine deleted fake modules; deleting it now would leave the audit
  path on the MongoDB substring fallback *and* destroy the artifact that proves the negative result.
- **The metric harness** (`metrics.py`, `labels.py`, `evaluate.py`, `tools/retrieval_eval.py`) and
  [[Retrieval Annotation Guideline]]. These are what make the track cheap to restart, and the
  committed `retrieval-baseline.json` is the evidence for the census. A negative result with its
  measuring instrument deleted is an anecdote.
- **R0's deletions.** Permanent, and independent of this decision — the nine modules were removed
  for lying about their capability, not for being on this roadmap. `tests/test_no_fake_ai_capability.py`
  stays and keeps working whatever happens to the track.

### Re-homed — the part that must not be lost

R3 carried one live defect fix and one live hazard. Both belong to the **comparison engine**, not
to the standards track, so retiring R3 would orphan them. They move to
[[00 - AI Maturity Status]]'s unblocked-engineering list.

1. **`AutoDocEngine.process_feedback_event` counts dismissals with no `client_name` filter**
   (`infrastructure/knowledge/auto_doc.py:43`), then files the resulting rule under
   `feedback.client_name`. A pattern dismissed **once at each of three different clients** reaches
   N≥3 and is written into `Learned_Rules_{whichever_client_tripped_it}.md`. That is cross-client
   contamination in the exact mechanism ADR-008's overlay tier existed to prevent — and with the
   overlay tier retired, **nothing else prevents it.**

2. **A second defect, found while confirming the first.** The count is wrapped in
   `except Exception: dismiss_count = getattr(feedback, "_mock_dismiss_count", 3)` — so **any**
   database error defaults the count to exactly the promotion threshold, and a single dismissal
   writes a permanent rule. Same class as the swallowed `AttributeError` R0 found
   ([[Gotcha - A Swallowed AttributeError Made a Write Path a Permanent No-Op]]), pointed the other
   way: that one made a write path silently do nothing, this one makes a failure silently do
   something.

Both matter more than they did yesterday, because `08 - Client Domain & CAD Rules/` is the **only**
directory in this vault that is a runtime input to the comparison engine — `vault_sync.get_learned_dismissal_rules()`
feeds `safe_filter` and the zone pools. A contaminated rule there suppresses real findings, in the
false-negative direction, in a system whose headline gap is that false negatives have never been
measured.

---

## Consequences

**ADR-008's headline consequence is reversed, and this is the real cost.** It opened with *"the
standards-audit pipeline gets an owner"*. Retiring the track takes the owner away again: the
pipeline is once more live product surface with no metric and no roadmap. What is different — and
what makes this survivable where it was not before — is that it is no longer running on fiction.
R0 deleted the fake stack, R1 replaced it with something honest that reports `MISSING` / `EMPTY` /
`STALE` rather than returning plausible noise, and `test_no_fake_ai_capability.py` prevents the
regression. **An unowned pipeline that says it has nothing is a different risk from an unowned
pipeline that invents answers.**

**The pipeline is not deleted by this decision, and that is deliberate.** Stopping a roadmap is not
the same as removing a surface. Whether to remove the standards-audit endpoints and their UI
entirely is a **separate decision, explicitly left open and recorded here so it does not become a
phantom.** It should be taken on product grounds, with the same care ADR-006 took over the three
comparison methods — including counting what is live in the database first.

**`recall@5` on this pipeline never existed and now never will.** That is the second retrieval
metric this project has retired: [[ADR-007 Re-scoping the Maturity Ladder]] retired the old rung 1's
recall@5 on the comparison engine because there was no retrieval to measure, and this retires it on
the standards engine because there is no corpus to measure over. Both were retired for the honest
reason rather than left to read 0 forever.

**Nothing changes on the comparison engine.** The cross-cutting invariant held throughout R0–R2 —
the eval corpus scores **P 0.98 / R 0.87 / F1 0.92** against `baseline-v43.json`, byte-identical at
every stage — so nothing leaked across the track boundary and there is nothing to unwind. Labelling
remains the comparison engine's critical path, exactly as it was before the standards knowledge
track opened.

**No cache bump.** Neither spatial matching nor zone extraction is touched. v43 stands.

---

## Reopening condition

Stated concretely, because *"if we ever need it"* is how a retired stage becomes a phantom. The
track reopens when **both** hold:

1. `standard_chunks > 0` — real standards uploaded, not fixtures. Verify with
   `python tools/retrieval_eval.py census`.
2. ≥30 hand-labelled `(query → relevant chunk)` pairs at `provenance: human`, clearing all four
   gates in [[Retrieval Annotation Guideline]] — ≥30 queries, chance floor ≤0.25, lift ≥0.15, no
   synthetic labels.

Then regenerate the baseline (`python tools/retrieval_eval.py census --baseline`) and R3 is a
question again. **Until (1), no amount of engineering moves any number**, which is the negative
result this ADR rests on.

---

## Alternatives rejected

| Alternative | Why not |
| :--- | :--- |
| **Load real standards, then label ~30 queries, then resume R3** | The engineering-optimal path, and it was offered first. Rejected on product grounds: it commits annotation effort and an upload workflow to a subsystem the owner has decided is not the product. Preserved verbatim as the reopening condition above, so choosing it later costs nothing but the labels. |
| **Narrow R3/R4 to `domain_rules` only** | The one collection with content — 6 client-local records. Rejected because 6 records do not need a distribution format, a two-tier resolver or a version-pinned bundle; `VaultSyncManager` already reads them from markdown and has done for months. It would be distribution machinery built at 1/5 scale for the same absent reason. |
| **Build R3 and R4 as specified anyway** | Two-tier bundles and sync over an empty payload, on the bet that content arrives later. This is the error the whole track was created to correct, one layer up: R0 deleted a retrieval stack that returned answers over nothing, and this would build a *distribution* stack that ships nothing. Rejected on the same argument, in the same words. |
| **Delete `infrastructure/retrieval/` along with the track** | Superficially consistent — no track, no code. Rejected: the audit path would fall back to substring matching (a regression against a working component), the census baseline would lose the instrument that produced it, and the next agent asking *"why don't we do RAG here?"* would find a deleted directory and a plan, rather than a measurement. **Keep the evidence for a negative result, especially when the result is "stop".** |
| **Amend ADR-008 in place** | [[ADR-005 Local-Only Processing with Cloud Licensing]] was amended in place and says why it was allowed to be: *"This ADR is still `status: proposed`, so the amendment is made in place — there is no ratified decision record to preserve."* ADR-008 is `accepted`. Its reasoning — particularly the encryption/custody argument, which is about ADR-005 and outlives this track entirely — is preserved intact and pointed at from here. |

---

## Related

- [[ADR-008 The Second Brain — Retrieval-Only Local Knowledge]] — the decision this amends; its
  decisions 1, 4 and 5 survive as constraints
- [[Standards Knowledge — Staged Plan]] — R0/R1/R2 landed; R3 and R4 marked retired
- [[Retrieval Annotation Guideline]] — the four gates, and the reopening condition
- [[00 - AI Maturity Status]] — the negative result, the work log, and the re-homed `AutoDocEngine`
  defects
- [[ADR-007 Re-scoping the Maturity Ladder]] — the first retrieval metric this project retired, for
  the same class of reason
