---
title: Gotcha - A Privacy Claim Rested on One Flag and Four Paths Ignored It
type: gotcha
tags: [gotcha, privacy, egress, gemini, llm, security, audit, adr-005, adr-010]
date: 2026-08-11
related: [ADR-005 Local-Only Processing with Cloud Licensing, ADR-010 Grounded LLM Summarization of Comparison Results, ADR-009 Retiring the Standards Knowledge Track, 00 - AI Maturity Status]
---

# A privacy claim rested on one flag, and four paths went around it

An audit package submitted for CTO sign-off on 2026-08-11 certified:

> *"Zero Default Cloud Data Egress — raw CAD vectors and drawing entities remain strictly on local
> storage."*

The evidence offered was a single line: `ENABLE_LLM_SUMMARY` defaults to `False` in `config.py`.

That flag is real, it defaults off, and it does gate the ADR-010 summary path
(`audit/summary/service.py:96`). The inference drawn from it was still wrong, because **three other
subsystems call Gemini and none of them consult it.**

## The four paths and what actually gates them

| Path | Sends | Fires on | Gate |
| :--- | :--- | :--- | :--- |
| `extraction_pipeline.py:232-237` → `summarization_pipeline.py:53-66` | entity context **+ a PNG of the drawing** | **every upload** | API key present |
| `orchestrator.py:552-555` (`execute_title_block_ocr`) | title-block **image crop** | every comparison, on OCR cache miss | API key present |
| `ai_engine.py:81-82, 156-160` | CAD text + visual passes | standards audit run | API key present |
| `streaming_engine.py:65-67, 84-90` | question + injected `=== DRAWING CONTEXT ===` | user sends a copilot message | API key present |

The first is the one nobody had written down, and it is the largest: it is automatic, it fires on
the most ordinary action in the product, and a rendered PNG is the biggest single disclosure this
system can make.

## The actual lesson: a settings default is not a system property

The reviewer read one flag and concluded a property of the whole system. The generalisable form:

> **A default answers "is this feature on?". It never answers "does data leave?"** Only an
> enumeration of the call sites answers that.

The check that would have worked takes one command:

```bash
grep -rnE "genai\.Client|generate_content|execute_gemini|openai" services/backend --include=*.py
```

Then, for each hit, read what gates it. Four of them gate on `if not api_key: return` — which is an
*availability* check wearing the costume of a *consent* check. They look identical at the call site
and mean opposite things.

## Why this survived in a vault that already knew

Both contradicting facts were already recorded here:

- [[ADR-010 Grounded LLM Summarization of Comparison Results]] states plainly that
  `execute_title_block_ocr` *"already sends image crops of the customer's title block to Gemini on
  a cache miss, today, with no flag"*, and says [[ADR-005 Local-Only Processing with Cloud
  Licensing]] **needs a second amendment** covering it. That amendment was never written — until
  this note prompted it.
- [[00 - AI Maturity Status]] records that the eval harness *"is **not** network-free: title-block
  OCR calls Gemini on a cache miss."*

So this is not a knowledge gap; it is a **reading** gap, and it is the second time this vault has
produced one. The first was ADR-002's Gemini schema defect, rediscovered from scratch because
`CLAUDE.md` had no inbound link to the vault. The lesson repeats: a fact recorded in a document
nobody opens has the same operational value as a fact nobody knows.

## What is true, stated so it can be quoted

**With no `GEMINI_API_KEY` configured, nothing leaves the machine.** Every path above degrades to a
logged skip or an offline-fallback string rather than an error, so a full audit completes offline.
**With a key configured, drawing content goes to Google as a side effect of ordinary use, and no
surface in the product says so.**

That is a defensible property and a good one. It is not the property ADR-005 claims, and shipping
both sentences at once is the defect.

## The fix that actually closes this class

Not a bigger flag — a test. ADR-005's gap 2 already specifies it:

> *An automated test must assert that a full audit run opens no socket to any host other than the
> licence endpoint.*

That test would have failed on the day each of these four landed. Until it exists, the next
enumeration will go stale the same way this one did, and someone will write "zero egress" again in
good faith.

**Corollary worth keeping:** `ENABLE_LLM_SUMMARY` should stop being described as a privacy control.
It governs one feature. What the claim needs is a single global egress switch, off by default,
covering every call site — one thing to check, instead of four things to remember.
