---
title: ADR-010 Grounded LLM Summarization of Comparison Results
type: adr
tags: [adr, architecture, llm, generation, summarization, grounding, ai-architecture, privacy]
status: accepted
date: 2026-08-10
supersedes: none
amends: ADR-008 The Second Brain — Retrieval-Only Local Knowledge (decision 1)
related: [ADR-002 Decoupled Zone Bounding Box Endpoint, ADR-005 Local-Only Processing with Cloud Licensing, ADR-006 Removing the Three AI Comparison Methods, ADR-008 The Second Brain — Retrieval-Only Local Knowledge, ADR-009 Retiring the Standards Knowledge Track]
---

# ADR-010 — The LLM summarizes findings; it never decides them

**Status:** accepted · **Date:** 2026-08-10 · **Amends:** [[ADR-008 The Second Brain — Retrieval-Only Local Knowledge]] decision 1

---

## Context

The product shape, as stated by the owner on 2026-08-10:

```
ingest ref + rev  →  compare accurately  →  LLM summarizes the result  →  the vault learns from it
                          ✅ exists            ❌ this ADR                  ⚠️ half-wired
```

Step 3 does not exist, and **two ADRs currently forbid it**:

- [[ADR-006 Removing the Three AI Comparison Methods]] deleted every LLM path on the comparison
  engine — ~2,100 lines — and made `comparison_method` a single literal.
- [[ADR-008 The Second Brain — Retrieval-Only Local Knowledge]] decision 1 is titled
  *"Retrieval-only — RAG without the G"*: **"No LLM in the loop… it never generates prose."**

### Why this is not a reversal of ADR-006

ADR-006's argument was never *"LLMs are bad"*. It was that an LLM must not **decide what changed**:
the three deleted methods each had a model generating findings, and the engine had no way to tell a
hallucinated dimension change from a real one. That argument stands completely and is not reopened.

**This ADR puts an LLM strictly downstream of a complete deterministic finding list.** It composes
prose about findings that already exist; it never detects one. The distinction is the entire ADR,
and it is enforced mechanically rather than by prompt discipline — see decision 3.

### What exists today

`orchestrator.py:1254-1276` already emits a `difference_summary` per category. It is a count:

> *"Found 3 changed / 12 matched dimensions and annotations."*

That is accurate, cheap and offline, and it will keep working. What it cannot express is which
changes **relate to each other** — that a plate thickness changed and the BOM weight did not follow
it, that four dimension edits are one revision to one feature. A checker reconstructs that by
reading 27 rows. That reconstruction is the thing being automated here, and nothing else.

---

## Decision

Add a **grounded summarization** stage, downstream of comparison, behind a flag, off by default.

### 1. The structured findings are the product of record; the summary is derived and disposable

The checklist is what an audit is signed off against. The summary is regenerable from the findings
at any time, is never hand-edited, and is never persisted as the authoritative result. If the two
ever disagree, **the findings are right by definition.**

### 2. The grounding contract — what the model is given, and what it may do

| | Rule |
| :--- | :--- |
| **Input** | The structured finding list **only**. Ids, categories, statuses, reference/revision values, coordinates. |
| **Not input** | Drawing images, raw entity dumps, retrieved standards prose, prior audits. |
| **Every claim** | Cites the finding ids it rests on. |
| **Counts** | Supplied in the prompt as facts. The model never counts. |
| **Prohibited** | Adding a finding, removing a finding, or restating a status. |

No images, deliberately. The finding list is already complete, so an image adds nothing the model
needs and everything it could invent from — it would reintroduce exactly the hallucination surface
ADR-006 removed, through a side door.

### 3. Verification is deterministic, runs before display, and can withhold the summary

The load-bearing decision. A post-check runs on every generated summary:

1. Every cited finding id **exists** in the list the model was given.
2. Every stated count **equals** the real count.
3. **Every non-`MATCHED` finding is either mentioned or falls in an explicitly-summarised group** —
   the recall guard.

Any check fails → **the summary is withheld** and the deterministic `difference_summary` renders in
its place, with a visible note saying the generated summary failed verification. It is never
silently truncated, never partially shown, and never repaired by a retry that hides the first
answer.

Check 3 is why this ADR exists in this shape. **In an inspection tool a dropped finding is the worst
possible failure, and a fluent summary is the last place a human will look for one.**
[[ADR-008 The Second Brain — Retrieval-Only Local Knowledge]] named this hazard for retrieval —
*"surfacing near-miss rules as authoritative is a recall attack"* — and it arrives the same way
through generation. The mitigation there was "a human reads the citation". Here it is mechanical,
because prose does not carry a citation a human will check.

### 4. The summary is optional, and its absence is normal operation

No API key, no network, rate-limited, verification failed, feature off: **the product works.** The
checklist is complete without it. This mirrors R1's `SearchOutcome`/`IndexStatus` posture, where
"could not answer" is a **different value** from "nothing to report" rather than an empty list that
looks like success.

### 5. Fixed-field schema, on its own endpoint, never nested into `PhysicalComparisonResponse`

`PhysicalComparisonResponse` is passed directly as Gemini's `response_schema`. A bare `dict`
anywhere under it emits open-ended `additionalProperties` and Gemini rejects **every** request with
`400 INVALID_ARGUMENT` — `CLAUDE.md` constraint 1,
[[ADR-002 Decoupled Zone Bounding Box Endpoint]], guarded by
`tests/test_zone_overlay_endpoint.py::test_llm_response_schema_has_no_open_ended_objects`.

So the summary gets **its own endpoint and its own fixed-field schema**, decoupled for precisely the
reason ADR-002 decoupled the zone bbox endpoint. Citations are a `list[str]` of finding ids, not a
map. Nothing about this feature touches the comparison schema.

### 6. Cached separately from the comparison, keyed by the finding-list digest

Not in `storage/cache/` under `COMPARISON_CACHE_VERSION`. Coupling them would mean a prompt
reword invalidates real comparisons — expensive and wrong — and constraint 2's rule ("bump when
spatial matching or zone extraction changes") would start carrying a meaning it was not written for.
A summary is a pure function of the finding list, so the finding-list digest is its correct key.

---

## The egress question, and an existing hole this ADR must not paper over

[[ADR-005 Local-Only Processing with Cloud Licensing]] promises that drawing data stays on the
customer's machine, and argues the claim is **commercial**, not cosmetic: for Japanese manufacturing
clients, uploading drawings to a vendor cloud is a procurement blocker.

**A summary request sends finding text, and finding text is verbatim drawing text.** Part numbers,
material specs, dimensions.

Stated plainly, because it changes the honest reading of ADR-005: **this is not the first egress on
the deterministic path.** `execute_title_block_ocr` (`orchestrator.py:553`) already sends **image
crops of the customer's title block** to Gemini on a cache miss, today, with no flag. That is a
larger disclosure than a finding list, and it predates this ADR.

Decision: **the summary is opt-in, off by default, per room.** A customer who has not enabled it
sends nothing new. This is the conservative default and it is reversible; making it default-on later
costs nothing, while making a default-on feature opt-in after a security review costs a customer.

**ADR-005 needs a second amendment** covering both this and the pre-existing OCR egress. Its first
amendment narrowed the claim for knowledge sync — a feature now retired by
[[ADR-009 Retiring the Standards Knowledge Track]] — so the current text narrows the claim for the
one thing that never shipped while staying silent about the one that did. That is recorded here as
an obligation, not silently inherited.

---

## Alternatives rejected

| Alternative | Why not |
| :--- | :--- |
| **Improve the deterministic template summary instead** | The strongest alternative and it is not dismissed: it is offline, free, deterministic, has no egress and cannot hallucinate. It fails only at the one thing being asked for — relating findings to each other — and doing that in a template means encoding domain judgment as hand-written rules, which is the rules engine already deferred. **This ADR does not claim the LLM version is better: nothing measures it.** That is why it ships behind a flag, off by default, with the template as the always-present fallback rather than as a legacy path to remove. |
| **Let the LLM generate findings (revert ADR-006)** | Unchanged and still rejected. The engine could not distinguish a hallucinated change from a real one, which is why ~2,100 lines went. Nothing in the product vision requires it — the vision says *"compare accurately, **then** summarize"*, and that ordering is the whole safety argument. |
| **Send the drawing images alongside the findings** | Richer context, and it breaks the grounding contract: with an image the model can describe something not in the finding list, and check 3 cannot distinguish that from a real omission by the differ. It also enlarges egress from text to images. |
| **A local model, so nothing leaves the machine** | Preserves ADR-005 outright, and there is no infrastructure for it: the sidecar already rejected `sentence-transformers` at ~2.5 GB for *embeddings*: a generation model is worse. Revisit only if egress actually blocks a sale, which is a commercial signal rather than an engineering one. |
| **Persist the summary as part of the audit record** | Makes it authoritative by accident. An audit signed off against generated prose is an audit whose evidence is unverifiable after the fact. Findings persist; the summary regenerates. |
| **Retry silently on verification failure until a summary passes** | Turns the guard into a filter for *plausible-looking* output and hides the failure rate. If generation cannot produce a verifiable summary for a given audit, that is information, and it shows. |

---

## Consequences

**ADR-008 decision 1 is narrowed, not repealed.** *"No LLM in the loop"* becomes: **no LLM in the
retrieval loop, and no LLM deciding findings; generation is permitted strictly downstream of a
complete deterministic finding list, behind a verification gate.** The reasoning that made
retrieval-only right for *clause retrieval* — a checker wants cited clauses, not a paragraph they
must re-verify — is untouched, because this summarises the system's own structured output rather
than a retrieved document.

**ADR-006 is not reopened**, and this ADR should not be cited as precedent for doing so. If a future
change puts a model back in the *detection* path, that needs its own ADR arguing against ADR-006 on
its merits.

**Quality is unmeasured, and this ADR does not invent a metric.** There is no summary-quality score
and no corpus to build one from. What *is* mechanically verified is the grounding contract — ids
resolve, counts match, nothing non-`MATCHED` goes unmentioned. **Do not read "verification passes"
as "the summary is good."** It means the summary is not lying about the finding list. Recorded per
the ledger's rule that an unmeasured effect is stated, never omitted.

**A new failure mode enters the product: the summary becoming the thing people read** instead of the
checklist. It renders below the checklist rather than above it, and always states the total finding
count, so a reader who stops at the summary still knows how many items they skipped.

**The comparison engine is untouched.** No cache bump — nothing on the deterministic path changes,
v43 stands. The eval corpus must remain **P 0.98 / R 0.87 / F1 0.92** against `baseline-v43.json`;
movement means this leaked somewhere it should not have.

---

## Built 2026-08-10 — two deviations, recorded rather than absorbed

The implementation landed the same day (`infrastructure/audit/summary/`, 20 tests). Two things
differ from the text above, and both are stated here because a plan that quietly reshapes itself
during implementation is how a decision record becomes fiction.

**1. Check 2 ("every stated count equals the real count") is enforced on a structured echo, not by
parsing prose.** `GroundedSummary` carries `total_findings_stated`, which the model is told to echo
and the verifier compares against `len(findings)`. It does **not** scan the prose for digits.

The reason is domain-specific and decides it: this corpus's finding text is *full* of numbers that
are not counts — `板厚 12 -> 14`, `2-7キリ`, `8.65`. A prose scan would withhold correct summaries
on dimension values, and **a false withholding costs the user the feature**, which is a real cost
against a check that was already the weakest of the three. So: this catches a model that lost track
of its input; it does not catch a wrong number written mid-sentence. **Check 3 (coverage) is the one
carrying the weight**, and it is implemented exactly as specified — the union of all cited ids must
cover every finding supplied. Verified non-vacuous: disabling that single check fails four tests,
including the whole-pipeline one.

**2. The opt-in is global, not per room.** `settings.ENABLE_LLM_SUMMARY`, default off. The
**default-off property is honoured** — which is the safety-relevant half, since it is what stops a
customer who has not opted in from sending anything new — but a workspace cannot yet enable the
summary for one room and not another. Per-room granularity is unbuilt, not rejected.

Also worth recording because it is the sharpest line in the implementation: **verification runs
before the cache write**, so a summary that failed the gate can never be served from cache later.
Cached summaries are also **re-verified on read** rather than trusted, so tightening the rules takes
effect on existing entries instead of grandfathering output today's gate would reject.

---

## Deliberately not decided

Recorded so they do not become phantoms, per the rule this vault learned the hard way from
*"the four V2 gaps"*:

- **Language.** Japanese, English, or both. The domain is Japanese CAD; the checklist today mixes
  both. Needs a user answer, not an engineering guess.
- **Audience and length.** A checker glancing at a workstation wants three lines; a PDF report
  reader may want a paragraph per category. These imply different prompts and different schemas.
- **Whether the summary is regenerated on every view or once per finding-list digest.** A cost
  question, answerable once there is usage.

---

## Related

- [[ADR-006 Removing the Three AI Comparison Methods]] — the LLM-must-not-detect argument this ADR
  preserves
- [[ADR-008 The Second Brain — Retrieval-Only Local Knowledge]] — decision 1, narrowed here
- [[ADR-002 Decoupled Zone Bounding Box Endpoint]] — why the summary gets its own schema
- [[ADR-005 Local-Only Processing with Cloud Licensing]] — owes a second egress amendment
- [[00 - AI Maturity Status]] — the work log, and the unmeasured-quality entry
