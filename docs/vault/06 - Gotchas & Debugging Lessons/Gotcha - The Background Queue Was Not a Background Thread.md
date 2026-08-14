---
title: Gotcha - The Background Queue Was Not a Background Thread
type: gotcha
tags: [gotcha, ingestion, cad-pipeline, asyncio, event-loop, rendering, performance]
status: resolved
date: 2026-08-12
cache-version: n/a — no comparison cache involvement. The fix moves *where* extraction runs, not
  what it produces; entity output, `render_bounds` and `render_layout` are byte-identical, so
  hard constraint 2 does not apply. If you find yourself wanting to bump `COMPARISON_CACHE_VERSION`
  for a thread hop, re-read the constraint.
related: [ADR-011 Vector as the Only Render Path, Gotcha - A Guard Test's Failure Path Had Never Run]
---

# Gotcha — the background queue was not a background thread

**Class:** event-loop starvation · **Found:** 2026-08-12, from a user-visible symptom that had
been dismissed as cosmetic

---

## Symptom

Uploading any drawing made the desktop app show its **"Server Reconnection"** banner for several
seconds, then recover on its own. Ingestion always completed successfully. Nothing failed, so it
read as a UI flicker.

It was not cosmetic. For the whole of that window the backend answered **no** HTTP request from
anyone.

## Cause

`ExtractionPipeline.run` is `async`, and `BackgroundProcessingQueue._worker` awaits it. Both
words in "background queue" are misleading:

```python
self.worker_task = loop.create_task(self._worker())   # processing_queue.py
```

`create_task` schedules a coroutine **on the event loop that serves HTTP**. "Background" here
means *not inside the request/response cycle* — it does not mean *off the loop*. A synchronous
call inside that task blocks FastAPI exactly as hard as one inside a route handler, and for
longer, because nothing about a background job is expected to be fast.

Two steps were inline:

- `self.parser.parse_file(...)` — ezdxf/PyMuPDF geometry extraction, at all three of its call
  sites (DWG-after-conversion, PDF, direct DXF).
- `render_dxf_background(...)` / `render_pdf_background(...)` — matplotlib rasterisation. The DXF
  one builds a **24×18in figure at dpi=350** and saves at 350 dpi: roughly 8400×6300 px. Seconds,
  reliably.

The client polls `/health` every 5s with a 3s `AbortController` timeout
(`apps/desktop/src/stores/connectionStore.ts`). The render alone overruns that budget, so the
fetch aborts, status goes `offline`, and the next poll shows `reconnecting`.

## Why it survived so long

**The codebase already knew the rule and applied it three times, on either side of the defect.**

- `ODAConverter.convert_dwg_to_dxf` wraps its subprocess in `asyncio.to_thread`.
- The 3D branch — *four lines above the DXF parse in the same method* — is
  `await asyncio.to_thread(ThreeDPipeline.parse_and_convert, ...)`.
- `StandardsLoader.ingest_standard` offloads hash, copy, parse and index build, and is pinned by
  `tests/test_standards_loader_async.py`, written for this exact failure mode after audit
  finding #2.

So the pattern was present, understood, documented and tested — on the *standards* path. The
drawing path, which does far heavier work, had no equivalent guard. **A rule enforced on one
pipeline and not its sibling is not enforced.** When you write a test that pins a property, check
whether a second component has the same property and no test.

The symptom also actively misled: because ingestion always *succeeded*, the banner looked like a
frontend polling artefact rather than a backend stall. The two candidate causes an analysis
naturally reaches for — a `--reload` watcher restart, and a native crash — are both wrong here,
and both are cheap to disprove:

- `start.ps1` passes `--reload-dir "$PSScriptRoot"` (= `services/backend`), while `STORAGE_ROOT`
  is repo-root `storage/`. Renders and temp DXFs land outside the watched tree, and uvicorn's
  watcher only matches `*.py` regardless. `.claude/launch.json` passes no `--reload` at all.
- A single-process uvicorn has no supervisor. A native crash would not recover on its own, and
  the banner always cleared.

## The rule

**`create_task` is not a thread. Anything CPU-bound inside a task must still go through
`asyncio.to_thread`.**

Corollary worth keeping: *the correctness of an async function cannot be read off its own body.*
`ExtractionPipeline.run` looks fine in isolation — it is `async`, it `await`s, it has no obvious
blocking sleep. What makes it a defect is the loop it is scheduled on, which is stated a file away
in `processing_queue.py`. Trace where a coroutine actually runs before deciding it is safe.

## Resolution

All five call sites now go through `asyncio.to_thread` (`extraction_pipeline.py`, step 2 and step
3). `import asyncio` was lifted to module scope from the inline import in the 3D branch.

Pinned by **`tests/test_extraction_pipeline_async.py`**, which uses the same proof technique as
the standards test — record `threading.get_ident()` inside each step, assert it differs from the
test's own thread — and covers both the DXF and PDF branches. It was confirmed to fail against
the pre-fix pipeline naming both offending steps, not merely to pass after.

Two things deliberately **not** done:

1. **The renderers were not ported to the thread-safe matplotlib API.** Both drive the `pyplot`
   state machine, and `render_dxf_background`'s failure path calls `plt.close('all')` — which
   would reach into another thread's figure. That is safe *only* because the queue has a single
   serial consumer, so at most one render is ever in flight. There is a comment at the call site
   saying so. **Parallelising the worker requires porting to `Figure`/`FigureCanvasAgg` first.**
2. **The health check was not made more tolerant.** Requiring two consecutive failures before
   showing the banner was considered and rejected: it hides this class of bug rather than fixing
   it, and the banner was telling the truth. The backend really was unreachable.

## Related

Per [[ADR-011 Vector as the Only Render Path]] the PNG is no longer a display source, but the
backend still renders it on **every** upload — it is where `render_bounds` comes from, and every
zone template's fractions are stored against it. So the expensive render cannot simply be
deleted; it has to be moved off the loop. That is the whole reason this fix takes the shape it
does.
