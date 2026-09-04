"""A disk cache for a Room's `physical_comparison_results`, and the one place that reads it.

Measured 2026-08-19 against live Atlas, on the largest of 11 rooms (166 KB in that one field):
`GET /rooms/{id}` took 4.53 s, of which the fetch was 1.97 s and stamping `last_opened_at` a
further 2.01 s, while all CPU on the document totalled 4 ms. Latency is linear in the field --
0 KB / 0.16 s, 32 KB / 1.00 s, 166 KB / 4.54 s -- so the cost is bytes crossing the link to a
remote cluster, as for `entity_cache`, and nothing on the query side reaches it.

The second 2 s was not the write. Beanie's `Document.update` issues
`response_type=UpdateResponse.NEW_DOCUMENT`, a `find_one_and_update` returning the document after
the update, then merges it back -- so stamping a timestamp dragged the whole 166 KB back.
`get_room` now issues a raw `update_one`, 0.041 s against 2.2 s, needing no reply. That half
needed no cache, which is why it is not implemented here.

The key is `(room_id, updated_at)`, with the stamp in the filename, so a changed document orphans
its own entry rather than relying on anyone remembering to clear it. That holds because
`physical_comparison_results` has exactly one writer, `PATCH /rooms/{room_id}`, which sets
`updated_at` on the line before `save()`; `GET` stamps `last_opened_at` only, deliberately, so
opening a room does not invalidate it. A second writer must bump `updated_at` too or it will serve
a stale checklist, which would render as a plausible comparison rather than an error.
`tests/test_room_results_cache.py::test_physical_comparison_results_has_exactly_one_writer` pins
that by parsing `rooms.py`.

Unlike `entity_cache` there is no live-count safety net: the results are one opaque string with no
cheap server-side property to probe. The key is the whole guarantee.
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
