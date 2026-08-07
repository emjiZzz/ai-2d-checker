---
tags: [gotcha, evaluation, zones, zone-template, reproducibility, measurement]
status: FIXED 2026-08-06 — the corpus now owns its zone boxes
cache-version: n/a — the divergence is between two run modes, not between two cache versions
date: 2026-08-05
verified-against: 36 pairs re-scored with templates applied; baseline-v42.json
---

# Gotcha — Zone Templates Vanish in Offline Eval

> [!WARNING] A baseline measured offline is **not** a baseline of what users see, unless
> this is dealt with. The offline run silently uses different zone boxes.

> [!TIP] Resolved 2026-08-06 — and the size of the effect is the headline.
> Option 1 below was taken. Applying this machine's seven hand-aligned zones to the corpus
> moved **precision 0.78 → 1.00, recall 0.65 → 0.78, F1 0.71 → 0.88**. Every one of the ten
> false positives in the v38 baseline was an artifact of the measurement, not a defect in the
> engine: `notes_section` went from the weakest category (F1 0.50) to **1.00**. See "How it
> was fixed" at the bottom — and [[Gotcha - Mutation Labels Predate the Zone Template]] for
> the one number that went the other way.

## What happened

The first offline run of `generate_deterministic_candidates` over an exported corpus pair
([[00 - AI Maturity Status]], Stage 0b) produced 50 candidates in 0.25 s with no network
call — the eval seam works. Buried in the log:

```
[WARNING] [zone_template] Template lookup failed for 'aspect-1.414': signature
[WARNING] [zone_template] Template lookup failed for 'aspect-1.384': signature
```

There **is** a template for `aspect-1.414` in this machine's database: the global default,
with all seven zones hand-aligned (`views`, `notes`, `bom`, `title`, `iso`, `tolerance`,
`title_upper_left`). In the app those seven boxes are applied. In the offline run, none of
them were.

## Why

`extract_dynamic_regions_async` (`bom/table_extractor.py:111-124`) applies hand-aligned
zone templates on top of detection:

```python
try:
    overrides = await resolve_zone_overrides(render_bounds, signature=signature)
except Exception as err:
    logging.getLogger(__name__).error(
        f"Zone template could not be applied, falling back to detection: {err}", exc_info=True
    )
    return result
```

`resolve_zone_overrides` queries `ZoneTemplateDocument`, a Beanie model. An offline run has
no Beanie session, so touching `ZoneTemplateDocument.signature` raises, and the handler does
exactly what it was designed to do: degrade to plain detection and carry on.

That fallback is **correct for the app** — a template lookup problem must not fail an audit.
It is **wrong for a measurement**, where "carried on with different zone boxes" is precisely
the thing that must never pass silently.

## Why it matters more than it looks

Zones are not decoration. They decide:

- what `drawing_views` even contains — it is now scoped strictly to the views box
  ([[Gotcha - drawing_views Was the Residual, Not the Views Box]])
- what is excluded from comparison entirely — `tolerance` and the shim table are safe zones
  ([[Gotcha - Optional Zones and the Shim Table]])
- which findings land in which category, which is scored independently of detection

So the offline/online divergence does not shift a number slightly. It moves findings
between categories and drops some out of scope altogether.

## What was done about it

Made **visible**, not fixed. Every exported pair records `zone_signature` per side — a pure
function of `render_bounds`, so no database is needed to compute it — and
`tools/eval_corpus.py verify` reports the risk:

```
[ok] M745200N01 [human, unlabelled]
       [warn] sheet 'aspect-1.384' has a pinned zone template that an offline run cannot
              resolve - its zone boxes will differ from the app's.
```

`CorpusPair.zone_template_risk()` is the programmatic form.

Note the CLI distinguishes "no template" from "could not check". An unreachable database
returns *unknown*, and the warning still fires. Treating an unreachable database as an
absence is how this class of divergence stays invisible in the first place.

## What was decided — Stage 0e

The two options were:

1. **Thread resolved overrides in.** Add a parameter to `extract_dynamic_regions_async` so
   the corpus can supply the boxes it recorded at export time. Zone fractions are stored
   relative to `render_bounds` and `fractions_to_absolute_bbox` is pure, so the resolution
   can happen once, at export, with a database present.
2. **Declare templates out of scope and pin it.** Assert no template resolves, and accept
   that the eval measures detection-only behaviour — stating plainly that the number is not
   what users see.

**Option 1, taken 2026-08-06.**

## How it was fixed

`extract_dynamic_regions_async` gained a `zone_template` parameter with **three** states,
and the three-way distinction is load-bearing:

| Value | Meaning |
| :--- | :--- |
| `None` | Resolve from Mongo. The app's path, unchanged. |
| `{}` | Captured, and this sheet has no pinned zones. **Not** a fall-through. |
| `{...}` | Apply exactly these, with no database access and no degradation. |

Collapsing `{}` into `None` — writing `if zone_template:` instead of `is not None` —
reintroduces the divergence for precisely the pairs a capture proved were safe. That bug is
**invisible to a result-only assertion**, because the degradation handler swallows the
failure and returns detection either way; the regression test asserts on whether the
database was *reached*, and was verified to fail against the truthy check.

The seam takes **fractions, not resolved boxes**, deliberately. Handing the engine
pre-resolved boxes would bypass `fractions_to_absolute_bbox` — the one conversion here whose
failure mode is a plausible-looking vertically mirrored zone — and the eval would go blind
to a regression in it.

Captured by `tools/eval_corpus.py capture-zones`, which mirrors `resolve_zone_overrides`'
lookup order exactly (signature-specific, then global default); a capture that resolved
differently from the app would substitute one divergence for another. The fractions live in
the **committed manifest** rather than in a payload file: they are layout geometry, not
customer drawing text, so they are diffable and reviewable, and being in the manifest means
they cannot drift from the digests recorded beside them.

Stored **once per sheet signature**, in a top-level `zone_templates` map — not per side. The
first implementation wrote them per side and grew the manifest by **3,330 lines**: the same
seven-zone block, 74 times, because every pair in this corpus is one sheet layout. A zone
template is a property of the layout, so the signature is its natural key, and the manifest
the staged plan requires stay *"tiny, reviewable, diffable"* grew by 47 lines instead.

That also removes the need for a second "captured?" flag: **presence in the map is the
capture state.** A signature that is absent was never asked; one that maps to `{}` was asked
and the answer was none. Two fields would eventually disagree; one cannot.

Pinned by `tests/test_offline_zone_templates.py` (6 tests).

### What it measured

Over 36 pairs, all 74 sides carrying the same seven hand-aligned zones:

| | v38 (no templates) | v42 (templates applied) |
| :--- | :--- | :--- |
| precision | 0.78 (36/46) | **1.00 (43/43)** |
| recall | 0.65 (36/55) | **0.78 (43/55)** |
| F1 | 0.71 | **0.88** |
| macro F1 | 0.75 | 0.86 |
| `notes_section` F1 | 0.50 | **1.00** |
| category attribution | 0.81 (29/36) | **0.74 (32/43)** ⚠ |

**Ten false positives disappeared, and they were the measurement's, not the engine's.** The
weakest category in the entire project became perfect. Zero false positives across the 11
zero-finding probes, unchanged.

**Attribution fell, and that is a different finding entirely** — see
[[Gotcha - Mutation Labels Predate the Zone Template]]. Do not read it as a regression.

## The transferable lesson

A `try/except` that is right for production is often wrong for measurement, and the same
line of code serves both. When a pipeline gains an offline mode, audit its graceful
degradations first: each one is a place where the two modes quietly disagree.

Related: the same run showed `generate_deterministic_candidates` is **not** network-free
either — it calls Gemini for title-block OCR on a cache miss (`orchestrator.py:464-467`).
That one is already guarded: `CorpusPair.missing_ocr_cache()` refuses to call a pair
offline-ready without both cache files present.

## See also

- [[Gotcha - Global Default Zone Template & the Aspect Caveat]] — why `aspect-1.414`
  collides across A-series sheets, which makes the default template broad
- [[Gotcha - Zone Detection Accuracy & Stability]] — what detection does without a template
- [[Gotcha - Exploded Block Children Have No Handle]] — the other divergence Stage 0b found
- [[00 - AI Maturity Status]] — the ledger, and Stage 0e where this is resolved
