---
tags: [gotcha, evaluation, zones, zone-template, reproducibility, measurement]
status: measured — visible, not yet fixed
cache-version: n/a — the divergence is between two run modes, not between two cache versions
date: 2026-08-05
verified-against: the first offline run of generate_deterministic_candidates, 3 eval pairs
---

# Gotcha — Zone Templates Vanish in Offline Eval

> [!WARNING] A baseline measured offline is **not** a baseline of what users see, unless
> this is dealt with. The offline run silently uses different zone boxes.

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

## What still has to be decided — Stage 0e

The runner needs one of:

1. **Thread resolved overrides in.** Add a parameter to `extract_dynamic_regions_async` so
   the corpus can supply the boxes it recorded at export time. Zone fractions are stored
   relative to `render_bounds` and `fractions_to_absolute_bbox` is pure, so the resolution
   can happen once, at export, with a database present.
2. **Declare templates out of scope and pin it.** Assert no template resolves, and accept
   that the eval measures detection-only behaviour — stating plainly that the number is not
   what users see.

Option 1 is better and is the reason `zone_signature` is already in the manifest. Either
way it must be **chosen and recorded**, because the failure mode of not choosing is a
number everyone trusts and nobody can reproduce.

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
