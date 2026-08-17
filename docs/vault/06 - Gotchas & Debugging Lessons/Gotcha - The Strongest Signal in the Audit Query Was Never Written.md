---
title: Gotcha - The Strongest Signal in the Audit Query Was Never Written
type: gotcha
tags: [gotcha, retrieval, rag, audit, silent-degradation, dead-branch]
status: active
date: 2026-08-17
cache-version: n/a (standards-audit retrieval path; no comparison cache involvement)
related: [ADR-012 Indexing Human Judgement as Retrieval Collections, ADR-008 The Second Brain — Retrieval-Only Local Knowledge, Retrieval Annotation Guideline, Gotcha - A Count You Could Not Take Is Not Evidence]
---

# Gotcha — the strongest signal in the audit query was never written

**Class:** silent degradation, dead branch · **Found:** 2026-08-17, by harvesting the production
queries for Stage B and *reading them* — not by any failure

---

## Symptom

None, in the sense of an error. The standards-audit retrieval has run on every audit for months and
returned results the whole time.

The symptom only appears when you print what it actually searched with:

```
q001  M7452A0N01_reference.dxf line circle arc ellipse spline polyline dimension text
q002  M7452A0N01_FSRS2_kmti.dxf line circle arc ellipse spline polyline dimension text
q003  M7452A1N01_reference.dxf line circle arc ellipse spline polyline dimension text
...
```

Nineteen distinct queries across 44 drawings, and **the only token that differs between any two of
them is the file name.** Every query carries the same eight entity-type words.

## Cause

`AuditOrchestrator._retrieve_lessons_learned` builds its query from three sources, and its own
comment ranks them:

```python
# 1. Layer names are the strongest signal (e.g. "BORDER", "DIMENSION", "GEOMETRY")
layer_meta = drawing.metadata.get("layers", [])
```

**Nothing writes `DrawingDocument.metadata["layers"]`.** Measured against the live database: 44
drawings, **0** with a non-empty `layers` list — the key is absent entirely. The metadata a
drawing actually carries is:

```
acad_version, coordinate_space, extmax, extmin, ezdxf_version, handseed,
measurement, regions, render_bounds, safe_zones, transform_version, viewport_transform
```

`.get("layers", [])` returns the default, the `for` loop runs zero times, and the branch is inert.
There are three other `"layers"` keys in the backend and none of them is this one:
`context_builder.py:95` builds one into an *audit context* dict, and
`geometry_serializer.py:353` / `drawings.py:318` build one into a *rendering* payload. The name
matches; the owner does not.

So branch 1 contributes nothing. Branch 2 (`entity_counts` keys) is the same set of CAD primitives
on every mechanical drawing — `line`, `circle`, `arc`, `dimension`, `text` — so it is a constant.
Branch 3 (file-name fragments) is the only discriminating input. **The query is the file name plus
noise.**

## Why nothing caught it

- **It cannot fail.** A missing key yields an empty keyword list, which yields a shorter query,
  which retrieves *something*. There is no error, no empty result, no log line.
- **The one thing that would have caught it did not exist.** `recall@5` on this collection has
  never been computed — the corpus is 16 chunks against a 0.25 chance-floor gate, so the metric
  refuses to render a verdict ([[Retrieval Annotation Guideline]]). A query built from noise and a
  query built from layer names score identically when neither is scored.
- **The docstring made it worse rather than better.** It says "the strongest signal", present
  tense, with three plausible examples. Reading the code confirms the *intent*, and the intent was
  never in doubt. Only reading the **data** shows it never happens.

Same family as [[Gotcha - A Count You Could Not Take Is Not Evidence]] and
[[Gotcha - A Tested Endpoint That Nothing Ever Called]]: code that is correct about what it wants
and wrong about what it gets.

## Fix — repair (2), taken the same day

Two repairs were available:

1. **Populate `metadata["layers"]` at extraction time.** Requires an `EXTRACTION_SCHEMA_VERSION`
   bump, and every existing drawing reads stale until re-extracted.
2. **Read layer names from `ExtractedEntity.layer`**, which is populated, indexed, and already the
   source `context_builder.py:95` uses for its own layer list. No schema bump, no re-extraction —
   the data is already there, one collection over.

(2), via `queries.layer_names_for(drawing_id)`, which uses the existing `(drawing_id, layer)`
compound index rather than loading entities. **Layer names are now a parameter of
`build_drawing_keywords` rather than something read off the drawing**, so the source is explicit
at each call site and the function stays synchronous and testable.

The result, on the same drawings:

```
before  M745230A01_reference.dxf line circle arc ellipse spline polyline dimension text
after   M745230A01_reference.dxf clin defpoints info rahm2 rahm3 rahm5 title line circle ...
```

Reference and revision sides are now distinguishable by more than their file name — the reference
carries `paref` / `rahm*` / `waku` / `title`, the revision `nolayername` / `001`-`004` /
`viewports` / `draftline`.

⚠ **The stored production queries had to be replaced, not appended to.** A production query is a
*projection* of the current construction over the current drawings, so `queries harvest` now drops
every `production`-origin entry before re-harvesting and **refuses to drop a human origin** —
`checker` and `finding` queries cannot be regenerated by re-running a tool. Without that, the store
would hold 19 queries production can no longer issue, beside 19 it can, with nothing marking which.

### Two things this fix broke on the way in, both caught

- **It hoisted a database call out of a non-fatal guard.** The layer fetch initially sat *above*
  `_retrieve_lessons_learned`'s `try`, so a transient Mongo error would crash an entire audit — in
  a function whose own comment says *"if retrieval fails, the audit continues without lessons"*.
  `test_phase4_audit_pipeline` caught it. The fetch now sits inside the guard.
- **`QuerySet.add` derived ids from the list length**, so after `drop_origin` left a gap, a store
  holding `q002(checker)` would mint a second `q002` — two different questions at one address,
  which is the same collision class as
  [[Gotcha - One Heading Twice in a Note Is One Retrieval Record]], found the same day one layer
  over. `add` now scans for a free id.

### The regression guard is about the output, not the code

`test_layer_names_actually_reach_the_query` asserts that a layer name a caller supplies is
**present in the resulting query**, rather than that the function reads layers. The original defect
was invisible precisely because a missing key produces a *shorter query*, never an error — so a
test that checked the code path would have passed against the broken version too.

## Lessons

- **A comment ranking its inputs is a claim about data, and data claims expire.** "Layer names are
  the strongest signal" was checkable in one query against the database and had never been checked.
- **Print what your system actually sends.** This survived code review, a docstring rewrite during
  R1, and an ADR — and died the first time somebody looked at nineteen queries in a column.
- **An unmeasured path degrades silently and indefinitely.** The absent metric is not a separate
  problem from this bug; it is the reason this bug is old. Corpus-widening ([[ADR-012]]) is what
  makes the metric possible, and the metric is what would have caught this on day one.
- **`dict.get(key, default)` on a dict you do not own is an assumption.** It reads as defensive and
  behaves as a silent branch-off. Where the key is load-bearing, assert it or log its absence.
