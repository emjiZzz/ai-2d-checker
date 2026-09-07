---
title: Gotcha - A Marking Cannot Store an Entity Id
type: gotcha
tags: [gotcha, ground-truth, addressing, extraction, silent-failure, data-integrity]
status: active
date: 2026-08-18
cache-version: n/a (capture path only; no comparison cache involvement — the mutation invariant was measured byte-identical before and after)
related: [Gotcha - Exploded Block Children Have No Handle, Gotcha - A Missing Y Flip Is Invisible Near the Centreline, Gotcha - The Worksheet Cannot Place a Dimension, ADR-007 Re-scoping the Maturity Ladder]
---

# Gotcha — a ground-truth marking cannot store an entity id

**Class:** data that decays silently · **Found:** 2026-08-18, before any data was collected —
which is the only reason it is cheap

---

## The failure that was avoided

A manual-check marking says *"an engineer looked at **this entity** and judged it ADDED"*. The
obvious way to record "this entity" is its `ExtractedEntity` id, and that is wrong in a way
that produces **no error, no warning, and no visible symptom** until the dataset is used.

`ExtractionPipeline.run` **deletes a drawing's entities and re-inserts them**
(`extraction_pipeline.py`, *"Re-extraction: cleared N existing entities"*). Every row gets a
fresh `ObjectId`. A marking keyed on one still reads perfectly afterwards — the id is a
well-formed string, the document validates, the UI renders it — it simply no longer points at
anything.

**This is routine, not hypothetical.** `EXTRACTION_SCHEMA_VERSION` is at **6**: six times a fix
has already required re-parsing drawings, and `POST /drawings/{id}/reextract` exists precisely
because it keeps happening. Any marking made before any of those six would have been orphaned.

## Why the DXF handle does not close the gap on its own

A `handle` comes from the source file, so it survives re-extraction. It is also **absent for
anything exploded out of a block**, and `handle` / `parent_handle` are perfectly mutually
exclusive — measured over 3615 entities in the first six exported drawings
([[Gotcha - Exploded Block Children Have No Handle]]).

| sheet | text-entity handle coverage |
| :--- | ---: |
| re-traced revision | 92% |
| **reference** | **0.8–13%** |

The reference side is where a REMOVED must anchor. Handle-only addressing would have made most
removals unrecordable — the half of the corpus that is hardest to capture and most valuable.

## The fix: a composite address, resolved in tiers

`GroundTruthMarking` stores an `EntityAddress` carrying every key that might survive, and
`infrastructure/ground_truth/address_resolver.py` re-binds it on demand:

1. **`handle`** — from the DXF, identical across any number of re-extractions.
2. **`parent_handle` + type + layer + text** — narrows a block-exploded child to one INSTANCE.
3. **type + layer + normalised text** — only when unambiguous.
4. **nearest coordinate**, within `COORDINATE_TOLERANCE = 1.0` drawing units.

Plus `source_file_hash` (the source DXF's hash — stable across re-extraction, so it proves the
drawing is still the same drawing when every entity id has changed) and
`extraction_schema_version`.

⚠ **Every tier returns `None` rather than a plausible wrong answer**, and a stored handle that
is *absent* from the drawing stops there rather than falling through to text matching. That
case means the entity was genuinely removed — which is what a REMOVED marking *means* — and
searching on would rebind the marking to a different entity that happens to share the string.

**An unresolved marking is a countable gap. A mis-resolved one attributes a human's judgement to
an entity they never looked at, and nothing downstream can detect it.** That asymmetry is the
whole design.

## The coordinate is a `CadPoint`, never a bare pair

Stamped server-side by `infrastructure/cad/coordinate_stamp.py`, the same treatment
`AnnotationDocument` gets. A bare `[x, y]` has no record of the render bounds it was authored
against, so a re-render silently moves it; `has_drifted` makes that detectable instead. Verified
against a real drawing: `space: model`, `bounds: [-52.5, -37.125, 1102.5, 779.625]`,
`transform_version: 1`, `source_file_hash` populated.

## The lesson

**When a record outlives the thing it points at, the pointer must be reconstructible, not
stored.** The tell is that the failure mode is *silence*: nothing raises, nothing logs, and the
data looks correct right up until someone tries to use it. `tests/test_ground_truth_addressing.py`
pins the round trip — stamp → re-extract → re-resolve — for both a handle-bearing entity and a
block-exploded one with none, because that test failing on day one is recoverable and the same
discovery in month six is not.
