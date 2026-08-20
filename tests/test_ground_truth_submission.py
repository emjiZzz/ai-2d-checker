"""The ground-truth router's contract: what it refuses, and what it never destroys.

DB access is fully mocked (same approach as `test_zone_templates_router.py`), so this runs
offline. The handlers are called directly rather than through a TestClient — the questions here
are about the rules, not about routing.

Two of these tests exist because of specific prior defects in this repo rather than from
general caution, and they say so where they sit.
"""

from datetime import UTC, datetime
from typing import get_args
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from services.backend.api.routers import ground_truth as gt
from services.backend.domain.models.ground_truth import (
    EntityAddress,
    GroundTruthMarking,
    ManualCheckSession,
)
from services.backend.infrastructure.audit.comparison.taxonomy import Category

# `asyncio_mode = "auto"` in pyproject.toml collects async tests without a marker, so a
# module-level `pytest.mark.asyncio` would only warn on the sync tests here.


def _address(handle="1B2A", drawing_id="drw1", text="60"):
    return gt.EntityAddressPayload(
        drawing_id=drawing_id,
        handle=handle,
        entity_type="text",
        layer="0",
        text=text,
        coordinates=[10.0, 20.0],
    )


def _session():
    return ManualCheckSession(
        room_id="room1",
        ref_drawing_id="ref1",
        rev_drawing_id="rev1",
        annotator="imrysn",
    )


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    """No database, no drawing lookups. Every write is captured instead of performed.

    Beanie's `Document.__init__` reaches for its collection, so that has to be stubbed before
    any document is constructed -- same pattern as `test_zone_templates_router.py`.
    """
    for model in (gt.ManualCheckSession, gt.GroundTruthMarking):
        monkeypatch.setattr(
            model, "get_pymongo_collection", classmethod(lambda cls: MagicMock()), raising=False
        )
    monkeypatch.setattr(gt.ManualCheckSession, "save", AsyncMock(), raising=False)
    monkeypatch.setattr(gt.GroundTruthMarking, "save", AsyncMock(), raising=False)
    monkeypatch.setattr(gt.DrawingDocument, "get", AsyncMock(return_value=None), raising=False)
    monkeypatch.setattr(gt, "_recount", AsyncMock())
    monkeypatch.setattr(gt, "get_or_404", AsyncMock(return_value=_session()))


# ── the category must come from the taxonomy, not from here ──────────────────────────


def test_valid_categories_is_read_off_the_taxonomy_not_restated():
    """A hand-copied category list would drift, and the drift would be invisible.

    `GroundTruthMarking.category` is a plain `str` because `domain/` may not import
    `infrastructure/` (`tests/test_layer_boundaries.py`). That makes this router the only place
    the real check happens — so it has to read `taxonomy.Category` itself. A marking filed under
    a category the engine has never heard of is not a corrupt row, it is an *invisible* one:
    every downstream group-by silently drops it.
    """
    assert gt.VALID_CATEGORIES == frozenset(get_args(Category))
    assert len(gt.VALID_CATEGORIES) == 6


async def test_an_invented_category_is_refused():
    with pytest.raises(HTTPException) as exc:
        await gt.create_marking(
            "sess1",
            gt.CreateMarkingRequest(
                status="ADDED", category="Manual Marker", rev_address=_address()
            ),
        )
    assert exc.value.status_code == 422
    assert "taxonomy" in str(exc.value.detail)


@pytest.mark.parametrize("category", sorted(get_args(Category)))
async def test_every_real_category_is_accepted(category):
    result = await gt.create_marking(
        "sess1",
        gt.CreateMarkingRequest(status="ADDED", category=category, rev_address=_address()),
    )
    assert result.success
    assert result.data.category == category


# ── a marking with no subject is refused ─────────────────────────────────────────────


async def test_a_marking_addressing_no_entity_is_refused():
    """The failure this whole feature exists not to repeat.

    The marker already shipping in the product (`CanvasContextMenu` -> `custom_marker_*`)
    records `category: 'Manual Marker'`, `affected_entities: []` and a bare coordinate. It says
    a human pointed at a place and nothing about what they saw there, which is exactly why
    nothing can learn from it — `build_feature_row`'s primary feature is `text_combined`, and
    with no entity there is no text.

    Storing that shape here would fill the dataset with rows that look like data and are not.
    """
    with pytest.raises(HTTPException) as exc:
        await gt.create_marking(
            "sess1", gt.CreateMarkingRequest(status="MATCHED", category="drawing_views")
        )
    assert exc.value.status_code == 422
    assert "must address at least one entity" in str(exc.value.detail)


# ── side is derived from the addresses, never trusted from the client ────────────────


@pytest.mark.parametrize(
    "ref, rev, expected",
    [
        (True, True, "both"),
        (True, False, "ref"),
        (False, True, "rev"),
    ],
)
async def test_side_is_derived_from_which_addresses_exist(ref, rev, expected):
    result = await gt.create_marking(
        "sess1",
        gt.CreateMarkingRequest(
            status="CHANGED" if ref and rev else "ADDED",
            category="drawing_views",
            ref_address=_address(handle="REF1") if ref else None,
            rev_address=_address(handle="REV1") if rev else None,
        ),
    )
    assert result.data.side == expected


async def test_a_changed_pair_keeps_both_coordinates_separately():
    """The degenerate mirror must not be inherited.

    `CanvasContextMenu` sets `coordinates` and `ref_coordinates` to the *same* point from one
    click, which is correct only where the two sheets share a coordinate frame and meaningless
    on a re-traced revision. A CHANGED marking comes from two clicks and must keep both.
    """
    ref = gt.EntityAddressPayload(
        drawing_id="ref1", entity_type="text", text="20", coordinates=[1.0, 2.0]
    )
    rev = gt.EntityAddressPayload(
        drawing_id="rev1", entity_type="text", text="25", coordinates=[900.0, 800.0]
    )
    result = await gt.create_marking(
        "sess1",
        gt.CreateMarkingRequest(
            status="CHANGED",
            category="drawing_views",
            ref_address=ref,
            rev_address=rev,
            ref_text="20",
            rev_text="25",
        ),
    )
    assert result.data.ref_coordinates == [1.0, 2.0]
    assert result.data.rev_coordinates == [900.0, 800.0]
    assert result.data.ref_coordinates != result.data.rev_coordinates


# ── retraction marks; it never deletes ───────────────────────────────────────────────


async def test_retraction_marks_rather_than_deletes(monkeypatch):
    """This collection is both the dataset and the record of who asserted what.

    A row that silently vanishes is unauditable, and the retraction is itself information: it
    says a human changed their mind, which a later consumer may want to weigh differently from a
    decision that was never made. Same reasoning as `AuditFeedbackDocument.retracted_at`.
    """
    marking = GroundTruthMarking(
        session_id="sess1",
        side="rev",
        rev_address=EntityAddress(drawing_id="drw1", entity_type="text", text="60"),
        status="ADDED",
        category="drawing_views",
        annotator="imrysn",
    )
    delete = AsyncMock()
    monkeypatch.setattr(gt.GroundTruthMarking, "delete", delete, raising=False)
    monkeypatch.setattr(gt, "get_or_404", AsyncMock(return_value=marking))
    monkeypatch.setattr(gt.ManualCheckSession, "get", AsyncMock(return_value=None), raising=False)

    result = await gt.retract_marking("m1")

    assert result.data.retracted_at is not None
    assert marking.retracted_at is not None
    delete.assert_not_awaited()


async def test_retracting_twice_keeps_the_first_timestamp(monkeypatch):
    """Idempotent. A double-click must not rewrite when the engineer changed their mind."""
    first = datetime(2026, 8, 1, tzinfo=UTC)
    marking = GroundTruthMarking(
        session_id="sess1",
        side="rev",
        rev_address=EntityAddress(drawing_id="drw1", entity_type="text"),
        status="ADDED",
        category="drawing_views",
        annotator="imrysn",
        retracted_at=first,
    )
    monkeypatch.setattr(gt, "get_or_404", AsyncMock(return_value=marking))

    result = await gt.retract_marking("m1")
    assert result.data.retracted_at == first


# ── an address is not editable ───────────────────────────────────────────────────────


def test_update_cannot_change_which_entity_a_marking_describes():
    """`UpdateMarkingRequest` deliberately has no address field.

    Editing an address in place would convert a marking into a statement about an entity the
    annotator never looked at, while leaving every timestamp and author field intact. There
    would be no trace. Re-stamping is the supported path.
    """
    fields = set(gt.UpdateMarkingRequest.model_fields)
    assert not fields & {"ref_address", "rev_address", "side"}
    assert "category" in fields and "status" in fields


async def test_update_only_writes_the_fields_that_were_sent(monkeypatch):
    marking = GroundTruthMarking(
        session_id="sess1",
        side="rev",
        rev_address=EntityAddress(drawing_id="drw1", entity_type="text"),
        status="ADDED",
        category="drawing_views",
        notes="original reasoning",
        annotator="imrysn",
    )
    monkeypatch.setattr(gt, "get_or_404", AsyncMock(return_value=marking))

    await gt.update_marking("m1", gt.UpdateMarkingRequest(category="notes_section"))

    assert marking.category == "notes_section"
    assert marking.notes == "original reasoning", "unsent fields must be left alone"
    assert marking.status == "ADDED"


# ── submit finalises; it is not when the data first exists ───────────────────────────


async def test_submit_finalises_a_session_that_already_holds_its_markings(monkeypatch):
    """Markings are saved as they are stamped, so submit is a status change, not a write.

    A submit-shaped API loses an hour of work to one crash — `M745230A01` carries 68
    addressable rows — and an annotator who has lost an hour does not come back.
    """
    session = _session()
    monkeypatch.setattr(gt, "get_or_404", AsyncMock(return_value=session))

    result = await gt.submit_session("sess1")

    assert result.data.status == "submitted"
    assert session.submitted_at is not None
    gt._recount.assert_awaited()


async def test_markings_persist_before_submit_is_ever_called():
    """The incremental guarantee, stated as a test rather than as a comment."""
    await gt.create_marking(
        "sess1",
        gt.CreateMarkingRequest(status="ADDED", category="notes_section", rev_address=_address()),
    )
    gt.GroundTruthMarking.save.assert_awaited()


# ── reopening a pair must resume, not restart ────────────────────────────────────────


def _open_request(room="room1", ref="ref1", rev="rev1"):
    return gt.CreateSessionRequest(room_id=room, ref_drawing_id=ref, rev_drawing_id=rev)


async def test_reopening_a_pair_resumes_the_session_already_in_progress(monkeypatch):
    """The defect the owner hit: markings vanished from the panel after every app reload.

    The client opens a session whenever the manual-check workspace mounts, and this handler
    unconditionally inserted a new one. So each reload minted an empty session, the UI listed
    *its* markings -- none -- and the engineer's work sat orphaned under the previous id. Nothing
    errored and nothing was deleted; the only symptom was an empty panel.
    """
    existing = _session()
    existing.marking_count = 3
    monkeypatch.setattr(
        gt.ManualCheckSession, "find_one", AsyncMock(return_value=existing), raising=False
    )
    monkeypatch.setattr(gt, "resolve_username", lambda _t: "imrysn")

    result = await gt.create_session(_open_request())

    assert result.success
    assert result.data.marking_count == 3
    gt.ManualCheckSession.save.assert_not_awaited()


async def test_a_pair_with_nothing_open_starts_a_new_session(monkeypatch):
    monkeypatch.setattr(
        gt.ManualCheckSession, "find_one", AsyncMock(return_value=None), raising=False
    )
    monkeypatch.setattr(gt, "resolve_username", lambda _t: "imrysn")

    result = await gt.create_session(_open_request())

    assert result.success
    assert result.data.annotator == "imrysn"
    assert result.data.marking_count == 0
    gt.ManualCheckSession.save.assert_awaited_once()


async def test_the_resume_is_scoped_to_pair_annotator_and_open_status(monkeypatch):
    """Each clause of the filter is load-bearing, and dropping one is silent.

    Without `status`, reopening a room would append to a session already submitted, so a
    finished pass would keep growing. Without `annotator`, a second engineer would inherit the
    first's partial work and the session would stop meaning "who checked this pair". Without the
    two drawing ids, swapping a room's drawings would resume a check of the previous pair.
    """
    find_one = AsyncMock(return_value=None)
    monkeypatch.setattr(gt.ManualCheckSession, "find_one", find_one, raising=False)
    monkeypatch.setattr(gt, "resolve_username", lambda _t: "imrysn")

    await gt.create_session(_open_request())

    query = find_one.await_args.args[0]
    assert query == {
        "room_id": "room1",
        "ref_drawing_id": "ref1",
        "rev_drawing_id": "rev1",
        "annotator": "imrysn",
        "status": "in_progress",
    }


async def test_the_resume_query_names_only_real_session_fields(monkeypatch):
    """A raw query dict has no field-name checking, and a typo fails in the quiet direction.

    `{"anotator": ...}` matches no document, so every open would mint a new session and the
    empty-panel defect would be back with nothing to show for it — no error, no log, just an
    engineer's markings orphaned again.
    """
    find_one = AsyncMock(return_value=None)
    monkeypatch.setattr(gt.ManualCheckSession, "find_one", find_one, raising=False)
    monkeypatch.setattr(gt, "resolve_username", lambda _t: "imrysn")

    await gt.create_session(_open_request())

    assert set(find_one.await_args.args[0]) <= set(ManualCheckSession.model_fields)


async def test_an_unidentified_caller_does_not_inherit_another_engineers_session(monkeypatch):
    """`resolve_username` returning None falls back to "unknown", which is a real annotator key.

    It has to be passed to the lookup like any other, or every unauthenticated open would share
    one session — and the markings inside it would carry no usable attribution.
    """
    find_one = AsyncMock(return_value=None)
    monkeypatch.setattr(gt.ManualCheckSession, "find_one", find_one, raising=False)
    monkeypatch.setattr(gt, "resolve_username", lambda _t: None)

    result = await gt.create_session(_open_request())

    assert result.data.annotator == "unknown"
    assert find_one.await_args.args[0]["annotator"] == "unknown"


async def test_the_repair_tool_groups_sessions_the_same_way_this_endpoint_resumes(monkeypatch):
    """`tools/merge_duplicate_check_sessions.py` consolidates onto the session this resumes.

    If the two ever disagree about what identifies a check, the repair moves an engineer's
    markings onto a session this endpoint will never ask for — and the empty-panel defect it was
    written to fix survives the fix, with the data now in a third place. Neither side can catch
    that alone, so the agreement is asserted here where the real query is observable.
    """
    from tools.merge_duplicate_check_sessions import GROUP_KEYS

    find_one = AsyncMock(return_value=None)
    monkeypatch.setattr(gt.ManualCheckSession, "find_one", find_one, raising=False)
    monkeypatch.setattr(gt, "resolve_username", lambda _t: "imrysn")

    await gt.create_session(_open_request())

    assert set(find_one.await_args.args[0]) == set(GROUP_KEYS) | {"status"}


# ── where a category came from is part of the record ─────────────────────────────────


async def test_a_category_the_engineer_chose_is_recorded_as_theirs():
    """The default has to be `human`, because every row written before this field existed was.

    A default of `zone` would retroactively relabel the entire corpus as derived, which is the
    one thing that cannot be undone by inspection: nothing in an old row says who chose it.
    """
    result = await gt.create_marking(
        "sess1",
        gt.CreateMarkingRequest(status="ADDED", category="drawing_views", rev_address=_address()),
    )
    assert result.data.category_source == "human"


async def test_a_category_taken_from_the_zone_says_so():
    """The reason this field exists at all.

    The mutation corpus's attribution figure is a known tautology — its labels come from
    `zone_detector`, and moving the zone boxes shifted attribution 0.81 → 0.74 with no engine
    change. The human pairs were the first attribution numbers that were not tautologies. That
    survives derivation only if an evaluator can tell the two kinds of row apart.
    """
    result = await gt.create_marking(
        "sess1",
        gt.CreateMarkingRequest(
            status="MATCHED",
            category="bill_of_materials",
            category_source="zone",
            rev_address=_address(),
        ),
    )
    assert result.data.category_source == "zone"


async def test_an_invented_category_source_is_refused():
    # A free-form string would let a third value appear and be counted as neither, quietly
    # shrinking whichever set an evaluator filtered for.
    with pytest.raises(ValidationError):
        gt.CreateMarkingRequest(
            status="MATCHED",
            category="drawing_views",
            category_source="guessed",
            rev_address=_address(),
        )


# ── a submitted session is a record, not a container ─────────────────────────────────
#
# Added 2026-08-20 with the readiness review. None of the four rules below held before it, and
# each one changes what a corpus label was derived from AFTER the derivation — which is the
# expensive shape here, because nothing downstream can see it happen.


def _submitted_session():
    session = _session()
    session.status = "submitted"
    session.submitted_at = datetime(2026, 8, 19, 12, 0, tzinfo=UTC)
    return session


async def test_a_submitted_session_refuses_a_new_marking(monkeypatch):
    """`submit` is the moment a pass becomes the thing `from-manual-check` converts.

    Appending afterwards rewrites the record a label was taken from. `create_session` mints a
    fresh session for a genuinely new pass, so refusing here blocks nothing legitimate.
    """
    monkeypatch.setattr(gt, "get_or_404", AsyncMock(return_value=_submitted_session()))

    with pytest.raises(HTTPException) as err:
        await gt.create_marking(
            "sess1",
            gt.CreateMarkingRequest(
                status="ADDED", category="drawing_views", rev_address=_address()
            ),
        )

    assert err.value.status_code == 409
    assert "closed" in err.value.detail


async def test_a_submitted_session_refuses_an_edit_to_its_markings(monkeypatch):
    marking = GroundTruthMarking(
        session_id="sess1",
        side="rev",
        rev_address=EntityAddress(drawing_id="rev1", handle="1B2A", entity_type="text"),
        status="ADDED",
        category="drawing_views",
        annotator="imrysn",
    )
    monkeypatch.setattr(gt, "get_or_404", AsyncMock(return_value=marking))
    monkeypatch.setattr(gt, "_session_of", AsyncMock(return_value=_submitted_session()))

    with pytest.raises(HTTPException) as err:
        await gt.update_marking("m1", gt.UpdateMarkingRequest(category="notes_section"))

    assert err.value.status_code == 409


async def test_submitting_twice_keeps_the_first_timestamp(monkeypatch):
    """Same rule as `retract_marking`, for the same reason.

    `submitted_at` is a claim about when an engineer finished. A double click, or a retry after a
    timeout that had actually succeeded, would move it to the moment of the retry — and re-run
    `_recount` over a session an export may already have been taken from.
    """
    session = _submitted_session()
    first = session.submitted_at
    monkeypatch.setattr(gt, "get_or_404", AsyncMock(return_value=session))
    recount = AsyncMock()
    monkeypatch.setattr(gt, "_recount", recount)

    result = await gt.submit_session("sess1")

    assert result.data.submitted_at == first
    recount.assert_not_awaited()


async def test_an_open_session_still_submits(monkeypatch):
    # The guard above must not make submit itself a no-op.
    session = _session()
    monkeypatch.setattr(gt, "get_or_404", AsyncMock(return_value=session))

    result = await gt.submit_session("sess1")

    assert result.data.status == "submitted"
    assert result.data.submitted_at is not None


# ── the session-open race ────────────────────────────────────────────────────────────


async def test_a_racing_open_resumes_the_session_that_won(monkeypatch):
    """The partial unique index turns a silent duplicate into a `DuplicateKeyError`.

    Before the index there was nothing between the resume query's miss and the insert, so two
    clients that both missed both inserted — visible in the collection as sessions in PAIRS,
    milliseconds apart, which is what `tools/merge_duplicate_check_sessions.py` was written to
    clean up. The only correct answer to losing that race is to read the session that won, which
    is what the caller asked for to begin with.
    """
    winner = _session()
    winner.marking_count = 4
    # Misses first (so the insert is attempted), then finds the winner on the retry.
    find_one = AsyncMock(side_effect=[None, winner])
    monkeypatch.setattr(gt.ManualCheckSession, "find_one", find_one, raising=False)
    monkeypatch.setattr(
        gt.ManualCheckSession,
        "save",
        AsyncMock(side_effect=gt.DuplicateKeyError("dup")),
        raising=False,
    )
    monkeypatch.setattr(gt, "resolve_username", lambda _t: "imrysn")

    result = await gt.create_session(_open_request())

    assert result.data.marking_count == 4
    assert find_one.await_count == 2


async def test_a_race_that_leaves_nothing_open_is_reported_not_guessed(monkeypatch):
    # The index rejected the insert but nothing in-progress is there to read. Retrying would
    # loop, and inventing a session would attach an engineer's work to the wrong record.
    monkeypatch.setattr(
        gt.ManualCheckSession, "find_one", AsyncMock(return_value=None), raising=False
    )
    monkeypatch.setattr(
        gt.ManualCheckSession,
        "save",
        AsyncMock(side_effect=gt.DuplicateKeyError("dup")),
        raising=False,
    )
    monkeypatch.setattr(gt, "resolve_username", lambda _t: "imrysn")

    with pytest.raises(HTTPException) as err:
        await gt.create_session(_open_request())

    assert err.value.status_code == 409


# ── a malformed stored session id must not 500 ───────────────────────────────────────


async def test_a_marking_naming_an_unloadable_session_still_retracts(monkeypatch):
    """`session_id` is a plain string, so nothing guarantees it parses as an ObjectId.

    `retract_marking` called `ManualCheckSession.get()` directly, which is exactly the failure
    `get_or_404` exists to stop — documented at length in `api/dependencies.py` and then
    reintroduced here. The caller is acting on the MARKING, which exists; an unloadable session
    must not fail the retraction of a row that is right there.
    """
    marking = GroundTruthMarking(
        session_id="not-an-object-id",
        side="rev",
        rev_address=EntityAddress(drawing_id="rev1", handle="1B2A", entity_type="text"),
        status="ADDED",
        category="drawing_views",
        annotator="imrysn",
    )
    monkeypatch.setattr(gt, "get_or_404", AsyncMock(return_value=marking))
    monkeypatch.setattr(
        gt.ManualCheckSession,
        "get",
        AsyncMock(side_effect=Exception("InvalidId")),
        raising=False,
    )

    result = await gt.retract_marking("m1")

    assert result.data.retracted_at is not None


# ── not pinned here, deliberately ────────────────────────────────────────────────────
#
# `list_markings` now pushes the `retracted_at` filter into the query so the
# `(session_id, retracted_at)` compound index is used on the panel's read. There is no test for
# it in this module and that is not an oversight: the handler builds its query from Beanie
# class-attribute expressions (`GroundTruthMarking.session_id == ...`), which resolve through
# descriptors that only exist after `init_beanie`. This harness is fully mocked and never calls
# it, so the expression raises `AttributeError` before the assertion can be reached.
#
# It is the same constraint `create_session` records above its resume query, and the reason that
# query is written as a raw mapping instead. `list_markings` is not worth the same contortion —
# it has no invariant to protect, only an index to use — so the cost is recorded here rather
# than paid.
