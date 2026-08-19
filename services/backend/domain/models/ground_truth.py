"""Ground-truth capture: what an engineer found when they checked a pair by hand.

## Why this is its own collection

`audit_feedback` records a human *correcting the engine* -- every row presupposes a finding the
engine already produced, so that collection can only ever describe precision. These documents
record a human *reading the drawings*, with no engine involved. That is the only kind of record
that can describe what the engine **missed**, which is the point of collecting them.

Keeping the two apart is deliberate. Merging them would make "did a human see this" and "did a
human disagree with us about this" the same question, and they are not.

## Why an address is a composite and not an entity id

`ExtractionPipeline.run` **deletes and re-inserts** a drawing's entities, so every
`ExtractedEntity` gets a fresh ObjectId on re-extraction. `EXTRACTION_SCHEMA_VERSION` is at 6,
which is six occasions on which a fix required exactly that. A marking keyed on an entity id
would dangle the first time anyone ran `POST /drawings/{id}/reextract` -- and it would dangle
*silently*: the marking still reads fine, it just no longer points at anything.

A DXF `handle` survives re-extraction because it comes from the source file, but it does not
cover the corpus. Measured over 3615 entities in the first six exported drawings, `handle` and
`parent_handle` are mutually exclusive, and text-entity handle coverage is 92% on a re-traced
revision sheet against **0.8-13% on a reference sheet** -- the side a REMOVED must anchor to.

So an address carries every key that might survive, and
`infrastructure/ground_truth/address_resolver.py` re-binds it in tiers. See
`tests/test_ground_truth_addressing.py`, which is the test that decides whether this data is
worth collecting at all.
"""

from datetime import UTC, datetime
from typing import Literal

from beanie import Document
from pydantic import BaseModel, Field, field_validator
from pymongo import ASCENDING, DESCENDING, IndexModel

from .cad_point import CadPoint, coerce_cad_point

#: What an engineer can say about one entity.
#:
#: `MATCHED` and `NOT_A_FINDING` have no equivalent in the eval corpus, whose `VALID_STATUSES`
#: is `{CHANGED, ADDED, REMOVED}` -- and that is fine, because this is not the eval corpus. A
#: verified non-change is real signal (it is `verdict_matched` in the trainer's existing
#: vocabulary), and "I looked at this and it is deliberately not a finding" is how a false
#: positive gets *attributed* rather than merely counted.
MarkingStatus = Literal["MATCHED", "ADDED", "REMOVED", "CHANGED", "NOT_A_FINDING"]

SessionStatus = Literal["in_progress", "submitted"]


class EntityAddress(BaseModel):
    """Everything that might still identify one entity after the drawing is re-extracted.

    No single field is sufficient, which is why they are all stored. The resolver tries them in
    descending order of trustworthiness and returns nothing rather than guessing.
    """

    drawing_id: str = Field(..., description="DrawingDocument this entity belonged to when marked")

    # Tier 1 -- from the DXF, so it survives re-extraction. Absent for block-exploded children.
    handle: str | None = Field(None, description="Source DXF entity handle")
    parent_handle: str | None = Field(
        None, description="Handle of the owning INSERT when this came from an exploded block"
    )

    # Tier 2 -- discriminators for the fallback match.
    entity_type: str = Field(..., description="Normalized CAD type: text, dimension, line, ...")
    layer: str = Field("0", description="Layer the entity sits on")
    text: str = Field("", description="Verbatim entity text; empty for non-text geometry")

    # Tier 3 -- position. A CadPoint rather than a bare pair so that a re-render against
    # different bounds is *detectable* (`coordinate_stamp.has_drifted`) instead of silently
    # moving the marking. Stamped server-side.
    point: CadPoint | None = Field(None, description="Where the engineer clicked, with provenance")

    # Provenance of the extraction this address was authored against.
    source_file_hash: str | None = Field(
        None,
        description="Hash of the source DXF. Stable across re-extraction, so it proves the "
        "drawing is still the same drawing even when every entity id has changed.",
    )
    extraction_schema_version: int | None = Field(
        None, description="EXTRACTION_SCHEMA_VERSION in force when this address was captured"
    )

    @field_validator("point", mode="before")
    @classmethod
    def _coerce_point(cls, value: object) -> "CadPoint | None":
        """Accept a bare [x, y] from any writer that bypasses the router's stamping."""
        return coerce_cad_point(value)


class ManualCheckSession(Document):
    """One engineer's pass over one reference/revision pair."""

    room_id: str = Field(..., description="Room the pair was opened from")
    ref_drawing_id: str = Field(..., description="Reference drawing")
    rev_drawing_id: str = Field(..., description="Revision drawing")
    annotator: str = Field(..., description="Who did the checking")
    status: SessionStatus = Field("in_progress")
    notes: str = Field(
        "", description="Pair-level narrative: context a per-marking note cannot hold"
    )
    marking_count: int = Field(0, description="Denormalised count, maintained on write")
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    submitted_at: datetime | None = Field(None)

    class Settings:
        name = "manual_check_sessions"
        indexes = [
            IndexModel([("room_id", ASCENDING)]),
            IndexModel([("annotator", ASCENDING)]),
            IndexModel([("status", ASCENDING)]),
            IndexModel([("started_at", DESCENDING)]),
        ]


class GroundTruthMarking(Document):
    """One decision an engineer made about one entity, or one pair of entities.

    ## The fields are a superset on purpose

    How these become training rows is not decided yet, and deciding it later must not require
    re-labelling. So this captures what either plausible consumer would need:

    * the learned trainer's `build_feature_row` wants `ref_text`, `rev_text`, `category`, a
      status, and both coordinates (it derives `match_distance` from them);
    * a corpus-style label wants an address, a category, a status, both texts and `is_bulk`.

    Nothing here is written by an automated process. Every row is a human statement.
    """

    session_id: str = Field(..., description="Owning ManualCheckSession")

    #: Which side the engineer clicked. A CHANGED carries both addresses; an ADDED carries only
    #: `rev_address`; a REMOVED only `ref_address` -- the reference is where a removal exists.
    side: Literal["ref", "rev", "both"] = Field(...)
    ref_address: EntityAddress | None = Field(None)
    rev_address: EntityAddress | None = Field(None)

    status: MarkingStatus = Field(...)

    #: One of the six in `infrastructure/audit/comparison/taxonomy.py`. Held as a plain `str`
    #: here because `domain/` may not import `infrastructure/`
    #: (`tests/test_layer_boundaries.py`); the API layer validates it against the real
    #: `Category` literal before anything reaches this model, and
    #: `tests/test_ground_truth_submission.py` pins that the two lists agree.
    category: str = Field(...)

    #: Whether a human chose the category or it was derived from the entity's zone.
    #:
    #: Load-bearing for what this corpus is FOR. The mutation corpus's attribution figure is a
    #: known tautology -- its labels come from `zone_detector`, and changing the zone boxes moved
    #: attribution 0.81 -> 0.74 with no engine change at all. The human pairs were the first
    #: attribution numbers here that were not tautologies (0.92), and that holds only while the
    #: engineer's category is independent of the detector.
    #:
    #: Deriving it removes a real click, so it is allowed -- but it must be VISIBLE, or the
    #: independent rows and the circular ones become indistinguishable and the whole figure
    #: reverts to measuring `zone_detector` against itself. An evaluator filters on this.
    #:
    #: Defaults to `human`: every row written before 2026-08-18 was chosen by a person, so the
    #: default has to be the one that is true of the existing data rather than the new path's.
    category_source: Literal["human", "zone"] = Field("human")

    ref_text: str = Field("", description="Verbatim reference-side text; empty where absent")
    rev_text: str = Field("", description="Verbatim revision-side text; empty where absent")
    #: True when the engineer overrode the auto-read value. The raw entity text stays in the
    #: address, so an override stays inspectable rather than being discovered later as a label
    #: that disagrees with its own entity.
    text_was_edited: bool = Field(False)

    #: One editorial act anchored on one entity -- a whole added view is 1 marking, not 40.
    #: Counts for these are reported separately, so it must be recorded, not inferred.
    is_bulk: bool = Field(False)

    notes: str = Field("", description="The engineer's reasoning. Not scored; read on dispute.")
    annotator: str = Field(...)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    #: Set rather than deleted, for the same reason `audit_feedback` does it: this collection is
    #: both the dataset and the record of who asserted what. A row that silently vanishes is
    #: unauditable.
    retracted_at: datetime | None = Field(None)

    class Settings:
        name = "ground_truth_markings"
        indexes = [
            IndexModel([("session_id", ASCENDING)]),
            IndexModel([("status", ASCENDING)]),
            IndexModel([("category", ASCENDING)]),
            IndexModel([("annotator", ASCENDING)]),
            IndexModel([("created_at", DESCENDING)]),
            # The training/export read is "every live marking in this session".
            IndexModel([("session_id", ASCENDING), ("retracted_at", ASCENDING)]),
        ]
