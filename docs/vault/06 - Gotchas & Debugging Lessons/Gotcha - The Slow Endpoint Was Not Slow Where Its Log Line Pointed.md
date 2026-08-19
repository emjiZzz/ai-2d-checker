# Gotcha - The Slow Endpoint Was Not Slow Where Its Log Line Pointed

> Measured 2026-08-19. Opening a room took roughly ten seconds. Every figure below is from that
> session; re-run the commands rather than quoting these, because the numbers describe a
> *network link*, not the code, and the link is not a constant.

## The symptom, and the thing that made it misleading

The backend log said:

```
Serialized 1046 entities into 6 distinct layers → GET /drawings/{id}/layers 9.4879s
```

The only named component in that line is the serializer, and it is the one component that is
innocent. Per-stage, for that same drawing:

| Stage | Time |
| :--- | ---: |
| MongoDB server-side (`explain`, `executionTimeMillis`) | **4 ms** |
| `GeometrySerializer.serialize_entities` | **14 ms** |
| Beanie `find().to_list()` | **8761 ms** |
| raw motor `find()` — no ODM | **9610 ms** |

The query plan was already optimal: `IXSCAN` on `drawing_id_1`, 1046 keys examined for 1046
returned, no fetch amplification, plan cached. The ODM was not the cost either — dropping to raw
motor was *slower*. 0.85 MB moved in 8.5 s is ~100 KB/s, against a remote Atlas cluster.

**A log line that names a stage is not a measurement of that stage.** This one had been read as
"serialization is slow" for as long as it had been slow.

## ⛔ Negative result: `batch_size` does nothing here

The obvious next hypothesis was round trips — 1046 documents at Mongo's default batching. It was
measured and rejected:

| Query | Time |
| :--- | ---: |
| `count_documents` (one round trip, warm) | 35 ms |
| `find` limit 100 | 710 ms |
| `find` limit 500 | 3862 ms |
| `find` all (1046), default batch | 8453 ms |
| `find` all, `batch_size(2000)` | 8822 ms |

Cost scales with **document count**, not with batch count, and latency per round trip is 35 ms.
Raising the batch size cannot help, and on a rerun it measured *worse* (13752 ms) because the
link is noisy. Do not reach for `batch_size` here again.

## What actually fixed it

Three changes, each measured:

| | Before | After |
| :--- | ---: | ---: |
| `GET /drawings/{id}/layers` | 4410 / 5215 ms | **174 / 197 ms** |
| `GET /rooms` (list) | 5193 ms, 397.9 KB | **103 ms, 7.2 KB** |
| `GET /rooms/{id}` | 1163 ms | **833 ms** |

1. **`infrastructure/storage/entity_cache.py`** — a disk cache for a drawing's entities, and now
   the single read path for all nine call sites that used to spell out
   `ExtractedEntity.find(...).to_list()`. Cached output verified byte-identical to a live fetch.
2. **The room list projects `physical_comparison_results` out at the database.** It holds a whole
   comparison checklist as a JSON string, per room, and the list view renders a name and a
   status. Projected in the *query*, not stripped after — the bytes are the cost.
3. **`GET /rooms/{id}` stamps `last_opened_at` with a targeted `$set`, not `room.save()`.** A
   full save rewrote the entire document, comparison payload included, to change one timestamp.

## The invalidation, because a stale geometry cache renders as a drawing

Three layers, and the third is the one worth copying:

1. `EXTRACTION_SCHEMA_VERSION` is in the cache filename, so the bump CLAUDE.md already requires
   orphans every entry for free.
2. `clear_for_drawing` is called at all three sites that write entities — and in
   `ExtractionPipeline.run` it must come **before** the delete, or a reader landing between the
   delete and the insert caches a blank sheet.
3. **The stored entity count is re-checked against the database on every read** (34 ms). This is
   the net for a write site added later that forgets 1 and 2. It cannot catch a same-count
   replacement, which is what 1 and 2 are for.

A stale entity cache does not throw — it renders as a plausible drawing with geometry missing.
That is why the net exists at all, and why an empty result is deliberately never cached.

## ⚠ Windows: a profiling script can start a web server

Twice during this session, running a plain script that imported a backend module spawned **whole
uvicorn stacks** — because Windows `multiprocessing` uses spawn, which re-imports the parent
module, and the script had no `if __name__ == "__main__":` guard. Two servers then held port
8080, the original wedged and stopped answering `/health`, and it had to be restarted.

Guard any script that imports from `services.backend`. The symptom is several `python.exe`
processes whose parent is your script, and a backend that listens without responding.

## Related

- [[Gotcha - Comparison Cache Invalidation]] — the same versioned-cache pattern, one layer up
- [[Gotcha - A Count You Could Not Take Is Not Evidence]]
- `tests/test_entity_cache.py`, `tests/test_room_list_projection.py`
