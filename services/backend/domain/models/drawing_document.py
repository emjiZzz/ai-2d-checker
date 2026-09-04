from datetime import datetime
from typing import Any

from beanie import Document
from pydantic import Field
from pymongo import ASCENDING, IndexModel


class DrawingDocument(Document):
    file_name: str = Field(..., description="Original name of the uploaded drawing")
    file_path: str = Field(..., description="Normalized relative path within storage root")
    file_hash: str = Field(..., description="SHA-256 checksum of file content. Stored for the OCR/comparison cache keys and provenance, NOT for dedup — the same file may be re-uploaded (see DrawingIngestionService.process_ingestion), so this is deliberately non-unique.")
    file_size_bytes: int = Field(..., description="File size in bytes")
    format: str = Field(..., description="File extension format ('dwg' or 'dxf')")
    status: str = Field("queued", description="Ingestion/extraction state: queued, processing, completed, failed")
    entity_counts: dict[str, int] = Field(default_factory=dict, description="Counts of lines, circles, dimensions, etc.")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Extracted structural drawing metadata")
    ai_summary: dict[str, Any] | None = Field(None, description="Detailed 6-view AI summary of the drawing")

    #: Who uploaded this, for per-user separation of workspaces on a shared backend.
    #:
    #: `None` means SHARED, not orphaned. Every drawing predating this field has no owner,
    #: and those are the pre-loaded corpus pairs every tester is meant to work on — so the
    #: `?mine=true` filter includes ownerless rows deliberately, matching what `GET /rooms`
    #: already does for `Room.created_by`. Excluding them would make the shared corpus vanish
    #: from every workspace at once.
    #:
    #: Separation, not access control. It is populated from `X-Engineer-Name`, an
    #: unverified client header (see `api/dependencies.resolve_username`), and every by-id route
    #: still serves any drawing to any caller holding the shared API token. It keeps testers out
    #: of each other's lists; it does not keep them out of each other's data.
    uploaded_by: str | None = Field(None, description="Engineer who uploaded this drawing; None = shared")

    # --- PHASE 1: extraction provenance ---
    # Version stamps make a stale extraction detectable without re-reading entities.
    # There is no backfill path by design: existing drawings are re-ingested rather
    # than migrated, so nothing reads an older value -- these exist for future
    # schema changes.
    extraction_schema_version: int = Field(0, description="Version of the entity extraction schema used")
    transform_version: int = Field(0, description="Version of the model<->paper viewport transform maths used")

    # Drawing-number-shaped text tokens found on the sheet, used to reject a
    # reference/revision pair that is not a pair. Deliberately separate from `part_number`
    # below: that field is dead on real drawings (detect_revision returns None on 14/14
    # corpus sides), and populating it would activate the dormant `previous_revision_id`
    # auto-link in audits.py as a side effect. See infrastructure/cad/drawing_identity.py.
    # Empty means "no judgement possible", never "no match" -- see is_pair_mismatch.
    drawing_numbers: list[str] = Field(
        default_factory=list,
        description="Drawing-number-shaped tokens extracted from the sheet's text",
    )

    # --- PHASE 7.1: DrawingDocument Revision Chain fields ---
    part_number: str | None = Field(None, description="Extracted part number identifier")
    revision_letter: str | None = Field(None, description="Drawing revision index (e.g. A, B, C)")
    previous_revision_id: str | None = Field(None, description="Reference to previous revision DrawingDocument")
    is_latest_revision: bool = Field(True, description="True if this is the most current revision in system")

    created_at: datetime = Field(default_factory=datetime.utcnow, description="Record creation time")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="Record last update time")

    class Settings:
        name = "drawing_documents"
        indexes = [
            # NON-unique on purpose. Dedup was removed (process_ingestion re-ingests every
            # upload as a fresh document); a unique file_hash index contradicts that and made
            # re-uploading a drawing fail with E11000 dup key. Kept as a plain index because
            # file_hash is still looked up for cache keys / provenance.
            IndexModel([("file_hash", ASCENDING)]),
            IndexModel([("created_at", ASCENDING)]),
            IndexModel([("status", ASCENDING)]),
            IndexModel([("part_number", ASCENDING)]),
            IndexModel([("is_latest_revision", ASCENDING)])
        ]
