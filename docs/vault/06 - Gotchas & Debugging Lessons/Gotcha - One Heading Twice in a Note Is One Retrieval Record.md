---
title: Gotcha - One Heading Twice in a Note Is One Retrieval Record
type: gotcha
tags: [gotcha, retrieval, indexing, corpus, labelling, latent-defect]
status: active
date: 2026-08-17
cache-version: n/a (retrieval index; no comparison cache involvement)
related: [ADR-012 Indexing Human Judgement as Retrieval Collections, Retrieval Annotation Guideline, Gotcha - A Stale Index Kept Answering For a Deleted Standard]
---

# Gotcha — one heading twice in a note is one retrieval record

**Class:** latent defect, harmless until the day it isn't · **Found:** 2026-08-17, by counting ids
after adding the `vault` collection — *not* by any failure

---

## Symptom

None available. Nothing in the system pins a chunk id, so nothing could have gone wrong yet.

Found by asking a question the code never asks itself: *are the ids this produces actually
unique?* Over the vault's 990 chunks the answer was **978 distinct ids** — twelve chunks sharing
four.

## Cause

`index_builder.chunk_markdown_by_heading` derives a record id from the file and the heading:

```python
def _record_id(source: str, discriminator: str) -> str:
    digest = hashlib.sha256(f"{source}::{discriminator}".encode()).hexdigest()
    return digest[:16]
```

**A heading is not unique within a note.** The offenders were exactly the notes you would predict
once stated:

| note | heading | occurrences |
| :--- | :--- | ---: |
| `AI Maturity Ladder — Staged Plan` | `Exit criterion` | **6** |
| `AI Maturity Ladder — Staged Plan` | `Risks` | 4 |
| `Standards Knowledge — Staged Plan` | `Risk` | 4 |
| `Gotcha - A Blurry CAD Canvas and Its Four Causes` | `Lessons` | 2 |

A staged plan has one `Exit criterion` per stage. That is good writing, and it is precisely what
breaks a `(file, heading)` key.

Note *which* content this hit: the per-stage exit criteria are among the most queryable text in the
vault — *"what is Stage 0b's exit criterion?"* is a question someone would actually ask. The
collision landed on the best content, not the worst.

## Why it was invisible, and why it was about to stop being

Six records can share one id and everything still works: `VectorStore` ranks by row position in
the matrix, not by id, so all six are indexed, all six are searchable, and all six return
correctly. The id is only ever *read* when something addresses a chunk from outside.

Exactly one thing does that, and it does not exist yet: `RetrievalLabel.relevant_ids` names chunk
ids, and `LabelSet` scores a query by checking whether a returned hit's id is in that list. So at
Stage C — the labelling this whole corpus-widening exists to enable — an annotator marking "Stage
0b's exit criterion" as relevant would have written an id that also names five other sections. The
scorer would then credit a hit on *any* of the six. **A retrieval metric that scores a wrong answer
as correct**, in the one place this project has been most careful to avoid inventing numbers.

This is the same shape as [[Gotcha - A Stale Index Kept Answering For a Deleted Standard]] one
level down: there a count was a claim about the index rather than the corpus; here an **id** is a
claim about a chunk that four other chunks also satisfy.

## Fix

Suffix only *repeats*, counted over records actually emitted:

```python
seen_headings[key] += 1
occurrence = seen_headings[key]
discriminator = key if occurrence == 1 else f"{key}#{occurrence}"
```

**Only repeats**, deliberately. A note whose headings are unique keeps byte-identical ids, so
`domain_rules` — built by the same chunker and the one collection that might plausibly have been
labelled already — does not move at all. Pinned by
`test_a_note_with_unique_headings_keeps_its_original_ids`, which asserts the plain
`sha256("Note::Heading")[:16]` the function has always produced.

Counted at *append* time rather than at parse time, so the numbering is dense over what is indexed
rather than over what was parsed — a heading whose body is too short to clear `MIN_CHUNK_CHARS`
does not silently consume an occurrence number.

After: **990 chunks, 990 distinct ids, 0 collisions.**

## Lessons

- **Fix an addressing scheme before anything addresses it.** The cost today was one counter and a
  test. The cost after Stage C would have been re-labelling, plus a period during which the
  retrieval metric was quietly generous.
- **A uniqueness assumption deserves to be counted, not reasoned about.** `sha256(file + heading)`
  reads as obviously unique. It took `Counter(r.id for r in records)` — three lines — to find that
  it was not, on content that had been in the vault for weeks.
- **Ask what makes a value *load-bearing*, not just what it is.** The id was inert for months
  because nothing read it. The right question was not "is this correct" but "what will read this,
  and when" — and the answer was "the next stage of the work I am doing right now".
- The repo's own [[Gotcha - Our Own Punctuation Broke on the cp932 Console]] fired again while
  investigating this: the diagnostic script printing the colliding headings died on an em-dash in
  a note title, on the Windows cp932 console. Set `PYTHONIOENCODING=utf-8` for any script that
  prints vault content.
