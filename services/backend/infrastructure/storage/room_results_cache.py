"""A disk cache for a Room's `physical_comparison_results`, and the one place that reads it.

## Why this exists

Measured 2026-08-19 against the live Atlas cluster, for room `6a7ec3f80f7b1df1dd247b2f`
("228") — 166 KB in that one field, the largest of the 11 live rooms:

    GET /api/v1/rooms/{id}                          4.53 s
      - Room.get()              (full document)     1.97 s
      - room.set(last_opened_at)                    2.01 s   <- see below
      - validate + _to_response + model_dump_json   0.004 s

    find_one WITHOUT physical_comparison_results    0.043 s
    find_one WITH it                                2.03 s

Latency is linear in that one field across every room — 0 KB / 0.16 s, 32 KB / 1.00 s,
60 KB / 1.80 s, 166 KB / 4.54 s — while all CPU on the fetched document totals 4 ms. So the
cost is bytes crossing the link to a remote cluster, exactly as for `entity_cache`, and
nothing on the query side can reach it.

The second 2 s was not the write. The `$set` note in `rooms.py::get_room` was half a
fix: it stopped *sending* the field, but Beanie's `Document.update` issues
`response_type=UpdateResponse.NEW_DOCUMENT` (`beanie/odm/documents.py`) — a
`find_one_and_update` returning the document AFTER the update — and then `merge_models` it
back into the in-memory object. So stamping a timestamp dragged the whole 166 KB *back*.
`get_room` now issues a raw `update_one`: 0.041 s against 2.2 s, and it needs no reply.
That half needed no cache at all, which is why it is not implemented here.

## Invalidation

The key is `(room_id, updated_at)` with `updated_at` in the filename, so a changed
document orphans its own entry instead of relying on anyone remembering to clear it.

That is sound because `physical_comparison_results` has exactly one writer — `PATCH
/rooms/{room_id}` — and it sets `room.updated_at = now()` on the line before `room.save()`.
`GET /rooms/{room_id}` stamps `last_opened_at` only, deliberately, so opening a room does not
invalidate the room's own entry.

A second writer of that field must bump `updated_at` too, or it will serve a stale
checklist — the failure mode this repo pays for most often, and here it would render as a
plausible comparison rather than as an error.
`tests/test_room_results_cache.py::test_physical_comparison_results_has_exactly_one_writer`
pins that assumption by parsing `rooms.py`, so adding a second writer fails loudly there.

Unlike `entity_cache`, there is no live-count safety net: a room's results are one opaque
string with no cheap server-side property to probe. The key is the whole guarantee, so it is
derived from the same `updated_at` the response reports.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from ...logger import logger
from .path_resolver import get_storage_root

# Bump when the CACHE FILE FORMAT changes. v1: the raw JSON string as stored on the document,
# written verbatim; a zero-byte file means the field is None (compared, then cleared, or never
# compared at all). Stored verbatim rather than wrapped in an envelope because the payload is
# already a JSON string — wrapping would escape 166 KB of it on every write and unescape it on
# every read, to carry one bit that a file's size already carries.
ROOM_RESULTS_CACHE_VERSION = "v1"


def _stamp(updated_at: datetime | None) -> str:
    """A filename-safe key component that is stable across the timezone round-trip.

    `PATCH` sets `datetime.now(timezone.utc)` (aware) in memory, while the same value read
    back from Mongo is naive UTC. Normalising to naive UTC here keeps the write-side and
    read-side keys identical; skipping it would not corrupt anything, but it would miss the
    cache exactly once per save — on the reopen that follows it, which is the common flow.
    """
    if updated_at is None:
        return "0"
    if updated_at.tzinfo is not None:
        updated_at = updated_at.astimezone(timezone.utc).replace(tzinfo=None)
    return updated_at.strftime("%Y%m%d%H%M%S%f")


def _cache_dir() -> Path:
    cache_dir = get_storage_root() / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def _cache_path(room_id: str, updated_at: datetime | None) -> Path:
    name = f"room_pcr_{ROOM_RESULTS_CACHE_VERSION}_{room_id}_{_stamp(updated_at)}.json"
    return _cache_dir() / name


def clear_for_room(room_id: str) -> None:
    """Drop every cached results payload for a room, across all stamps and format versions.

    Not needed for correctness — a stale stamp can never be read, because the reader only ever
    asks for the stamp it just read off the document. This is housekeeping so a room that is
    recompared fifty times does not leave fifty files behind, and the delete path's cleanup.
    """
    cache_dir = get_storage_root() / "cache"
    if not cache_dir.exists():
        return
    for stale in cache_dir.glob(f"room_pcr_*_{room_id}_*.json"):
        try:
            stale.unlink()
        except OSError as err:
            # Not fatal: an orphan is unreadable by construction, it only wastes disk.
            logger.warning(f"Room results cache: could not clear {stale.name}: {err}")


def store(room_id: str, updated_at: datetime | None, payload: str | None) -> None:
    """Cache a room's results string against the `updated_at` it was saved with."""
    path = _cache_path(room_id, updated_at)
    # Temp file + atomic replace. A torn read here would parse as a *partial checklist* —
    # findings silently missing from a comparison that still renders — not as an error.
    tmp = path.with_suffix(f".{os.getpid()}.tmp")
    try:
        tmp.write_text(payload or "", encoding="utf-8")
        os.replace(tmp, path)
    except OSError as err:
        logger.warning(f"Room results cache: could not write {path.name}: {err}")
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def load(room_id: str, updated_at: datetime | None) -> str | None | bool:
    """The cached results string for this exact `updated_at`.

    Returns the string, or `None` for a room whose field is None, or `False` for a miss.
    Three-valued because "no results" and "not cached" are different answers and collapsing
    them would refetch 166 KB on every open of a room that has none.
    """
    path = _cache_path(room_id, updated_at)
    if not path.exists():
        return False
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as err:  # a bad cache file must never fail a request
        logger.warning(f"Room results cache: unreadable {path.name} ({err}) — refetching.")
        return False
    return text or None
