---
tags: [gotcha, extraction, entity-model, evaluation, ground-truth, addressing, toolchain]
status: measured — constraint, not yet a fix
cache-version: n/a — no engine behaviour changed; this is a property of extraction as it stands
date: 2026-08-05
amended: 2026-08-11 — the cause is the export toolchain, not the reference/revision role
verified-against: 3615 entities across the 6 drawings of the first three eval pairs; re-confirmed 2026-08-11 on the M745221N01 pair
---

# Gotcha — Exploded Block Children Have No Handle

> [!IMPORTANT] The entity handle is this system's addressing scheme, and on reference
> drawings it is mostly absent. Anything designed around "every finding names a handle" —
> the eval corpus, the Stage 0d scorer, entity-grounded prompting, canvas hit-testing —
> has to be designed around this instead.

## The measurement

Exporting the first three evaluation pairs ([[00 - AI Maturity Status]], Stage 0b) put a
number on something that had never been counted:

| drawing | text entities carrying a DXF handle |
| :--- | ---: |
| M7452A0N01 reference | 2 / 249 — **0.8%** |
| M7452A0N01 revision | 234 / 254 — 92.1% |
| M7452A1N01 reference | 2 / 249 — **0.8%** |
| M7452A1N01 revision | 234 / 254 — 92.1% |
| M745200N01 reference | 25 / 192 — **13.0%** |
| M745200N01 revision | 247 / 295 — 83.7% |

And the cause, which is unusually clean:

> Across all **3615** entities in these six drawings, `handle` and `parent_handle` are
> **perfectly mutually exclusive**. Zero exceptions. An entity has one or the other, never
> both, never neither.

## Why

`DXFParser.process_entity` (`infrastructure/cad/dxf_parser.py:200-218`) explodes every
`INSERT` through `ezdxf`'s `virtual_entities()`:

```python
insert_handle = getattr(entity.dxf, "handle", None)
for sub_ent in entity.virtual_entities():
    process_entity(sub_ent, layout_name, depth + 1, is_dimension, insert_handle)
```

`virtual_entities()` yields **unbound copies**. They are not in the document's entity
database, so they have no handle to report — `EntityMapper` records `None`. The child is
then tagged with the owning INSERT's handle as `parent_handle`, which is where the perfect
mutual exclusion comes from: top-level entities get a handle and no parent; block children
get a parent and no handle.

This is not a bug in the parser. Exploding blocks is what makes their content individually
addressable at all, and the comment at `:201` says so. The gotcha is that the *addressing*
half of that sentence quietly does not hold.

## Why it bites the reference side hardest

> [!WARNING] Amended 2026-08-11 — this section had the right correlation and the wrong variable.
> It reads the split as a property of **re-tracing**: old sheet keeps its content in blocks,
> re-traced sheet is flat. The observation is correct; the cause is one level down.
>
> **It is the export toolchain.** The user supplied the provenance the vault never recorded:
> the reference is exported **DWG → DXF**, the revision **iCAD SX `.icd` → DXF**. DWG nests
> text inside blocks; the iCAD exporter writes MTEXT straight into the paper layout. Measured
> on the M745221N01 pair, which is not one of the six above:
>
> | file | route | own handle | parent_handle |
> | :--- | :--- | ---: | ---: |
> | `M745221N01_reference` | DWG → DXF | 6 / 144 — **4.2%** | 138 |
> | `M745221N01_FSRS2_kmti` | iCAD `.icd` → DXF | 231 / 250 — **92.4%** | 19 |
>
> Same split, same perfect mutual exclusion, a different drawing pair — and the raw DXF shows
> the mechanism directly: **6** top-level MTEXT on the DWG side against **231** on the iCAD side.
>
> **So handle coverage tracks the exporter, not the reference/revision role.** A reference
> exported from iCAD would arrive at ~92%; a revision exported from DWG at ~4%. Anything
> designed around *"reference drawings have no handles"* is keyed on the wrong variable and will
> be wrong the first time a pair breaks the current convention. Key on the measurement, never on
> the side.
>
> `NoLayerName_001` is likewise not a re-tracing artifact — it is the iCAD exporter inventing
> layer names because `.icd` has no DXF-compatible layer table. See
> [[Gotcha - The Two Sides of a Comparison Come From Different Exporters]].

The consequence below is unchanged and is what still matters day to day:

Handle coverage is ~90% on the revision side and ~1–4% on the reference side — and **REMOVED
findings anchor on the reference side by definition.** The one status that can only be addressed
from the reference drawing is the one with almost no addresses available.

## What was done about it

Nothing to extraction. Adding synthetic handles to exploded children is a real option
(`f"{parent_handle}/{index}"` is deterministic given the same file and the same `ezdxf`),
but it changes `EXTRACTION_SCHEMA_VERSION`, invalidates every cached comparison, and needs
a decision about what a "handle" then means to the canvas and to the LLM prompt manifest.
That is a decision, not a cleanup.

Instead the **eval corpus accepts two address forms**
(`infrastructure/eval/corpus.py::ExpectedFinding`):

| form | example | availability |
| :--- | :--- | :--- |
| DXF handle | `REV-1B2A` | ~1–92%, depending on the sheet |
| payload address | `REF#412` — line 412 of `ref.entities.jsonl` | **100%** |

A payload address is not portable across a re-extraction. That is acceptable *here* and
nowhere else: the payload is pinned by sha256 in the committed manifest, so a re-extraction
changes bytes the loader refuses to accept. The corpus cannot drift underneath an index
without failing loudly — see [[Gotcha - Comparison Cache Invalidation]] for the same idea
applied to a cache.

`tools/eval_corpus.py worksheet` prints whichever form applies per entity, so an annotator
copies one column and never has to know which case they are in.

## Consequences to keep in mind

- **The Stage 0d scorer is "handle-first", but only where handles exist.** On these pairs
  that is a minority of the reference side. `PairLabels.handle_anchored_count` reports the
  fraction rather than letting it be assumed.
- **Entity-grounded AI comparison inherits this.** `entity_index.py`'s manifest asks the
  model to cite `[ID: REV-1B2A]`; entities with no handle cannot be cited at all, and on a
  reference sheet that is almost all of them. Worth measuring before Stage 4 leans on it.
- **`parent_handle` is not a substitute.** Every child of one INSERT shares it, so it
  identifies the block instance, not the entity.

## The transferable lesson

"Every entity has a handle" was true of the DXF *file* and false of what the parser
produces. A property of the input format survived into the mental model of the pipeline
without anyone re-checking it at the output. Counting took one query; the assumption had
stood since Phase 1.

## See also

- [[Gotcha - The Two Sides of a Comparison Come From Different Exporters]] — the root cause of
  the split above, and the other asymmetries that travel with it
- [[00 - AI Maturity Status]] — Stage 0b, where this surfaced
- [[Eval Corpus Annotation Guideline]] — the annotation rules this amends
- [[Gotcha - Zone Templates Vanish in Offline Eval]] — the other divergence the first
  offline run exposed
- [[Gotcha - Comparison Cache Invalidation]] — the sha256-pinning precedent
