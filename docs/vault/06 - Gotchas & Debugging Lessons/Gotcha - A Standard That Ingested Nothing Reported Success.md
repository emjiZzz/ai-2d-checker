---
tags: [gotcha, backend, frontend, standards, ingestion, routing, encoding, adr-009]
status: fixed
cache-version: n/a — standards ingestion; no comparison engine or zone-extraction behaviour
date: 2026-08-10
---

# Gotcha — A Standard That Ingested Nothing Reported Success

> [!WARNING] An ADR was written on the strength of a zero. The zero was ours, not the users'.
> `standards` = 0 was read as *"nobody has ever uploaded a standard"* and a whole track was
> retired as **blocked on data, not engineering**. The upload button had never worked.

## The 405

The desktop app posted the ingest form to `POST /api/v1/standards`. The live route table:

```
/api/v1/standards/upload    POST
/api/v1/standards           GET       <-- no POST handler
/api/v1/standards/{id}      DELETE, GET
```

Posting to a GET-only route is **405 Method Not Allowed**, which the dialog rendered as
*"Ingestion Fault: Method Not Allowed."* One missing path segment, in
`createStandardsSlice.ts`. TypeScript cannot catch it: the URL is a string and both spellings
type-check.

**This is the fourth defect of the same shape in this project** — a working endpoint that nothing
correctly reached. See [[Gotcha - A Tested Endpoint That Nothing Ever Called]] and
[[Gotcha - A Guard Clause Named an Exception the Library Stopped Raising]]. The backend was
tested. The route existed. Nothing joined them.

## The rule

**A count of zero is evidence about the system until you have shown the path works.**

[[Gotcha - A Count You Could Not Take Is Not Evidence]] states this for a query that could not
run. Here the same error appears one level up, in a **census**: three collections were counted,
found empty, and the emptiness was attributed to *user behaviour* — nobody wants this feature —
when it was a property of the code. The census was accurate and the inference was not, and the
inference is what reached [[ADR-009 Retiring the Standards Knowledge Track]].

Before concluding "unused", exercise the path once.

## Three more defects, all of which would have poisoned the first real upload

Found while fixing the 405, and each independently sufficient to make an ingested standard
worthless without saying so.

**1. A zero-chunk parse reported success.** The loader answered an empty parse by inventing a
chunk containing only the title the uploader typed:

```python
if not chunks:
    chunks = [{"content": f"Engineering Standard Document: {name}", "fallback": True, ...}]
```

HTTP 200. The standard appears in the list. It reports a chunk. It contains none of its own
content. For a **scanned PDF** — the most likely bad input for engineering standards, since
`pypdf.extract_text()` reads a text layer and never runs OCR — this is the default outcome. And
it is *permanent*: re-uploading the same file hits the duplicate-hash bypass and never re-parses.

Same family as the SHA-256 embeddings ([[RAG Reference Architecture — Gap Analysis]]): **returning
something plausible instead of failing.** Now an error that names the cause and the fix.

**2. `.xls` was advertised by three format lists and readable by none.** The router, the loader
and the parser each carried their own copy of `("pdf", "txt", "md", "xlsx", "xls")`, and Excel is
read with `openpyxl`, which handles the OOXML formats only. A legacy `.xls` passed every check,
then died inside the parser as *"Ingestion process failed. Reference: <uuid>"* — a message naming
neither the cause nor the one-step fix. The three lists are now one constant,
`SUPPORTED_STANDARD_FORMATS`; the fourth caller (the desktop file picker) is checked by test.

> [!NOTE] **Resolved differently, same day: `.xls` is now read, not rejected.**
> The first fix was to reject `.xls` with an actionable message, on the reasoning that supporting
> it means either a second copy of the colour-classification logic or a silently degraded
> `.xls` path — and *"Save As → .xlsx"* is free. That reasoning does not survive **a per-company
> archive of legacy files**, which is what exists here.
>
> **The objection was real and avoidable.** The business rule — which fill colour means what —
> already lived in one function taking a hex string, so only *"get a colour out of this library"*
> differs. Both readers now emit a `_Cell(text, bold, fill_rgb)` and everything downstream is
> shared, pinned by a test asserting the two formats produce **byte-identical** output for
> identical input. Splitting reader from semantics is what made the second format cheap;
> duplicating the parser would not have been.
>
> `xlrd>=2.0.1` reads `.xls` only and openpyxl reads OOXML only, so they are exactly
> complementary. `formatting_info=True` is what keeps `.xls` equivalent rather than degraded, and
> the cost was **measured, not assumed: 1.2 s and 67 MB peak on a real 30.8 MB, 18-sheet
> workbook** — identical to `formatting_info=False`, i.e. free.
>
> One asymmetry is recorded rather than hidden: xlrd exposes no picture API, so `.xls` reports
> `images_ignored: None` where `.xlsx` reports a count. **None, not 0** — zero would assert
> something nobody checked.

**3. `errors="ignore"` on hard-coded UTF-8 was silent corruption in a Japanese CAD shop.** A
Shift-JIS standard decoded to mangled-but-**non-empty** text, which passes every emptiness check
downstream — including the new one in (1) — and lands a corrupted corpus that looks fine. Now
UTF-8 → CP932 → Shift-JIS → UTF-16, strictly, recording which won. *Mangled text is worse than no
text, because no text is detectable.*

## The generic error handler was right, and was the problem

The router replaced every exception with `"Ingestion process failed. Reference: {corr_id}"`. That
is correct for an unexpected exception — it can carry a filesystem path or an internal detail —
and it is useless for *"this is a scanned PDF"* or *"re-save as .xlsx"*, which the person holding
the file can act on immediately.

The fix is not to remove the opaque handler but to **distinguish errors about the user's file from
errors about us**: `StandardIngestError` is surfaced verbatim, everything else still gets the
correlation id. Worth stating because the tempting fix — echo `str(e)` — is a disclosure bug.

## The finding that outlives all of it: the standards are pictures

Running the finished parser over the real `KEMCO and JIS Standards.xls` — 32.3 MB, 18 sheets —
produced **5,757 characters of text**, and *fourteen of the eighteen sheets contain none at all*:

```
  '2D'                                 60 rows     525 chars
  'Piping'                            122 rows    5127 chars
  'Showa Catalog'                      47 rows       1 chars
  'Instrution'                         97 rows     104 chars
  'General Standard Steel'              0 rows       0 chars
  'Steel Pipes'                         0 rows       0 chars
  'Angle Bar Dimensions'                0 rows       0 chars
  'Available Plate Thickness (JIS)'     0 rows       0 chars
  'Bolting (KEMCO Standard)'            0 rows       0 chars
  'JIS Scale'                           0 rows       0 chars
  'Keyplate & Groove'                   0 rows       0 chars
  'Retainer Ring'                       0 rows       0 chars
  'Shaft Keyway'                        0 rows       0 chars
  ...
```

The empty ones are precisely the sheets a checker would consult. 32 MB of file holding 5.7 KB of
text means the rest is **embedded images** — the standards are screenshots of tables.

So the format work was necessary and is not sufficient: `.xls` ingestion is real, keeps its
Japanese (744 CJK characters, zero U+FFFD) and its colour semantics (40 severity markers), and
still yields a corpus consisting mostly of a piping parts list. **The binding constraint on the
standards track is not the file format and never was — it is that the content is not text.**
Whether to OCR these sheets is a genuine decision with a real cost, and it should be taken
knowingly rather than discovered after converting an archive. Recorded here so the next person
does not repeat the conversion work and reach the same 5.7 KB.

## What is still not fixed, deliberately

**Embedded images in a workbook are not read.** `iter_rows()` yields cells; a pasted diagram
contributes nothing. Reading them needs OCR, which is a decision, not an oversight. They are now
**counted** into `metadata["images_ignored"]` and logged, so a standard whose rules live in
pictures says so instead of appearing complete.

## Verified

Route table queried from the running server rather than read from source.
`tests/test_standards_ingest_guards.py` (10) covers the parser half — the loader half needs Mongo,
which the suite does not have, so it is exercised through the parse result it branches on.
`createStandardsSlice.test.ts` (4) pins the URL and was **mutation-checked**: restoring
`/api/v1/standards` fails it. Backend 77 passed on the standards/retrieval selection; frontend
`tsc` clean, vitest 278.

## See also

- [[ADR-009 Retiring the Standards Knowledge Track]] — amended; its census stands, its inference
  does not
- [[Gotcha - A Count You Could Not Take Is Not Evidence]] — the same rule, one level down
- [[Gotcha - A Tested Endpoint That Nothing Ever Called]] — the same shape, third occurrence
- [[Gotcha - The Cache Served Findings That Existed Nowhere]] — also found this session: a
  success path that produced nothing reviewable
