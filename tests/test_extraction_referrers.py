"""What still points at a drawing, which is what `--referenced-only` re-extracts.

The rule is cheap to get subtly wrong in two ways, and both fail silently: a soft-deleted
room's drawing ids are expected to dangle, so counting them keeps rows current that nobody
can open; and a marking names its drawing under the address rather than at the top level, so
the obvious query returns nothing and reads as "no marking references any drawing".
"""

from tools.extraction_status import REFERRER_SOURCES, referenced_ids


class _Collection:
    def __init__(self, docs):
        self._docs = docs

    def find(self, query=None, projection=None):
        for doc in self._docs:
            # The only query this module issues is `is_deleted: {"$ne": True}`.
            if query and "is_deleted" in query and doc.get("is_deleted") is True:
                continue
            yield doc


class _DB:
    def __init__(self, **collections):
        self._collections = collections

    def __getitem__(self, name):
        return _Collection(self._collections.get(name, []))


def test_a_live_room_references_both_of_its_drawings():
    db = _DB(rooms=[{"active_old_drawing_id": "ref1", "active_new_drawing_id": "rev1"}])
    assert referenced_ids(db) == {"ref1": {"rooms"}, "rev1": {"rooms"}}


def test_a_soft_deleted_rooms_drawings_are_not_referenced():
    """Deleting a room purges both slots and keeps the Room, so its ids dangle by design."""
    db = _DB(rooms=[
        {"active_old_drawing_id": "gone", "active_new_drawing_id": "gone2", "is_deleted": True},
        {"active_old_drawing_id": "kept", "is_deleted": False},
    ])
    assert referenced_ids(db) == {"kept": {"rooms"}}


def test_a_marking_is_found_through_its_address_not_at_the_top_level():
    db = _DB(ground_truth_markings=[
        {"ref_address": {"drawing_id": "ref1"}, "rev_address": {"drawing_id": "rev1"}},
        {"ref_address": None, "rev_address": {"drawing_id": "rev1"}},
    ])
    assert referenced_ids(db) == {
        "ref1": {"ground_truth_markings"},
        "rev1": {"ground_truth_markings"},
    }


def test_every_referrer_is_reported_by_name():
    """A drawing several things point at names all of them, so a report can say why it stayed."""
    db = _DB(
        rooms=[{"active_old_drawing_id": "d"}],
        audit_sessions=[{"drawing_id": "d"}],
        audit_feedback=[{"drawing_id": "d"}],
    )
    assert referenced_ids(db)["d"] == {"rooms", "audit_sessions", "audit_feedback"}


def test_absent_and_empty_fields_reference_nothing():
    db = _DB(
        rooms=[{"active_old_drawing_id": None, "active_new_drawing_id": ""}, {}],
        audit_sessions=[{"reference_drawing_id": None}],
    )
    assert referenced_ids(db) == {}


def test_an_id_naming_a_deleted_row_is_still_returned():
    """Callers intersect against `collect`'s rows; this must not quietly decide for them."""
    db = _DB(audit_sessions=[{"drawing_id": "no-such-row"}])
    assert referenced_ids(db) == {"no-such-row": {"audit_sessions"}}


def test_the_two_soft_deletable_sources_are_the_two_that_carry_the_flag():
    """`rooms` and `audit_sessions` have `is_deleted`; nothing else in the tuple does, and a
    source marked filterable that lacks the field would silently return no rows at all."""
    filtered = {name for name, _fields, flag in REFERRER_SOURCES if flag}
    assert filtered == {"rooms", "audit_sessions"}
