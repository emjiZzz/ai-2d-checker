"""The repair tool's grouping, which decides where an engineer's markings end up.

No database: `_plan` is pure so the two decisions that matter — what counts as the same check,
and which of several sessions survives — are checkable without one.

The stakes are not "the script is tidy". If this groups differently from
`api/routers/ground_truth.create_session`, the merge consolidates markings onto a session the
app will never ask for, and the empty panel the tool exists to fix stays empty with the data now
in a third place. That agreement is pinned in `test_ground_truth_submission.py`.
"""

from datetime import UTC, datetime, timedelta

from tools.merge_duplicate_check_sessions import GROUP_KEYS, _plan

T0 = datetime(2026, 8, 18, 9, 0, tzinfo=UTC)


def _session(sid, *, started, status="in_progress", annotator="imrysn", room="room1",
             ref="ref1", rev="rev1", notes=""):
    return {
        "_id": sid,
        "room_id": room,
        "ref_drawing_id": ref,
        "rev_drawing_id": rev,
        "annotator": annotator,
        "status": status,
        "started_at": started,
        "notes": notes,
    }


def test_the_oldest_open_session_is_the_one_kept():
    """It must be the same one the endpoint resumes, which sorts `started_at` ascending.

    Keeping the newest would look equally reasonable and be wrong in the direction that is hard
    to notice: the merge would report success, and the next reload would resume the *oldest*
    session — now empty, because everything was just moved off it.
    """
    sessions = [
        _session("newest", started=T0 + timedelta(minutes=5)),
        _session("oldest", started=T0),
        _session("middle", started=T0 + timedelta(minutes=2)),
    ]
    plans = _plan(sessions, {"newest": 4, "middle": 1, "oldest": 0})

    assert len(plans) == 1
    assert plans[0]["canonical"]["_id"] == "oldest"
    assert {d["session"]["_id"] for d in plans[0]["drained"]} == {"middle", "newest"}
    assert sum(d["markings"] for d in plans[0]["drained"]) == 5


def test_a_submitted_session_is_never_touched():
    """A submitted session is a finished pass, and a human statement about it.

    Draining one destroys that record; growing one rewrites it. Either way the collection stops
    being an audit trail, which is the only reason to collect it.
    """
    sessions = [
        _session("done", started=T0, status="submitted"),
        _session("open", started=T0 + timedelta(minutes=1)),
    ]
    assert _plan(sessions, {"done": 9, "open": 2}) == []


def test_a_different_annotator_is_a_different_check():
    # Two engineers over the same drawings are two passes. Merging them would attribute one
    # person's judgements to the other's session and destroy what a session means.
    sessions = [
        _session("a", started=T0, annotator="imrysn"),
        _session("b", started=T0 + timedelta(minutes=1), annotator="tsuda"),
    ]
    assert _plan(sessions, {}) == []


def test_a_different_drawing_pair_is_a_different_check():
    # A room's drawings can be swapped, so the room alone does not identify the check.
    sessions = [
        _session("a", started=T0, rev="rev1"),
        _session("b", started=T0 + timedelta(minutes=1), rev="rev2"),
    ]
    assert _plan(sessions, {}) == []


def test_a_lone_session_is_not_a_duplicate():
    assert _plan([_session("only", started=T0)], {"only": 3}) == []


def test_sessions_opened_in_the_same_instant_still_order_deterministically():
    """A fast double-mount can open two sessions with the same `started_at`.

    Without the id tiebreak the survivor would depend on the order Mongo happened to return, so
    two runs of this tool could disagree about which session is canonical — and the second run
    would move everything back.
    """
    sessions = [_session("b2", started=T0), _session("a1", started=T0)]
    first = _plan(sessions, {})
    second = _plan(list(reversed(sessions)), {})

    assert first[0]["canonical"]["_id"] == "a1"
    assert second[0]["canonical"]["_id"] == "a1"


def test_notes_on_a_drained_session_are_surfaced_rather_than_merged():
    """There is no rule for whose prose wins, so the tool refuses to invent one.

    The flag is what stops `--delete-drained` removing a session carrying an engineer's only
    written account of the pair.
    """
    sessions = [
        _session("keep", started=T0),
        _session("drop", started=T0 + timedelta(minutes=1), notes="  checked against ISO copy  "),
    ]
    drained = _plan(sessions, {})[0]["drained"]
    assert drained[0]["notes"] == "checked against ISO copy"


def test_the_group_keys_are_the_identity_of_a_check():
    # Restated here so a silent widening — dropping `annotator`, say — fails a test that says
    # what it costs, not just a diff.
    assert GROUP_KEYS == ("room_id", "ref_drawing_id", "rev_drawing_id", "annotator")
