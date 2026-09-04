---
title: Gotcha - Adding a Note Destroys the Notes Zone
type: gotcha
tags: [gotcha, zone-detection, notes, comparison, false-positive, detection-only]
status: resolved
date: 2026-08-12
---

# The change under test destroyed the zone that was supposed to catch it

Raised by the owner as a direction, not a bug report: *"zone box isn't a feature we could rely on
in the future. Our system must adopt and learn."*

`notes_section` scored **P 0.59 / R 1.00** on the detection-only path — 9 false positives against
perfect recall. Perfect recall means the box already catches every real change and only *adds*,
which is a specific signature with a specific cause.

## The measurement

On `M7452A0N01-rev-mut005`, both sides carry the **same four notes rows at identical
coordinates**:

```
REF  notes box = (38.0, 202.6,  60.0, 251.0)   -> all four rows INSIDE
REV  notes box = (65.0, 202.6, 254.0, 231.8)   -> all four rows OUTSIDE
```

Nothing moved on the sheet. Only the box moved, and the four rows reported `REMOVED` on a drawing
that plainly has them — 7 false positives from one pair.

The cause is the mutation itself. It adds the text **`追加注記`** ("additional note") at x=264,
**209 units** from the real notes cluster at x=55. That text contains `注記`, a legitimate entry in
`ZONE_ANCHORS["notes"]`, so the anchor pass now has two clusters:

```
REF  'notes' anchor hits: 3        REV  'notes' anchor hits: 4
  ( 55.0, 207.6) 'なきこと'          ( 55.0, 207.6) 'なきこと'
  ( 55.0, 217.2) '面取り'            ( 55.0, 217.2) '面取り'
  ( 55.0, 226.8) '面取り'            ( 55.0, 226.8) '面取り'
                                    (264.0, 213.0) '注記'      <-- the added note
```

**The detector cannot represent two clusters.** It grows one box, which spans x 65-254 and covers
**neither** — not the block at x=55, not the new note at x=264.

> **Adding a note destroys the notes zone.**

## Why this one could not be fixed the way the last one was

This is the same failure mode as [[Gotcha - Zone Detection Accuracy & Stability]]'s `仕上げ`
anchor, removed earlier the same day for matching `仕上げ記号` in the tolerance block and dragging
the notes box across the sheet. That anchor was **wrong** and deleting it fixed the box.

`注記` is the canonical Japanese word for "notes". It cannot be deleted. The approach is
**structurally fragile, not mis-tuned** — and the fragility is worst in exactly the case the system
is for, because a revision that adds a note is a revision worth checking.

The geometry offers no way out either. The ruled-border spike measured a best-IoU **ceiling** of
**0.08** for `notes` (0.06 for `iso`) against segments actually drawn on the sheet — chosen knowing
the answer, so it bounds *any* selection rule. These sheets contain no drawn box around the notes;
the "notes zone" is a rectangle we impose on floating text. See
[[Gotcha - Every Published Baseline Measures a Configuration Users Do Not Get]].

## The fix: classify per entity, not per box

`notes_classifier.py` decides whether each text **is** a note, from its own content and its
neighbours. A content predicate is side-independent by construction, so the two sides cannot
disagree however their boxes landed.

Two stages, because content alone is not enough:

1. **Seed** on content — instruction form (`〜こと`, `。`), `注記`/`注意`, a `注` prefix, the
   English word `note`/`notes`, heat-treatment specs (`施工`/`硬度`), and the existing
   `ZONE_ANCHORS["notes"]` vocabulary (reused, never forked — it carries two hard-won exclusions).
2. **Cohere** the item markers. Nothing about `１` says "note"; it is a note because it sits on the
   **same row** as an instruction, 12 units to its left.

### Three traps, each found by measurement

| trap | what happened |
| :--- | :--- |
| **The length gate ran first** | `追加注記` is 4 characters, under the 6-character seed floor — and it is the corpus's one ADDED-note label. The classifier missed the single finding it exists to catch. Strong markers now bypass the floor. |
| **The cohesion window spanned the seed set** | A note may legitimately sit far from the block. With a bounding window from x=55 to x=264, anything sharing a row *anywhere* was admitted — the view label `Ａ`, the chamfer callout `Ｃ１`. Cohesion is now measured against **one** seed, in both axes. |
| **`endswith` was asymmetric** | The CHANGED label mutates `指示なき角部は糸面取りのこと` to `…のこと2`. An exact `endswith` scored that as not-a-note **on the revision side only** — reintroducing the very asymmetry the module exists to remove. Instruction endings are now matched within 3 trailing characters. |

## The precedence mistake, which is the transferable part

Content cannot separate a note from the tolerance block's `必要な場合は、粗さ区分を記入のこと` —
an instruction in identical form. That needs a zone veto, and the veto needs an order, so
[[zone_ownership]] ranks zones by **whether they have a drawn border**.

`title_upper_left` was ranked **above** `notes` on its 0.62 border ceiling. That was wrong, and the
eval said so immediately: `notes_section` recall fell to **0.54**, because under detection the UL
box swallows the notes block whole — the census finds **31 texts** in that intersection at frac
**1.00** over **6 of 12** corpus sides.

> **The border ceiling measures how well a *hand-aligned* box sits on ruled lines. It says
> nothing about whether the *detected* box is right.**

`title_upper_left`'s box over-reaching **is** the defect the rest of that day was spent on. A zone
cannot both be the known-unreliable one and outrank a peer. It is now a peer of `notes` and `iso`,
with content breaking the tie — the UL table's values are short codes, note lines are sentences,
and no box is needed to tell them apart.

## The collision census

The owner named three colliding pairs. All three are real, and all are far worse without a
template — counting text entities inside each intersection over 12 corpus sides:

| zone pair | pinned | detected |
| :--- | ---: | ---: |
| `views` x `tolerance` | 72 | 1840 |
| `views` x `title` | 36 | 818 |
| `title` x `tolerance` | 570 | 622 |
| `views` x `bom` | 241 | 240 |
| `bom` x `tolerance` | 0 | 72 |
| `title_upper_left` x `tolerance` | 0 | 54 |
| **`title_upper_left` x `notes`** | **1** | **31** |
| **`bom` x `iso`** | **1** | **24** |

Two are structural: `iso`'s quadrant prior is `x > 0.30w` with **no y bound**, so it strictly
contains `bom`'s `x > 0.50w and y > 0.35h`; `notes`' is `y > 0.15h` with **no x bound**, so it
spans all of `title_upper_left`'s. Those pairs cannot be separated by the priors at all.

⚠ **One hypothesis was checked and refuted.** `notes` x `iso` had no arbitration rule in any of the
four exclusion lists, and the markings are concatenated with no de-duplication — so an entity in
that intersection would be diffed twice and emitted under two categories. It looked like a cause of
the 9 false positives. **It is not: the census finds that pair firing on zero corpus sides**,
pinned or detected. The hole is latent, and closing it moves no metric. Recorded because a
plausible cause that measurement kills is worth as much as one it confirms.

## Results

| | templated | detection only |
| :--- | :--- | :--- |
| F1 | 0.9231 -> **0.9231** | 0.7736 -> **0.8367** |
| precision | 0.9796 -> **0.9796** | 0.8039 -> **0.9535** |
| recall | 0.8727 -> **0.8727** | 0.7455 -> **0.7455** |
| false positives | 1 -> **1** | 10 -> **2** |
| `notes_section` | P 1.00 / R 1.00 (held) | **P 0.59 -> 0.93**, R 1.00 held |
| duplicates | 0 | 0 |

**Templated attribution fell 1.00 -> 0.83, and that number is not readable here.** All 8 findings
whose category moved were inspected: 7 are the classifier disagreeing with a label the **old box**
produced — `追加注記` and two instruction sentences were labelled `drawing_views`, and two `C1`
chamfer callouts were labelled `notes_section`. Mutation labels are exported from the engine's own
pool, so attribution is tautological while the zone map is shared and becomes meaningless the
moment scoping changes. See [[Gotcha - Mutation Labels Predate the Zone Template]]. P and R are the
readable metrics, and both are unchanged.

⚠ **One false positive remains** on `M7452A0N01-rev-mut011`: a `１` item marker reports `REMOVED`
when the sentence it cohered to is the thing the mutation deleted — **removing a note orphans its
item number**. Left alone deliberately. It is 1 of 43 predictions on one mutation pair, and tuning
cohesion against a single pair is how a classifier gets fitted to its corpus.

## Guarded by / cache

`tests/test_notes_entity_classifier.py` (21 tests) and `tests/test_zone_ownership.py` (14),
including a regression per trap above and `test_the_same_text_classifies_the_same_on_both_sides`,
which pins the property the whole module exists for. Cache **v46 -> v47**.

## Follow-up from the same report: a value excluded by a zone that never compared it

Retested by the owner on `M745227N01`, the upper-left table now pairs correctly — and one line
came out **`ADDED` with no `REMOVED` counterpart** on a sheet that plainly carries it on both
sides. Their read was exactly right: *"So the system just drop the data because it doesn't have a
pair? But basically have a pair."*

```
REF  '4 ロール：12 (2x6台)'   at (179.2, 767.5)  -> owner = title_upper_left
REF  '2 ロール： 4 (2x2台)'   at (179.2, 743.3)  -> owner = notes
REV  '４ロール：１２（２×６台）' at (118.4, 273.8)  -> owner = views
```

The reference's UL box bottom edge is at **y=763.0** and that line sits at **y=767.5** — **4.5
units inside**. Its sibling, 24 units lower, falls outside and paired correctly, which is why one
of the two lines was right and the other was not. `title_upper_left` is in
`VIEWS_EXCLUDED_ZONES`, so the box removed the reference's copy from the only pool that could
have matched it — while `ul_value_band_index` had already cut that row as not-a-values-row, so
the extractor never claimed it as a field either.

**Claimed by the zone for exclusion, unclaimed by it for comparison, compared by nobody.**

> **A zone may only take content out of the shared pool if it is going to compare it.**

`extract_title_ul_kv` now returns its claimed entity ids alongside its pairs, and `views`
subtracts those instead of the box — the same identity-not-hull treatment `notes` already had.
Everything the zone declined falls through to `views`, the drawing area, which is the right home
for content no specialised pass wanted. This is the owner's own proposed rule: *"if a data
doesn't have a pair in that zone, maybe give it to drawing views or notes."*

### And the defect that fix exposed

With both copies present, the two lines **cross-paired**: `4 ロール：12 (2x6台)` reported as
becoming `２ロール：　４（２×２台）`. Not a missing finding but a false one, and a worse one — it
reads as a 4-roll spec becoming a 2-roll spec.

`spatial_differ`'s pass-1 scored every plausible cross-text pair as `dist + 1000.0`, ordering them
by **proximity alone**. The block moved between revisions — normalized y 0.8285 / 0.8039 on the
reference against 0.8834 / 0.8581 on the revision, a shift of **0.055** against a row pitch of
**0.025** — so each line's nearest neighbour on the other side is its **sibling**. Each line is
near-identical to its own counterpart and merely similar to its sibling, so similarity separates
what distance cannot: `CROSS_TEXT_SIMILARITY_WEIGHT` (100.0, bounded far below the 1000 penalty so
a cross-text pair can never outrank an identical-text one).

⚠ **Neither fix moves either baseline** — both are byte-identical before and after. `M745227N01`
is one of the six pairs the runner **skips for having no labels**, so the corpus cannot see either
of them. That is the same blind spot recorded above under a different name, and it is the argument
for Stage 0b in one line: **the pair that produced two real defects in one afternoon is invisible
to every number this project publishes.**

## The transferable rules

> **A zone box that is grown from content moves when the content moves — including when the
> content that moved is the change you are trying to detect.**

> **Do not let a box you know to be unreliable veto a classification. Ranking a zone by how well
> its *hand-aligned* box fits the drawing says nothing about its *detected* box.**
