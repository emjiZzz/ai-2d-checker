---
tags: [gotcha, tooling, measurement, documentation-drift, extraction]
status: fixed
cache-version: n/a — no engine change; the mutation invariant is byte-identical
date: 2026-08-20
---

# Gotcha — Three Quoted Figures That No Command Could Reproduce

> Found by building four measurement tools and running them. Every one of the three documented
> figures they were able to reproduce turned out to be **wrong**. None had been wrong when it
> was written.

## The shape of it

CLAUDE.md opens with the rule: *"Measure the count, do not quote it — this block has already
carried a stale one."* It then quoted three more, in three different sections, and all three
had rotted by the time anything could check them:

| Documented | Actual, measured 2026-08-20 | How long nobody could tell |
| :--- | :--- | :--- |
| cull sweep: **23 of 32** drawings cull nothing, max **10** | **37 of 55**, max **8** | since it was written — `main()` took a single DXF |
| `EXTRACTION_SCHEMA_VERSION` is **6**, and *"nothing reads it yet"* | **7**, and now something does | weeks |
| `--provenance mutation` *"reproduces `baseline-v48.json` exactly at P 0.9796"* | **P 0.96 / F1 0.9143** at cache v53 | unknown |

The common cause is not carelessness. **Each figure was quoted rather than produced.** There was
no command that regenerated any of them, so the only thing keeping them true was that nothing had
changed — and things changed.

This is [[Gotcha - A Checklist Item With No Producer Reported Clean]] and
[[Gotcha - A Count You Could Not Take Is Not Evidence]] a third time, at the level of the
documentation rather than the code. The escalation worth noticing: the cull sweep figure was not
merely undocumented-as-unmeasurable, it was **mandated as a pre-landing check**. The docs told
you to re-run a sweep that did not exist.

## What the producers found on first run

Building them was cheap. What they returned was not:

* **`render_audit.py --sweep`** — the denominator alone gives the drift away: `storage/uploads`
  holds **55** drawings, not 32. The cull *rule* is fine; the sweep agrees with the single-sheet
  path at 7 on the documented sheet. Only the figures had moved.

* 🔴 **`tools/extraction_status.py`** — **36 of 55 stored drawings are stale, 20 of them at v2**,
  five versions behind. They are missing dimension text anchors, leader hooklines, leader
  arrowheads and the angular-dimension degree conversion. **They render wrong, and have been
  rendering wrong,** and nothing could say so because the field recording it had no reader.

* **`scorer.py` → `recall_by_entity_type`** — on the mutation corpus the breakdown lists only
  `text` and `dimension`. **There are no line, arc or polyline findings in it at all**, so that
  corpus structurally cannot measure the geometry case that
  [[Gotcha - The Click Was Never Where the Entity Was]] had just broken on. One line of output;
  invisible in every aggregate the eval prints.

* **`tools/address_audit.py`** — clean: 97.2% correct, 0 wrong, 3029/3029 round trip. Verified
  to be a real check by restoring the old resolver in memory, where it reports 28 wrong.

## Two near-misses that are the actual lesson

### 1. A query that finds nothing proves nothing

Chasing whether any committed label had captured an angular dimension in radians, the first scan
looked for `dim_kind` / `dimtype` and returned **empty**. The property is `dim_type`. The silence
was not evidence of a clean corpus; it was evidence of a wrong key, and it looked exactly the
same.

Re-run correctly, there **are** 12 angular dimensions in the corpus — and they are fine:
`M745204N01` stores text `60°` (codepoints `0x36 0x30 0xb0`), so its payload post-dates the v7
fix, and `M745227N01`, whose live drawings sit at v2, has **zero** angular dimensions.

**The corpus is clean. That is a measurement, not an assumption — and it was nearly a
fabrication.** Before reporting that a search found no problems, show that the search could have
found one.

### 2. A gap that was not a gap

A fifth tool was nearly proposed on the claim that `eval_corpus.py validate` does not check
address resolvability. **It does**, via `_addressable()`. Checked before writing it down, and
dropped. A tool built to close an imaginary gap is worse than no tool: it is permanent evidence
of a problem that never existed.

## The remaining hole this exposed, and closed

A corpus payload records **no extraction provenance at all**. `ref.drawing.json` carried
`entity_counts`, `file_hash`, `file_name`, `format`, `id`, `metadata`, `status` — and nothing
about which extractor produced it. So *"was this labelled pair captured from a stale drawing?"*
could only be answered by reading entity values and inferring, which is how the check above had
to be done.

It matters because extraction-time fixes are frozen into the payload: the v7 note states that
text captured as ground truth through `EntityAddress.text` is wrong on pre-v7 rows. `M745227N01`
is a **labelled** pair whose live drawings are at v2.

Fixed: `extraction_schema_version` now travels on `EvalDrawing` (into `{side}.drawing.json`) and
on `PairSide` (into the manifest), and `warn_if_stale_extraction` complains at **export** — the
last moment where the problem is cheap, because afterwards the payload is sha256-frozen and its
labels are authored against it.

⚠ **`0` means unknown, not version zero.** Every pair exported before 2026-08-20 lacks the field.
Unknown and stale get different messages because the remedy differs.

⚠ **The warning is the point, not the field.** `EXTRACTION_SCHEMA_VERSION` spent weeks stamped on
every drawing with no reader — that is the second row of the table above. Adding a second unread
field one layer down would have reproduced the same defect inside the fix for it.

## Rules

* **A figure in the docs must name the command that regenerates it.** Without one it is a claim
  with a shelf life, and nothing announces its expiry. Every number this session corrected now
  sits beside its command.
* **A mandated check with no producer is worse than no check**, because the mandate is read as
  evidence the check happens.
* **A search that returns nothing has proven nothing until you have shown it could return
  something.** Verify the failure path of a query before trusting its silence.
* **Adding a field is not closing a gap; adding a reader is.** An unread field is the same defect
  in a new place.
* **Denominators drift first.** Two of the three figures were detectable from the row count alone
  — 32 vs 55 — long before anyone examined the metric.

## Verified

`pytest` **1410 passed, 2 failed, 3 skipped** — both failures pre-existing and confirmed by
reverting (`test_committed_corpus_has_every_ocr_reading_captured`, which is `M745204N01`'s absent
OCR payload, and the environment-dependent `test_database_retry_handling`). Frontend **558
passed**, `tsc --noEmit` clean. The mutation invariant is **byte-identical** before and after
every change here — tp 48, fp 2, fn 7, duplicates 1 — so none of this touched the engine.

Related: [[Gotcha - The Click Was Never Where the Entity Was]],
[[Gotcha - A Checklist Item With No Producer Reported Clean]],
[[Gotcha - A Count You Could Not Take Is Not Evidence]],
[[Gotcha - A Tested Endpoint That Nothing Ever Called]],
[[Gotcha - Every Published Baseline Measures a Configuration Users Do Not Get]].
