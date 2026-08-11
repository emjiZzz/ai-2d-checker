"""A malformed path-param id must be a 404, and the guard for that had gone inert.

**The live failure.** A supervisor clicked Approve on a finding whose canvas marker was generated
client-side, so the id on the wire was `phys_chk_restored_1_1786329084013` rather than a Mongo
ObjectId. The endpoint answered `500 INTERNAL_SERVER_ERROR`:

    File "services/backend/api/dependencies.py", line 47, in get_or_404
        doc = await model.get(id)
    File "beanie/odm/documents.py", line 243, in get
        document_id = parse_object_as(...)
    pydantic_core._pydantic_core.ValidationError: 1 validation error ...
      Value error, Id must be of type PydanticObjectId

**Why the existing guard did not catch it.** `get_or_404` was written for exactly this bug and
caught `bson.errors.InvalidId`. Beanie 2.x validates the id through a Pydantic `TypeAdapter`
*before* it reaches bson, so on this version (beanie 2.1.0 / pydantic 2.13.4) `InvalidId` can no
longer be raised from that call at all. The guard kept compiling, the suite kept passing, and it
had silently stopped guarding — across all ~24 `get_or_404` call sites in annotations, audits and
drawings.

That is the generalisable part, and it is why these tests assert on **both** exception types
rather than only the one this version happens to raise: a guard clause naming a concrete exception
type is a dependency on a library's internals, and nothing fails when the library stops raising it.

These run with no MongoDB because Beanie validates the id shape before it opens a connection — the
malformed-id path never reaches the database, which is precisely why it is cheap to pin.
"""
from __future__ import annotations

import pytest
from bson.errors import InvalidId
from fastapi import HTTPException

from services.backend.api.dependencies import get_or_404
from services.backend.domain.models.audit_violation import AuditViolation

pytestmark = pytest.mark.asyncio

#: The exact id from the production traceback — a client-side marker, not an ObjectId.
SYNTHETIC_MARKER_ID = "phys_chk_restored_1_1786329084013"


async def test_a_synthetic_marker_id_is_404_not_500():
    """The live reproduction, against the real Beanie model and this pinned version."""
    with pytest.raises(HTTPException) as excinfo:
        await get_or_404(AuditViolation, SYNTHETIC_MARKER_ID, "Audit violation not found.")

    assert excinfo.value.status_code == 404, (
        f"A malformed violation id returned {excinfo.value.status_code}, not 404. "
        "The reviewer sees INTERNAL_SERVER_ERROR for a row that simply does not exist."
    )
    assert excinfo.value.detail == "Audit violation not found."


@pytest.mark.parametrize(
    "bad_id",
    [
        SYNTHETIC_MARKER_ID,
        "",
        "not-an-objectid",
        "12345",
        "zzzzzzzzzzzzzzzzzzzzzzzz",  # 24 chars, but not hex
    ],
)
async def test_no_malformed_id_shape_escapes_as_a_500(bad_id):
    """Whatever a client sends in the path, the answer is 404 — never an unhandled exception."""
    with pytest.raises(HTTPException) as excinfo:
        await get_or_404(AuditViolation, bad_id, "Audit violation not found.")
    assert excinfo.value.status_code == 404


async def test_the_older_bson_invalidid_path_is_still_handled():
    """Version-independence, asserted rather than assumed.

    Beanie 2.x raises `ValidationError`; older versions raised `bson.errors.InvalidId`. Catching
    only whichever one today's version happens to throw is what created this defect, so both are
    pinned. Do not "tidy" either out of the except clause.
    """

    class RaisesInvalidId:
        @staticmethod
        async def get(_id):
            raise InvalidId("not a valid ObjectId")

    with pytest.raises(HTTPException) as excinfo:
        await get_or_404(RaisesInvalidId, "whatever", "Nope.")
    assert excinfo.value.status_code == 404


async def test_a_well_formed_but_absent_id_is_also_404():
    """The ordinary miss, so the malformed-id fix cannot be mistaken for the whole behaviour."""

    class ReturnsNothing:
        @staticmethod
        async def get(_id):
            return None

    with pytest.raises(HTTPException) as excinfo:
        await get_or_404(ReturnsNothing, "507f1f77bcf86cd799439011", "Nope.")
    assert excinfo.value.status_code == 404


async def test_a_found_document_is_returned_unchanged():
    """The happy path, so none of the above can pass by making everything 404."""
    sentinel = object()

    class ReturnsDoc:
        @staticmethod
        async def get(_id):
            return sentinel

    assert await get_or_404(ReturnsDoc, "507f1f77bcf86cd799439011", "Nope.") is sentinel
