---
tags: [gotcha, backend, api, beanie, pydantic, error-handling, frontend, review-ui]
status: fixed
cache-version: n/a — API error handling and a UI gate; no engine or zone-extraction behaviour
date: 2026-08-10
---

# Gotcha — A Guard Clause Named an Exception the Library Stopped Raising

> [!WARNING] A supervisor clicked **Approve** and got `500 INTERNAL_SERVER_ERROR`. The guard written
> to prevent exactly that was present, correct-looking, and **inert** — it caught an exception the
> installed version of Beanie no longer raises. Every one of ~24 routes was affected.

## What happened

`PATCH /audits/violations/phys_chk_restored_1_1786329084013/review` → 500. From the log:

```
File "services/backend/api/dependencies.py", line 47, in get_or_404
    doc = await model.get(id)
File "beanie/odm/documents.py", line 243, in get
    document_id = parse_object_as(...)
pydantic_core._pydantic_core.ValidationError: 1 validation error
  Value error, Id must be of type PydanticObjectId
    input_value='phys_chk_restored_1_1786329084013'
```

`get_or_404` exists **for this exact bug** and says so in its own docstring:

> *Beanie raises InvalidId (not a clean 404-able None) when `id` isn't a well-formed ObjectId, which
> previously surfaced as an unhandled 500 on every router that took a raw path-param id straight
> into `Model.get(id)`.*

It caught `bson.errors.InvalidId`. **Beanie 2.x validates the id through a Pydantic `TypeAdapter`
before it reaches bson**, so on beanie 2.1.0 / pydantic 2.13.4 that call cannot raise `InvalidId` at
all — it raises `pydantic.ValidationError`. The guard kept compiling, the suite kept passing, and it
had quietly stopped guarding for every caller: annotations, audits, drawings.

## The rule

**A guard clause naming a concrete exception type is a dependency on that library's internals, and
it is the one kind of dependency nothing verifies.** A renamed method breaks the build. A changed
signature breaks a test. An exception type that stops being raised breaks *nothing* — the `except`
arm simply never runs again, and the code reads exactly as it did when it worked.

The fix catches both, and says why, because the tidy-looking cleanup is to delete the one that
"can't happen":

```python
except (InvalidId, ValidationError):
    doc = None
```

Same family as [[Gotcha - A Guard Test's Failure Path Had Never Run]] and
[[Gotcha - A Swallowed AttributeError Made a Write Path a Permanent No-Op]]: **code that only runs
when something goes wrong is code nothing has ever run.** Here the failure path had not merely gone
unexercised — it had become unreachable, and no signal existed to say so.

## It took two independent defects to become visible

Neither would have surfaced alone, and that is why this sat in a shipped endpoint.

**Frontend:** the verdict block was gated on `matchingViolation` alone, so it rendered on a MATCHED
row carrying a **client-side canvas marker** — `phys_chk_restored_…`, synthesised in
`markerGenerator.ts`, with no `AuditViolation` document behind it. The comment directly above that
gate stated the rule it failed to implement:

> *Supervisor verdict, **on findings only**. A MATCHED row is the engine reporting no change: there
> is nothing to approve, and **the orchestrator never persists one as an AuditViolation**.*

Worse, `isPersistedViolationId` already existed for precisely this, was used by the visibility
toggle **two lines above**, and predicted the whole thing:

> *A supervisor verdict on a synthetic marker would PATCH a document that does not exist — a 404 the
> reviewer would read as "my review did not save", on a row that was never reviewable in the first
> place. Better to not offer the control than to offer one that cannot work.*

**Backend:** the malformed id then hit the inert guard and became a 500 instead of that predicted
404.

So: without the frontend defect nobody ever sends a malformed id and the dead guard is never
noticed; without the backend defect it is a quiet 404 nobody investigates. Compare
[[Gotcha - A Tested Endpoint That Nothing Ever Called]] — *two independent faults on one path*, again.

**Rule: a comment stating a rule is not the rule.** Three places in this file described the intended
gate and the boolean implemented one third of it. When a condition and the prose above it disagree,
the condition wins, silently.

## The third defect, found by fixing the first two

Gating the control on "is this reviewable" made it vanish from **every** comparison finding — which
is how the real problem surfaced: **the checklist had no reviewable identity at all.**

The backend persists a real `AuditViolation` per non-MATCHED finding
(`orchestrator.py`, `insert_many`) and returns the owning session id in
`diagnostics.audit_session_id`. The 2D checklist renders `canvas_markings` instead — a payload with
**no id field** — so `markerGenerator.ts` and `roomStore.ts` invent `phys_chk_*` ids. Three other
places in the app already call `GET /audits/sessions/{id}/violations`; this screen was the one that
did not. So Approve had never once recorded a review: 500 before, 404 after.

**The obvious fix is unavailable, and that is worth knowing before someone tries it.** Adding
`violation_id` to `CanvasMarking` would put the field in Gemini's `response_schema`
(`gemini_client.py`, CLAUDE.md constraint 1) — an id the model would be asked to invent — and would
need a `COMPARISON_CACHE_VERSION` bump (constraint 2). So the join is client-side:
`utils/persistedViolations.ts` fetches the session's violations and matches them onto the markers.

**The join is on content, not on index.** `insert_many` preserves order, so "Nth non-MATCHED marker
↔ Nth violation" looks correct and is rejected: MongoDB does not guarantee natural read order, and
an index join fails *silently and wrongly* — attaching a supervisor's verdict to a finding they
never looked at. A content join can only fail by matching nothing. Two passes, entity handle then
`(category, status, text)`, each violation claimed once — the same shape as `ChecklistPanel`'s own
row→violation resolution, and for the same reason.

The parse keys off the backend's exact f-strings (`comparison_{category}`, `[{status}] {details}`,
`Resolve discrepancy in '{text}' against the reference drawing.`), which the tests reproduce
**literally** rather than sharing a helper — if that wording changes, they must fail.

## The fix, three parts

- `dependencies.py::get_or_404` catches `(InvalidId, ValidationError)`. One line, ~24 call sites.
- `usePhysicalComparison` and `roomStore`'s restore branch join the persisted ids onto the markers.
  The restore branch also stopped dropping `status` and `entity_handle`, which the live path kept.
- The verdict block is gated on `reviewableViolationId(...)`, which returns the id to PATCH or
  `null` — one question, one answer, so a caller cannot check one id and submit another.

The backend fix alone is not sufficient: a 404 in red still tells a reviewer their verdict failed to
save. The frontend gate alone is not sufficient either — it removes the feature. Only the join
restores it.

## Verified

**Live, against the running server** (uvicorn runs with `--reload`, so it had already picked the
change up) — the exact request from the traceback:

```
PATCH /api/v1/audits/violations/phys_chk_restored_1_1786329084013/review
HTTP 404  {"detail":"Audit violation not found."}
```

and a well-formed-but-absent ObjectId likewise 404s, so the fix did not simply make everything fail
one way.

**Mutation-tested**, because a regression test that passes either way proves nothing: reverting the
except clause to `except InvalidId` makes `tests/test_malformed_id_is_404.py` fail. That file also
pins the **older** bson path with a stub raising `InvalidId`, so the guard stays version-independent
rather than tracking whichever exception today's library happens to throw.

**The join was verified against live data, not fixtures.** A real session's 32 violations were
fetched from the running API and fed to the real `parsePersistedViolation` / `reconcilePersistedIds`:
**32 of 32 parsed, 32 of 32 joined to distinct documents**, Japanese text intact. That is the check
that matters, because the join depends on f-strings in another language in another process — a
fixture I wrote myself would only have proved I can copy my own assumptions.

**No verdict was recorded during verification, deliberately.** Clicking Approve on a real finding
would inject a judgment no human made into the `lessons` corpus — the exact thing this feature
exists to collect. The write path is covered by `test_violation_review_response.py` instead.

Backend 863 tests, 2 known pre-existing failures. Frontend `tsc` clean, vitest 273/273.

## See also

- [[Gotcha - A Tested Endpoint That Nothing Ever Called]] — the endpoint this defect lives on, and
  the same two-independent-faults-on-one-path shape
- [[Gotcha - A Child Cannot Claim Its Own Line in a Nowrap Flex Row]] — the other defect in this same
  verdict block, and the same lesson from the CSS side: a comment asserting something is handled,
  over code that does not handle it
- [[Gotcha - A Guard Test's Failure Path Had Never Run]] — the failure path nothing executes
- [[Gotcha - A Swallowed AttributeError Made a Write Path a Permanent No-Op]] — an `except` arm that
  turned a defect into silence
