"""What the room-results cache serves, and the structural assumption it rests on.

`GET /rooms/{id}` costs 4.53 s for the largest live room and ~0.09 s from disk (measured
2026-08-19; see `room_results_cache`'s module docstring). So the cache is hit on essentially
every room open, and the tests that matter are about the *key*: the payload is a comparison
checklist, and a stale one renders as a plausible set of findings rather than as an error.

Unlike the entity cache there is no live-count net to fall back on — the key is the whole
guarantee — so `test_a_persisted_results_change_must_bump_updated_at` is the load-bearing
test in this file. It parses the router rather than exercising it, because what it pins is an
invariant about code that does not exist yet: the *next* writer of that field.
"""

import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from services.backend.infrastructure.storage import room_results_cache

ROOMS_ROUTER = (
    Path(__file__).resolve().parents[1] / "services" / "backend" / "api" / "routers" / "rooms.py"
)
FIELD = "physical_comparison_results"


@pytest.fixture
def cache_root(tmp_path, monkeypatch):
    """Inject the storage root. The real one is the repo's `storage/`, and a test that wrote
    results payloads into it would poison the running app's cache."""
    monkeypatch.setattr(room_results_cache, "get_storage_root", lambda: tmp_path)
    return tmp_path / "cache"


# --------------------------------------------------------------------------------------
# The structural invariant
# --------------------------------------------------------------------------------------

def _functions(tree):
    return [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]


def _assigned_attributes(fn):
    names = set()
    for node in ast.walk(fn):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Attribute):
                    names.add(target.attr)
    return names


def _calls_method(fn, method):
    return any(
        isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == method
        for n in ast.walk(fn)
    )


def test_a_persisted_results_change_must_bump_updated_at():
    """The cache key is `(room_id, updated_at)`, so persisting new results without touching
    `updated_at` would leave every reader serving the previous checklist — indefinitely, and
    without any symptom other than wrong findings.

    Pinned structurally rather than behaviourally: the risk is a *future* second writer, and a
    behavioural test can only cover the writer that already exists.
    """
    tree = ast.parse(ROOMS_ROUTER.read_text(encoding="utf-8"))
    offenders = [
        fn.name
        for fn in _functions(tree)
        if FIELD in _assigned_attributes(fn)
        and _calls_method(fn, "save")
        and "updated_at" not in _assigned_attributes(fn)
    ]
    assert not offenders, (
        f"{offenders} persist {FIELD} via .save() without assigning updated_at. "
        "The room results cache is keyed on updated_at; see room_results_cache.py."
    )


def test_results_are_never_persisted_through_a_targeted_update():
    """`update_one({'$set': {...}})` bypasses the `updated_at` assignment that `.save()` sites
    are checked for above, so the field must never appear in one. `get_room` uses exactly such
    an update for `last_opened_at` — deliberately, so that opening a room does not invalidate
    that room's own entry — which is what makes this the plausible next mistake.
    """
    source = ROOMS_ROUTER.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        if node.func.attr not in {"update_one", "update_many", "find_one_and_update", "set"}:
            continue
        rendered = ast.dump(node)
        assert FIELD not in rendered, (
            f"{node.func.attr}() at line {node.lineno} persists {FIELD} without going through "
            "the updated_at bump that the cache key depends on."
        )


def test_the_router_reads_results_through_the_cache_module():
    """A second read path that queried the field directly would be correct but slow, and the
    slowness is invisible — it just restores the 2 s that this module removed."""
    # Unparsed, not raw text: a comment mentioning the projection would otherwise satisfy this
    # while the query still dragged the field across. See test_room_list_projection._source.
    code = ast.unparse(ast.parse(ROOMS_ROUTER.read_text(encoding="utf-8"))).replace("'", '"')
    assert "room_results_cache" in code
    assert f'projection={{"{FIELD}": 0}}' in code, (
        "get_room must fetch the room without the heavy field; that projection is the fix."
    )


# --------------------------------------------------------------------------------------
# Round-trip behaviour
# --------------------------------------------------------------------------------------

STAMP = datetime(2026, 8, 16, 23, 40, 25, 239000)


def test_stores_and_serves_the_payload_verbatim(cache_root):
    payload = '{"findings": [{"id": "a"}]}'
    room_results_cache.store("r1", STAMP, payload)
    assert room_results_cache.load("r1", STAMP) == payload


def test_a_different_updated_at_is_a_miss(cache_root):
    room_results_cache.store("r1", STAMP, '{"findings": []}')
    assert room_results_cache.load("r1", STAMP + timedelta(milliseconds=1)) is False


def test_never_stored_is_a_miss(cache_root):
    assert room_results_cache.load("nobody", STAMP) is False


def test_a_room_with_no_results_is_cached_as_none_not_as_a_miss(cache_root):
    """`None` and "not cached" are different answers. Collapsing them would refetch the whole
    document on every open of a room that has never been compared."""
    room_results_cache.store("r1", STAMP, None)
    assert room_results_cache.load("r1", STAMP) is None


def test_the_key_survives_the_timezone_round_trip(cache_root):
    """PATCH stores an aware UTC datetime; the same value read back from Mongo is naive UTC.
    Both must produce one key, or every save is followed by a guaranteed miss on the reopen."""
    aware = STAMP.replace(tzinfo=timezone.utc)
    room_results_cache.store("r1", aware, '{"findings": []}')
    assert room_results_cache.load("r1", STAMP) == '{"findings": []}'


def test_clear_for_room_drops_every_stamp_and_leaves_other_rooms_alone(cache_root):
    room_results_cache.store("r1", STAMP, "a")
    room_results_cache.store("r1", STAMP + timedelta(seconds=5), "b")
    room_results_cache.store("r2", STAMP, "c")
    room_results_cache.clear_for_room("r1")
    assert room_results_cache.load("r1", STAMP) is False
    assert room_results_cache.load("r1", STAMP + timedelta(seconds=5)) is False
    assert room_results_cache.load("r2", STAMP) == "c"


def test_an_unreadable_entry_is_a_miss_not_an_error(cache_root):
    """A bad cache file must never fail a request — it must degrade to the live fetch."""
    room_results_cache.store("r1", STAMP, "a")
    path = next(cache_root.glob("room_pcr_*_r1_*.json"))
    path.unlink()
    path.mkdir()  # a directory where a file is expected: read_text raises OSError
    assert room_results_cache.load("r1", STAMP) is False
