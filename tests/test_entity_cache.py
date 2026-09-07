"""What the entity cache serves, and — mostly — when it refuses to.

The endpoint it exists for costs 8.5 s against the remote cluster and ~150 ms from disk
(measured 2026-08-19; see the module docstring). That ratio is large enough that the cache will
be hit on essentially every read, so the tests that matter are the ones about staleness: a
cache that silently serves last week's geometry renders as a *plausible drawing*, not as an
error, which is the failure shape this repo pays for most often.
"""

import json
from unittest.mock import MagicMock

import pytest
from bson import json_util

from services.backend.domain.models.extracted_entity import (
    EXTRACTION_SCHEMA_VERSION,
    ExtractedEntity,
)
from services.backend.infrastructure.storage import entity_cache


@pytest.fixture(autouse=True)
def constructible_entities(monkeypatch):
    """Let the real `ExtractedEntity` be built without a database.

    Beanie's `Document.__init__` reaches for its pymongo collection, so neither the constructor
    nor `model_validate` works uninitialised. Stubbing the collection getter — the same trick
    `test_extraction_replacement.py` uses — keeps the REAL model in these tests. A hand-written
    double would have to be pinned against the model to be worth anything, and there is no
    reason to take on that duplication when the real one can simply be made to work.
    """
    monkeypatch.setattr(
        ExtractedEntity, "get_pymongo_collection", classmethod(lambda cls: MagicMock())
    )
    # `ExtractedEntity.drawing_id` at class level is a Beanie query field that only exists once
    # the model is initialised; the cache builds its filter from it. Same stand-in as
    # `test_extraction_replacement.py` — the value is never inspected, only passed to `find`.
    monkeypatch.setattr(ExtractedEntity, "drawing_id", "drawing_id", raising=False)


@pytest.fixture
def cache_root(tmp_path, monkeypatch):
    """Inject the storage root. The real one is the repo's `storage/`, and a test that wrote
    entity payloads into it would poison the running app's cache."""
    monkeypatch.setattr(entity_cache, "get_storage_root", lambda: tmp_path)
    return tmp_path / "cache"


def _entity(text: str = "a", handle: str = "1A") -> ExtractedEntity:
    # `model_validate`, not the constructor: Beanie's `Document.__init__` reaches for its
    # pymongo collection and raises without `init_beanie`. This is also the exact call the
    # cache makes when rehydrating, so the fixture and the code under test agree.
    return ExtractedEntity.model_validate(
        {"drawing_id": "d1", "job_id": "j1", "entity_type": "text", "layer": "0",
         "handle": handle, "properties": {"text": text}, "geometry": {}}
    )


class _Find:
    """Stands in for `ExtractedEntity.find(...)`, counting how often the network is reached."""

    def __init__(self, store): self.store = store
    def __call__(self, *_a, **_kw): return self
    async def to_list(self): self.store["fetches"] += 1; return list(self.store["docs"])
    async def count(self): self.store["counts"] += 1; return len(self.store["docs"])


@pytest.fixture
def db(monkeypatch):
    store = {"docs": [_entity("a"), _entity("b", "2B")], "fetches": 0, "counts": 0}
    monkeypatch.setattr(ExtractedEntity, "find", _Find(store))
    return store


# ── the point of the whole thing ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_cold_load_fetches_and_a_warm_load_does_not(cache_root, db):
    first = await entity_cache.load_entities("d1")
    assert db["fetches"] == 1

    second = await entity_cache.load_entities("d1")
    assert db["fetches"] == 1, "the second read must not reach the database"
    assert [e.handle for e in second] == [e.handle for e in first]
    assert [e.properties for e in second] == [e.properties for e in first]


@pytest.mark.asyncio
async def test_the_cached_entities_are_real_documents_not_dicts(cache_root, db):
    # Every consumer calls attributes (`e.entity_type`, `e.geometry`). Returning dicts would
    # fail at the call site rather than here, and only for the cached path.
    await entity_cache.load_entities("d1")
    assert all(isinstance(e, ExtractedEntity) for e in await entity_cache.load_entities("d1"))


# ── staleness, which is the whole risk ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_changed_entity_count_invalidates_the_cache(cache_root, db):
    """The safety net. Layers 1 and 2 (schema version in the key, explicit clears at the write
    sites) are the real mechanism; this catches a write site added later that forgets both."""
    await entity_cache.load_entities("d1")
    db["docs"].append(_entity("c", "3C"))

    again = await entity_cache.load_entities("d1")
    assert db["fetches"] == 2, "a count mismatch must refetch"
    assert len(again) == 3


@pytest.mark.asyncio
async def test_every_warm_read_pays_for_the_count_probe(cache_root, db):
    # Asserted so nobody "optimises" the probe away: without it the cache is only as correct as
    # the invalidation call sites, and one missed site is stale geometry forever.
    await entity_cache.load_entities("d1")
    await entity_cache.load_entities("d1")
    assert db["counts"] == 1


@pytest.mark.asyncio
async def test_the_schema_version_is_part_of_the_key(cache_root, db):
    """CLAUDE.md already requires bumping EXTRACTION_SCHEMA_VERSION when an extraction-time
    field is added, so putting it in the filename orphans every stale payload for free."""
    await entity_cache.load_entities("d1")
    assert list(cache_root.glob(f"entities_*_s{EXTRACTION_SCHEMA_VERSION}_d1.json"))


@pytest.mark.asyncio
async def test_clear_removes_entries_from_other_schema_versions_too(cache_root, db):
    await entity_cache.load_entities("d1")
    cache_root.mkdir(parents=True, exist_ok=True)
    (cache_root / "entities_v1_s2_d1.json").write_text("{}", encoding="utf-8")

    entity_cache.clear_for_drawing("d1")
    assert not list(cache_root.glob("entities_*_d1.json"))


@pytest.mark.asyncio
async def test_clear_leaves_other_drawings_alone(cache_root, db):
    await entity_cache.load_entities("d1")
    entity_cache.clear_for_drawing("d2")
    assert list(cache_root.glob("entities_*_d1.json"))


# ── refusing to cache, and refusing to fail ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_an_empty_result_is_not_cached(cache_root, db):
    """A drawing queried mid-extraction returns zero entities for a moment. Caching that would
    pin a *blank sheet* — which renders as a valid empty drawing, never as an error — and the
    count probe would agree with it right up until the insert lands."""
    db["docs"] = []
    assert await entity_cache.load_entities("d1") == []
    assert not list(cache_root.glob("entities_*_d1.json"))


@pytest.mark.asyncio
async def test_a_corrupt_cache_file_refetches_rather_than_raising(cache_root, db):
    await entity_cache.load_entities("d1")
    path = next(cache_root.glob("entities_*_d1.json"))
    path.write_text("{ this is not json", encoding="utf-8")

    assert len(await entity_cache.load_entities("d1")) == 2
    assert db["fetches"] == 2


@pytest.mark.asyncio
async def test_a_cache_file_missing_its_count_refetches(cache_root, db):
    # An older format, or a partial write that predates the atomic replace. `None == live_count`
    # is false, so this falls through to a refetch rather than trusting the docs it found.
    await entity_cache.load_entities("d1")
    path = next(cache_root.glob("entities_*_d1.json"))
    payload = json_util.loads(path.read_text(encoding="utf-8"))
    del payload["count"]
    path.write_text(json_util.dumps(payload), encoding="utf-8")

    assert len(await entity_cache.load_entities("d1")) == 2
    assert db["fetches"] == 2


@pytest.mark.asyncio
async def test_the_write_is_atomic(cache_root, db):
    # os.replace, so a reader never sees half a payload. A torn read deserializes as a drawing
    # with geometry missing, which looks like a drawing.
    await entity_cache.load_entities("d1")
    assert not list(cache_root.glob("*.tmp")), "no temp file may survive a successful write"
    payload = json.loads(json_util.dumps(
        json_util.loads(next(cache_root.glob("entities_*_d1.json")).read_text(encoding="utf-8"))
    ))
    assert payload["count"] == len(payload["docs"]) == 2
