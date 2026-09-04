"""A disk cache for a drawing's extracted entities, and the one place that reads them.

## Why this exists

Measured 2026-08-19 against the live Atlas cluster, for drawing `6a741fc6e01d720e27be28e1`
(1046 entities, 0.85 MB):

    server-side query (explain)          4 ms    IXSCAN on drawing_id_1, 1046 keys / 1046 docs
    Beanie find().to_list()           8761 ms
    raw motor find (no ODM)           9610 ms
    GeometrySerializer.serialize      14 ms

The query is optimal and the serializer is free. The 8.5 seconds is the network: cost scales
with document count (100 docs 710 ms, 500 docs 3862 ms, 1046 docs 8453 ms — ~8 ms each) and
`batch_size` does not move it, so it is throughput against a remote cluster and not round
trips. Nothing on the query side can reach it.

`GET /drawings/{id}/layers` is called twice on every room open, so that was ~10 s of a room's
open time. This cache reads the same entities in ~150 ms:

    read + parse cache                  44 ms
    rehydrate to ExtractedEntity        53 ms
    count_documents validation probe    34 ms
    ------------------------------------------
                                      ~131 ms   (then the same 17 ms serialize)

Output verified byte-identical to the live fetch.

## Invalidation — three layers, deliberately

1. `EXTRACTION_SCHEMA_VERSION` is in the filename. CLAUDE.md already requires bumping it when
   an extraction-time field is added, so every such bump orphans every entry for free.
2. `clear_for_drawing` is called at all three sites that write entities (the extraction
   pipeline's replace, and the two deletes). This is the precise mechanism.
3. The stored entity count is re-checked against the database on every read. This is the
   safety net for a write site added later that forgets (1) and (2). It costs one indexed
   `count_documents` — 34 ms against 8500 — and turns "stale forever, silently" into "stale
   until the count changes", which is the failure mode this repo pays for most often.

Layer 3 cannot catch a replacement that keeps the count identical. That case is what layers 1
and 2 are for; the net is a net, not a substitute.
"""

from __future__ import annotations

import os
from pathlib import Path

from bson import json_util

from ...domain.models.extracted_entity import EXTRACTION_SCHEMA_VERSION, ExtractedEntity
from ...logger import logger
from .path_resolver import get_storage_root

# Bump when the CACHE FILE FORMAT changes (not when extraction changes — the schema version in
# the key handles that). v1: initial format, {"count": int, "docs": [...]} via bson.json_util.
ENTITY_CACHE_VERSION = "v1"


def _cache_path(drawing_id: str) -> Path:
    cache_dir = get_storage_root() / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / f"entities_{ENTITY_CACHE_VERSION}_s{EXTRACTION_SCHEMA_VERSION}_{drawing_id}.json"


def clear_for_drawing(drawing_id: str) -> None:
    """Drop every cached entity payload for a drawing, across all schema versions.

    Globbed rather than pointed at the current version's filename: a drawing extracted under an
    older schema still has an entry, and leaving it behind means a later downgrade — or a
    re-extraction that lands on the older version — reads a payload nobody invalidated.
    """
    cache_dir = get_storage_root() / "cache"
    if not cache_dir.exists():
        return
    for stale in cache_dir.glob(f"entities_*_{drawing_id}.json"):
        try:
            stale.unlink()
            logger.info(f"Entity cache: cleared {stale.name}")
        except OSError as err:
            # Not fatal: the count probe in `load_entities` is what makes a survivor harmless.
            logger.warning(f"Entity cache: could not clear {stale.name}: {err}")


def _write(drawing_id: str, entities: list[ExtractedEntity]) -> None:
    path = _cache_path(drawing_id)
    # Temp file + atomic replace. A torn read here would deserialize as a *partial drawing*,
    # which renders as a plausible sheet with geometry missing rather than as an error.
    tmp = path.with_suffix(f".{os.getpid()}.tmp")
    try:
        payload = {
            "count": len(entities),
            "docs": [e.model_dump(by_alias=True) for e in entities],
        }
        tmp.write_text(json_util.dumps(payload), encoding="utf-8")
        os.replace(tmp, path)
    except (OSError, TypeError, ValueError) as err:
        logger.warning(f"Entity cache: could not write {path.name}: {err}")
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


async def load_entities(drawing_id: str) -> list[ExtractedEntity]:
    """Every extracted entity for a drawing — from cache when it is provably current.

    This is the single read path. The nine call sites that each spelled out
    `ExtractedEntity.find(ExtractedEntity.drawing_id == x).to_list()` now share one answer to
    "give me this drawing's entities", so a cache that only some of them consulted cannot exist.
    """
    path = _cache_path(drawing_id)
    if path.exists():
        try:
            payload = json_util.loads(path.read_text(encoding="utf-8"))
            live_count = await ExtractedEntity.find(ExtractedEntity.drawing_id == drawing_id).count()
            if payload.get("count") == live_count:
                return [ExtractedEntity.model_validate(d) for d in payload["docs"]]
            logger.info(
                f"Entity cache: stale for {drawing_id} "
                f"(cached {payload.get('count')} vs live {live_count}) — refetching."
            )
        except Exception as err:  # noqa: BLE001 — a bad cache file must never fail a request
            logger.warning(f"Entity cache: unreadable {path.name} ({err}) — refetching.")

    entities = await ExtractedEntity.find(ExtractedEntity.drawing_id == drawing_id).to_list()
    if entities:
        _write(drawing_id, entities)
    return entities
