"""The room list does not carry comparison results, and the room detail does.

Measured 2026-08-19 against the live cluster: `GET /rooms` returned 397.9 KB in 5.19 s for a
view that renders each room's name and status. The weight is `physical_comparison_results` — a
whole comparison checklist, every finding and every canvas marking, stored as a JSON string on
each Room. Projected out at the database the same call is 103 ms / 7.2 KB.

The reason this needs a test rather than a comment: a projected-away field arrives as `null`,
and `null` is exactly what a room that has never been compared reports. A future caller reading
it off the list would render "no findings" for a fully compared room and see no error anywhere.
So the split is pinned from both sides — the list must omit it, the detail must keep it.
"""

import ast
from pathlib import Path

ROUTER = Path(__file__).resolve().parents[1] / "services/backend/api/routers/rooms.py"


def _function(name: str) -> ast.FunctionDef:
    tree = ast.parse(ROUTER.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"{name} not found in rooms.py")


def _source(name: str) -> str:
    """The function's code with comments stripped.

    Not `ast.get_source_segment`, which returns the comments too. Every assertion in this
    file is a substring match against a handler, and with comments included both directions
    are wrong: `"room.set(" not in src` matched the comment *explaining why room.set() is not
    used* (that is how it first failed against correct code), and every positive assertion
    here could be satisfied by a comment mentioning the string while the code did nothing.

    `ast.unparse` drops comments. Quotes are normalised to double because it always emits
    single ones, so the assertions can be written the way the source spells them.
    """
    return ast.unparse(_function(name)).replace("'", '"')


def test_the_list_projects_the_comparison_payload_out():
    src = _source("list_rooms")
    assert '"physical_comparison_results": 0' in src, (
        "GET /rooms must project physical_comparison_results out. Without it the endpoint ships "
        "every room's full comparison checklist — 397.9 KB / 5.19 s measured 2026-08-19."
    )


def test_the_projection_happens_in_the_query_not_after_it():
    """Stripping the field after loading would keep every byte crossing the network, which is
    the entire cost — the serialization was never the problem. `projection=` must sit on the
    database call."""
    src = _source("list_rooms")
    assert "projection=" in src and ".find(" in src


def test_the_detail_endpoint_still_returns_the_payload():
    """The counterpart, and the reason this cannot simply be dropped everywhere: `openRoom`
    restores a room's canvas markers from `physical_comparison_results.canvas_markings`.

    This originally asserted `"projection" not in src`, which pinned the *mechanism* — "the
    detail endpoint fetches the whole document" — as a proxy for the behaviour. The detail
    endpoint now projects the field out of the fetch too and restores it from disk, so the
    proxy failed while the behaviour it stood for was intact. Rewritten to check what actually
    matters: the response carries the payload, and the miss path can still obtain it.
    """
    src = _source("get_room")
    assert "_to_response(room)" in src
    assert "room_results_cache.load(" in src, (
        "the payload must come from the cache module, not from a second ad-hoc query"
    )
    assert '"physical_comparison_results": 1' in src, (
        "a cache miss must refetch the field. Without this the endpoint would quietly return "
        "null for every room — indistinguishable from one that was never compared, which is "
        "the ambiguity this whole file exists to pin."
    )


def test_the_detail_endpoint_writes_only_the_timestamp():
    """`room.save()` rewrote the whole document — comparison payload included — to stamp
    `last_opened_at`.

    `room.set()` is now banned here too, and that is not a style preference. Beanie's
    `Document.update` issues `response_type=UpdateResponse.NEW_DOCUMENT` — a
    `find_one_and_update` returning the document AFTER the write — then merges it back into the
    instance. So the targeted `$set` sent one timestamp and pulled the entire 166 KB checklist
    *back*: 2.01 s of room 228's 4.53 s open, against 0.041 s for the raw `update_one`
    (measured 2026-08-19). Reverting to either ODM helper silently restores that cost, and
    nothing else in the suite would notice.
    """
    src = _source("get_room")
    assert "await room.save()" not in src, (
        "A full save here rewrites physical_comparison_results on every room open."
    )
    assert "room.set(" not in src, (
        "Beanie's set() returns the whole updated document — see this test's docstring."
    )
    assert "update_one(" in src and "last_opened_at" in src


def test_the_response_model_is_shared_by_both_endpoints():
    # Both return RoomResponse. If they ever diverge into two shapes, the null-vs-absent
    # ambiguity this file exists to pin would become a type-level difference instead — which
    # would be an improvement, and this test should then be rewritten rather than deleted.
    text = ROUTER.read_text(encoding="utf-8")
    assert "StandardResponse[list[RoomResponse]]" in text
    assert "StandardResponse[RoomResponse]" in text


def test_the_list_still_sorts_newest_first():
    """Pinned here because nothing else pins it any more.

    `test_rooms.py::test_list_sorted_by_updated_at_descending` does not call `list_rooms` — it
    re-states the query inline and asserts against the mock, so it passes whatever the endpoint
    does. That was already true before this change; moving the query from Beanie's
    `.sort(-Room.updated_at)` to pymongo's `.sort("updated_at", -1)` is what made it matter,
    because the two spellings could now disagree with nothing failing.
    """
    src = _source("list_rooms")
    assert '"updated_at", -1' in src, "the room list must stay newest-first"


def test_the_soft_delete_filter_survived_the_rewrite():
    """`Room.is_deleted == False` became a raw `{"is_deleted": False}`. Getting this wrong
    would list deleted rooms — visible, but only to someone who had deleted one."""
    src = _source("list_rooms")
    assert '"is_deleted": False' in src
