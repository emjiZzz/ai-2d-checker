# Gotcha - A Write That Sent One Field And Returned The Whole Document

> Measured 2026-08-19, against the live Atlas cluster. Re-run rather than quote: every figure
> here describes a *network link*, not the code, and the link is not a constant. Sibling of
> [[Gotcha - The Slow Endpoint Was Not Slow Where Its Log Line Pointed]] — same cluster, same
> root cause, and the same failure of an obvious-looking fix to be a complete one.

## The symptom

`GET /api/v1/rooms/{id}` took **4.53 s** for one room. Latency was almost exactly linear in a
single field, `physical_comparison_results` — a comparison checklist stored as a JSON string:

| Room | That field | Endpoint |
| :--- | ---: | ---: |
| Manual check 2 | 0 KB | 0.156 s |
| 2A2 | 32 KB | 1.004 s |
| 230A | 60 KB | 1.795 s |
| **228** | **166 KB** | **4.541 s** |

## The part that was already "fixed"

The handler had been optimised once, and its comment said so:

> `$set` on the one field, not `room.save()`. […] The targeted update sends the timestamp alone.

That is true, and it is half a fix. Stamping `last_opened_at` still cost **2.01 s of the
4.53 s** — as much as reading the room:

```
Room.get()                    1.907 s
room.set(last_opened_at)      1.907 s      <- the "fixed" line
validate + response + dump    0.004 s
```

Beanie's `Document.update` (`beanie/odm/documents.py`) issues:

```python
result = await self.find_one(find_query).update(
    *arguments, response_type=UpdateResponse.NEW_DOCUMENT, ...
)
...
merge_models(self, result)
```

`NEW_DOCUMENT` is `find_one_and_update(..., return_document=AFTER)`. **The request carried one
timestamp; the response carried the entire 166 KB document back**, so Beanie could re-sync the
in-memory instance. Neither `save()` nor `set()` can express *write this and tell me nothing*.

A raw `update_one` is **0.041 s against 2.2 s**, and needs no cache, no schema change and no
new abstraction:

| | before | after |
| :--- | ---: | ---: |
| stamp `last_opened_at` | 2.007–2.292 s | **0.041 s** |
| fetch the room | 1.973–2.230 s | **0.043 s** (projected; payload from disk) |

Verified end-to-end after restarting the backend, `GET /api/v1/rooms/{id}`:

| Room | That field | Before | After (warm) |
| :--- | ---: | ---: | ---: |
| Manual check 2 | 0 KB | 0.156 s | 0.143 s |
| 2A2 | 32 KB | 1.004 s | 0.149 s |
| 230A | 60 KB | 1.795 s | 0.151 s |
| **228** | **166 KB** | **4.541 s** | **0.148 s** |

Warm latency is now flat in payload size, which is the point — the linear relationship was the
whole symptom. A miss (first open after a re-comparison) is **2.653 s**, still below the old
best case because the write half no longer costs anything. All 11 live rooms were checked field
-by-field against the raw documents: **11/11 identical to the database.**

## The lesson

**A write is a round trip, and an ODM decides the size of the return leg for you.** The cost
model everyone reasons about — "an update sends only what changed" — describes the request and
is silent about the response. On a local database the difference is invisible; against a remote
cluster at ~80 KB/s it is the whole latency.

Two things generalise past this bug:

- **Half a fix measures as a fix if you only measure the half you changed.** The `$set` comment
  quoted a real before/after (1.16 s → 0.83 s) and was accurate. It just never asked what came
  back, and the endpoint kept a 2 s write nobody was looking for, *documented as optimised* —
  which is worse than an undocumented one, because the comment tells the next reader not to
  look. Compare [[Gotcha - A Verdict Mapping That Contradicted Its Own Comment]].
- **The linear-in-one-field signature is the tell.** When latency scales with a payload and all
  CPU on that payload totals single-digit milliseconds, stop profiling code and start counting
  bytes on the wire — in *both* directions.

## What was changed

- `api/routers/rooms.py::get_room` — raw `update_one` for the timestamp; fetch projects
  `physical_comparison_results` out and restores it from disk.
- `infrastructure/storage/room_results_cache.py` — new. Keyed `(room_id, updated_at)` with the
  stamp *in the filename*, so a changed document orphans its own entry. Sound because `PATCH
  /rooms/{room_id}` is the field's only writer and bumps `updated_at` on the line above its
  `save()`; `get_room` deliberately stamps `last_opened_at` only, so opening a room does not
  invalidate that room's entry.
- `api/dependencies.py::get_or_404` — optional `projection`. ⚠ Its `except InvalidId` branch,
  documented since Beanie 2.x as unreachable, is **live again**: the projected path goes through
  bson's `ObjectId` rather than Beanie's `TypeAdapter`. Both branches now have exactly one live
  caller. Keep both.

## Two traps met while pinning it

**The reloader was inert.** `uvicorn --reload` had not restarted since 16:38, so the first
"after" measurement reproduced the *before* numbers exactly. Two uvicorn processes were bound at
the same port spec and the one holding it was the **system interpreter, not the venv** — the
precise failure `services/backend/start.ps1` already carries a comment about, where a
dot-sourcing bug let `python` resolve off `PATH`. Confirm the server restarted (the app writes
one log file per PID) before believing any before/after.

**A source-matching test matched its own explanation.** `test_the_detail_endpoint_writes_only_
the_timestamp` asserted `"room.set(" not in src` and failed against correct code — it had
matched the *comment saying why `room.set()` is not used*. `ast.get_source_segment` returns
comments; `ast.unparse` does not. Both directions were affected, and the positive assertions
were the more dangerous half: `'"physical_comparison_results": 0' in src` would have passed on a
comment while the query dragged the field across regardless.

⚠ Two assertions in `tests/test_room_list_projection.py` also had to be rewritten because they
pinned a *mechanism* as a proxy for behaviour (`"projection" not in src` meaning "the detail
endpoint returns the payload"). They failed while the behaviour they stood for was intact. Same
lesson `get_or_404`'s docstring already states: a guard naming a concrete mechanism is a
dependency on that mechanism.
