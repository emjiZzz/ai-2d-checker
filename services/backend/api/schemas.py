from typing import Any, List, Optional, TypeVar, Literal

from pydantic import BaseModel, Field, field_validator

from ..domain.models.cad_point import CadPoint, CoordinateSpace
from ..domain.models.extracted_entity import EXTRACTION_SCHEMA_VERSION
from ..domain.models.room_mode import AI_COMPARISON, RoomMode, normalize_room_mode
from ..domain.models.comparison_method import (
    DETERMINISTIC,
    ComparisonMethodName,
    normalize_comparison_method,
)

# Re-exported so API consumers import the coordinate envelope from one place.
__all_coordinate_types__ = ("CadPoint", "CoordinateSpace")

T = TypeVar("T")

class ErrorDetail(BaseModel):
    code: str = Field(..., description="Unique machine-readable uppercase error string")
    message: str = Field(..., description="Human-friendly descriptive error message")
    detail: Any | None = Field(None, description="Optional diagnostic error properties or traceback")

class StandardResponse[T](BaseModel):
    success: bool = Field(..., description="Indicates if the requested operation succeeded")
    data: T | None = Field(None, description="Response payload")
    error: ErrorDetail | None = Field(None, description="Populated error details if success is false")

class SystemStatusResponse(BaseModel):
    status: str = Field(..., description="E.g., healthy, degraded, offline")
    version: str
    name: str
    timestamp: float

class DatabaseHealthDetails(BaseModel):
    status: str
    latency_ms: float
    connected: bool
    database_name: str | None = None
    error: str | None = None

class StorageHealthDetails(BaseModel):
    status: str
    write_permission: bool
    storage_root: str
    disk_usage: dict
    directories: dict
    error: str | None = None

from datetime import datetime


class DrawingResponse(BaseModel):
    id: str
    file_name: str
    file_path: str
    file_hash: str
    file_size_bytes: int
    format: str
    status: str
    entity_counts: dict
    metadata: dict
    ai_summary: dict | None = None
    # Drawing-number tokens the desktop client compares between the two slots to reject a
    # reference/revision pair that is not a pair. Defaulted, so drawings ingested before
    # this field existed deserialize as "no judgement possible" rather than failing.
    drawing_numbers: list[str] = []
    # Which extraction schema this drawing's entities were written under, and whether that is
    # behind the current one. `render_paths`, dimension text anchors, leader hooklines and
    # arrowheads, MTEXT rotation and the angular-dimension degree conversion are all computed
    # at EXTRACTION time, so a stale drawing renders wrong and keeps rendering wrong until
    # `POST /drawings/{id}/reextract` — and it looks like a drawing the whole time.
    #
    # `extraction_is_stale` is computed server-side rather than by comparing the two numbers in
    # the client. The rule belongs beside `EXTRACTION_SCHEMA_VERSION`; there is no runtime type
    # sharing between Python and TypeScript here, so a second copy of the comparison is a
    # second thing to forget when the constant moves. Both numbers are still sent because the
    # badge shows them ("v2 of v7"), which a boolean cannot express.
    #
    # Defaulted, so a drawing ingested before this field existed deserializes as "no judgement
    # possible" rather than failing — the same reasoning as `drawing_numbers` above.
    extraction_schema_version: int = 0
    current_extraction_schema_version: int = 0
    extraction_is_stale: bool = False
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_document(cls, drawing: Any) -> "DrawingResponse":
        """The wire response for one `DrawingDocument`.

        One constructor because there are three call sites -- upload, list and get -- which
        held byte-identical field literals. Adding a field to two of the three is not an error
        in Python; it is a response that carries the field on some endpoints and silently omits
        it on others, and the client cannot tell the difference from a drawing that genuinely
        lacks it. That is the drift this repo keeps paying for, so there is one site.
        """
        # `0` is what a never-stamped row deserializes to (the document field defaults to 0),
        # so it is treated as "older than anything current" rather than as a real version.
        stored = int(getattr(drawing, "extraction_schema_version", 0) or 0)
        return cls(
            id=str(drawing.id),
            file_name=drawing.file_name,
            file_path=drawing.file_path,
            file_hash=drawing.file_hash,
            file_size_bytes=drawing.file_size_bytes,
            format=drawing.format,
            status=drawing.status,
            entity_counts=drawing.entity_counts,
            metadata=drawing.metadata,
            drawing_numbers=drawing.drawing_numbers,
            extraction_schema_version=stored,
            current_extraction_schema_version=EXTRACTION_SCHEMA_VERSION,
            extraction_is_stale=stored < EXTRACTION_SCHEMA_VERSION,
            created_at=drawing.created_at,
            updated_at=drawing.updated_at,
        )

class JobResponse(BaseModel):
    id: str
    drawing_id: str
    status: str
    error_message: str | None = None
    diagnostics: dict
    conversion_duration_seconds: float | None = None
    parsing_duration_seconds: float | None = None
    total_duration_seconds: float | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None

class UploadResponse(BaseModel):
    drawing: DrawingResponse
    job: JobResponse
    is_duplicate: bool

class StandardDocumentResponse(BaseModel):
    id: str
    name: str
    file_path: str
    standard_hash: str
    file_size_bytes: int
    format: str
    scope: str = "client_specific"
    client_name: str | None = None
    category: str | None = None
    description: str | None = None
    metadata: dict
    created_at: datetime

class ClientResponse(BaseModel):
    id: str
    name: str
    created_at: datetime

class CreateClientRequest(BaseModel):
    name: str

class LaunchAuditRequest(BaseModel):
    drawing_id: str
    reference_drawing_id: str | None = None
    standard_id: str | None = None
    client_name: str | None = None

class AuditSessionResponse(BaseModel):
    id: str
    drawing_id: str
    reference_drawing_id: str | None = None
    standard_id: str | None = None
    client_name: str | None = None
    status: str
    compliance_score: float | None = None
    confidence_score: float | None = None
    error_message: str | None = None
    timings: dict
    diagnostics: dict
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    remarks: str | None = None
    username: str | None = None
    is_deleted: bool = False
    deleted_at: datetime | None = None
    deleted_by: str | None = None
    is_restored: bool = False

class UpdateAuditSessionRequest(BaseModel):
    remarks: str

class AuditViolationResponse(BaseModel):
    id: str
    audit_session_id: str
    severity: str
    category: str
    description: str
    recommendation: str
    affected_entities: list
    confidence: float
    source: str
    coordinates: list[CadPoint] | None = None
    entity_handle: str | None = None
    standard_reference: str | None = None
    pen_type: str
    # `is_resolved` is a boolean and therefore cannot express "not reviewed yet": an unreviewed
    # finding and a finding a supervisor explicitly REJECTED both read False. `resolution_type`
    # is the three-state field (None | APPROVED | REJECTED) and is what a review queue must
    # filter on -- without it a rejected finding reappears in the queue forever.
    resolution_type: str | None = None
    is_resolved: bool
    resolved_at: datetime | None = None
    checker_remarks: str | None = None
    created_at: datetime

# PBKDF2 Auth & Session Schemas
class LoginRequest(BaseModel):
    username: str = Field(..., description="Unique login identifier")
    password: str = Field(..., description="Plaintext raw credentials")

class LoginResponse(BaseModel):
    session_token: str = Field(..., description="HMAC-SHA256 signed active session identifier (base64 payload + '.' + signature, not encrypted)")
    username: str = Field(..., description="Logged-in username")
    role: str = Field(..., description="Enterprise workspace role: admin or user")

class UserAccountResponse(BaseModel):
    id: str
    username: str
    role: str
    active: bool
    created_at: datetime
    permissions: list[str]

class CreateUserRequest(BaseModel):
    username: str
    password: str
    role: str
    permissions: list[str] | None = None

class UpdateUserRequest(BaseModel):
    active: bool | None = None
    role: str | None = None
    password: str | None = None

class PhysicalComparisonRequest(BaseModel):
    reference_drawing_id: str
    drawing_id: str
    comparison_method: ComparisonMethodName = Field(
        DETERMINISTIC,
        description="Comparison pipeline. Only the deterministic method exists; the three Gemini-backed ones were removed (ADR-006). The legacy name 'rag' is accepted and normalised."
    )
    _normalize_method = field_validator("comparison_method", mode="before")(
        lambda v: normalize_comparison_method(v)
    )
    force_refresh: bool = Field(
        default=False,
        description="If true, bypasses cached comparison results on disk and re-evaluates fresh."
    )
    refresh_ocr: bool = Field(
        default=False,
        description="If true, ALSO bypasses the cached title-block OCR and re-reads the crop "
                    "with Gemini (a paid call per drawing). Implies force_refresh, since a fresh "
                    "OCR value only takes effect through a fresh comparison run."
    )

class CorrectedCounterpart(BaseModel):
    """The entity a human says the engine should have paired with.

    Fixed fields rather than a bare dict. Two reasons: a free-form object lets every client
    invent its own key names, and `PhysicalComparisonResponse` has already taught this codebase
    what an open-ended shape costs (constraint 1 in CLAUDE.md).

    `handle` is optional because block-exploded content carries none — the normal case on a
    reference sheet, at 0.8–13% coverage — so `text` and `coordinates` are how such an entity is
    identified, not decoration.
    """

    side: Literal["ref", "rev"]
    handle: Optional[str] = None
    text: str = ""
    coordinates: Optional[List[float]] = None


class FindingSnapshot(BaseModel):
    """Fixed-field feature snapshot of a finding at the moment a human corrects it.

    Captured so the learned-model trainer can reconstruct the exact runtime feature
    vector from stored feedback long after the comparison that produced it is gone.
    Fixed fields on purpose (never a bare `dict`) so training and inference features
    stay identical — but note this rides ONLY on /audits/feedback and is stored on the
    Mongo AuditFeedbackDocument; it is deliberately NOT part of PhysicalComparisonResponse
    or CanvasMarking, which are handed to Gemini as response_schema (CLAUDE.md constraint 1)."""
    ref_text: Optional[str] = None
    rev_text: Optional[str] = None
    det_status: Optional[str] = Field(None, description="Deterministic status before correction: MATCHED/CHANGED/ADDED/REMOVED/CONFLICT")
    category: Optional[str] = None
    feature: Optional[str] = None
    ref_coord: Optional[list[float]] = None
    rev_coord: Optional[list[float]] = None

    #: The three below are ALWAYS null in stored rows, and that is correct — do not "fix" it.
    #:
    #: Measured 2026-08-19: non-null in 0 of 249 documents. That looks like a defect and is not.
    #: `feature_extractor.build_feature_row` derives each one whenever it arrives as `None`, and
    #: `features_from_snapshot` routes every stored snapshot through it, so they are computed on
    #: the training path from `ref_text` / `rev_text` / the two coordinates.
    #:
    #: They stay in the schema because the INFERENCE path shares that function and may pass real
    #: values; one shape serves both, which is what keeps training and serving on a single
    #: definition of a feature.
    #:
    #: Filling them from the client would be train/serve skew and has shipped before — there is
    #: no `SequenceMatcher` or `SpatialDiffer._normalize_text` in TypeScript, so a browser-side
    #: `text_similarity` would not be the number the trainer means by that name. Pinned by
    #: `tests/test_stage_0a_measurement_unblocking.py`.
    #:
    #: `match_distance` is `-1.0` where a coordinate is missing (142 of 249 rows) — an explicit
    #: sentinel, not a silent zero.
    text_similarity: Optional[float] = None
    match_distance: Optional[float] = None
    is_numericish: Optional[bool] = None


# Human correction verbs. Extended from the original dismissed/confirmed_valid/
# category_override trio: the model needs a positive/negative verdict signal, not just
# suppression. See docs plan "Human-in-the-Loop Learning for the rag Comparison".
HumanCorrectedStatus = Literal[
    "dismissed",         # false alarm — treat as not a real discrepancy (label 0)
    # Label 1, not 0. The parenthetical here previously read "(label 0…)", contradicting
    # trainer.py's VERDICT_ONE, which is where the label is actually decided. The prose was
    # right and the parenthetical was wrong: "this finding IS valid to report" means it is a
    # true discrepancy.
    "confirmed_valid",   # undo of a dismissal — this finding IS valid to report (label 1)
    "category_override", # finding belongs in a different category/feature
    "verdict_matched",   # a CHANGED/ADDED/REMOVED that is actually MATCHED (label 0)
    "verdict_changed",   # a MATCHED that is actually a real change (label 1)
    "confirmed_change",  # affirm a flagged discrepancy is genuinely a change (label 1)
    "value_correction",  # the extracted Original/Revision value was misread; corrected_value holds the fix
    # --- pairing feedback -----------------------------------------------------------------
    # A different *kind* of statement from everything above. The seven verbs all judge a
    # finding's verdict, category or value — they assume the engine paired the right two
    # entities and only got its conclusion wrong. These two say the pairing itself is
    # wrong, which nothing could express before.
    #
    # Deliberately NOT mapped to a verdict label; see trainer.MATCHER_FEEDBACK for why. They
    # are training data for the Stage 3 learned matcher, captured now so the labels exist when
    # there is something to train — the same reason AuditFeedbackDocument was worth building
    # before the model that reads it.
    "mispaired_missing_counterpart",  # reported ADDED/REMOVED, but the other drawing does have a match
    "mispaired_wrong_match",          # paired two entities that are not the same thing
]


class AuditFeedbackRequest(BaseModel):
    session_id: str
    drawing_id: str
    client_name: Optional[str] = None
    entity_text: str
    entity_handle: Optional[str] = None
    category: str
    original_status: str
    human_corrected_status: HumanCorrectedStatus
    human_comment: Optional[str] = None
    coordinates: Optional[list[float]] = None
    corrected_category: Optional[str] = Field(None, description="Target category for a category_override correction.")
    corrected_value: Optional[str] = Field(None, description="Corrected value for a value_correction.")
    corrected_counterpart: Optional[CorrectedCounterpart] = Field(
        None,
        description=(
            "For a mispaired_* correction: the entity the engine SHOULD have paired with. "
            "Optional so the 249 rows predating it stay valid; absent means 'not recorded', "
            "never 'no counterpart exists'."
        ),
    )
    finding_snapshot: Optional[FindingSnapshot] = Field(None, description="Feature snapshot of the corrected finding, used as a training example.")

class AuditFeedbackResponse(BaseModel):
    id: str
    status: str
    auto_documented: bool = False
    message: str

# Room workflow schemas
class RoomCreateRequest(BaseModel):
    name: str = Field(..., description="User-facing room label")
    description: str | None = None
    client_name: str | None = None
    comparison_method: ComparisonMethodName = Field(
        DETERMINISTIC,
        description="Comparison pipeline for this room. Only the deterministic method exists (ADR-006). The legacy name 'rag' is accepted and normalised."
    )
    room_mode: RoomMode = Field(
        AI_COMPARISON,
        description="What this room is for: 'ai_comparison' runs the deterministic engine; 'manual_check' collects human ground truth and never invokes it. Orthogonal to comparison_method."
    )
    _normalize_method = field_validator("comparison_method", mode="before")(
        lambda v: normalize_comparison_method(v)
    )
    _normalize_room_mode = field_validator("room_mode", mode="before")(
        lambda v: normalize_room_mode(v)
    )

class RoomResponse(BaseModel):
    id: str
    name: str
    description: str | None = None
    client_name: str | None = None
    active_old_drawing_id: str | None = None
    active_new_drawing_id: str | None = None
    active_old_drawing_name: str | None = None
    active_new_drawing_name: str | None = None
    active_audit_session_id: str | None = None
    physical_comparison_results: dict | None = None
    zones_confirmed_for: str | None = None
    comparison_method: ComparisonMethodName = DETERMINISTIC
    room_mode: RoomMode = AI_COMPARISON
    _normalize_method = field_validator("comparison_method", mode="before")(
        lambda v: normalize_comparison_method(v)
    )
    _normalize_room_mode = field_validator("room_mode", mode="before")(
        lambda v: normalize_room_mode(v)
    )
    created_by: str | None = None
    created_at: datetime
    updated_at: datetime
    last_opened_at: datetime | None = None

class UpdateRoomRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    client_name: str | None = None
    active_old_drawing_id: str | None = None
    active_new_drawing_id: str | None = None
    active_old_drawing_name: str | None = None
    active_new_drawing_name: str | None = None
    active_audit_session_id: str | None = None
    physical_comparison_results: dict | None = None
    zones_confirmed_for: str | None = None

AnnotationSeverity = Literal["info", "low", "medium", "high", "critical"]
AnnotationPenType = Literal["checker_blue", "amber_gold", "warning_orange", "alert_red", "resolved_green", "resolved_pink"]

class CreateAnnotationRequest(BaseModel):
    review_session_id: str = Field(..., description="Active review session or room id")
    drawing_id: str = Field(..., description="Drawing this annotation is pinned to")
    annotation_type: str = "pin"
    content: str
    severity: AnnotationSeverity = "info"
    # Requests carry a bare [x, y]; the server stamps coordinate-space provenance from
    # the DrawingDocument it is attached to (see infrastructure/cad/coordinate_stamp.py).
    # Clients cannot know the drawing's layout or transform version, and trusting them
    # to supply it would let a point's provenance disagree with its own drawing.
    coordinates: list[float] | None = Field(None, description="[x, y] pin centre; provenance is stamped server-side")
    target_entity_ids: list[str] = Field(default_factory=list)
    violation_id: str | None = None
    pen_type: AnnotationPenType = "checker_blue"

class UpdateAnnotationRequest(BaseModel):
    content: str | None = None
    status: str | None = None
    severity: AnnotationSeverity | None = None
    coordinates: list[float] | None = Field(None, description="[x, y] pin centre; re-stamped server-side on move")
    pen_type: AnnotationPenType | None = None

class AnnotationResponse(BaseModel):
    id: str
    review_session_id: str
    drawing_id: str
    author_id: str
    annotation_type: str
    content: str
    severity: AnnotationSeverity
    coordinates: CadPoint | None = None
    target_entity_ids: list[str]
    violation_id: str | None = None
    status: str
    pen_type: AnnotationPenType
    created_at: datetime
    updated_at: datetime
    # True when the drawing has been re-rendered against different bounds since this
    # pin was placed, so its stored position no longer maps to where the user put it.
    # Previously this situation was silent and unrecoverable.
    coordinate_drift: bool = Field(False, description="Stored coordinates predate the drawing's current render bounds")

class ZoneComparisonResult(BaseModel):
    status: str
    differenceSummary: str
    extractedContent: Optional[str] = None
    discrepancyDetails: Optional[str] = None

class BomRowComparison(BaseModel):
    row: int
    col: str
    original: str
    kmti: str
    diffType: str


class CategoryComparison(BaseModel):
    status: Literal["MATCHED", "CHANGED", "ADDED", "REMOVED", "MISSING"]
    difference_summary: str = Field(..., description="High-level engineering discrepancy summary.")
    reference_content: Optional[str] = Field(None, description="Extracted content from the reference drawing.")
    revision_content: Optional[str] = Field(None, description="Extracted content from the revision drawing.")
    engineering_discrepancy_details: Optional[str] = Field(None, description="Actionable checklist feedback.")

class CanvasMarking(BaseModel):
    text_content: str = Field(..., description="The exact text string in the revised KMTI drawing to locate and highlight.")
    status: Literal["MATCHED", "CHANGED", "ADDED", "REMOVED", "CONFLICT"] = Field(..., description="Audit status for this specific text marking. CONFLICT means the hybrid pipeline's two generators disagreed and the crop verifier could not confirm either side — flagged for human review, never silently resolved.")
    details: str = Field(..., description="Short explanation of the check result for this element.")
    category: Literal["drawing_views", "notes_section", "bill_of_materials", "title_block", "isometric_view", "other_engineering_references"] = Field(
        default="drawing_views",
        description="The checklist category this text belongs to."
    )
    entity_id: Optional[str] = Field(default=None, description="The precise [ID: <handle>] extracted from the provided text string (e.g. '1B2A'). For ADDED or CHANGED items, use the REV-ID. For REMOVED items, use the REF-ID. Mandatory if present.")
    coordinates: Optional[list[float]] = Field(default=None, description="Optional physical coordinate [x, y] of the text element on the sheet.")
    ref_coordinates: Optional[list[float]] = Field(default=None, description="Optional physical coordinate [x, y] of the text element on the reference sheet.")
    bbox: Optional[list[list[float]]] = Field(default=None, description="Optional bounding box of the text element.")
    ref_bbox: Optional[list[list[float]]] = Field(default=None, description="Optional bounding box of the text element on the reference sheet.")
    original_value: Optional[str] = Field(default=None, description="The original value from the reference drawing, if changed.")
    visual_bbox: Optional[list[float]] = Field(default=None, description="Optional visual bounding box [ymin, xmin, ymax, xmax] on the revision drawing sheet image, normalized 0 to 1000.")
    ref_visual_bbox: Optional[list[float]] = Field(default=None, description="Optional visual bounding box [ymin, xmin, ymax, xmax] on the reference drawing sheet image, normalized 0 to 1000.")
    origin: Optional[Literal["deterministic", "ai_vision"]] = Field(default=None, description="Which generator produced this finding in the removed hybrid pipeline (ADR-006). Always None now; the literal keeps 'ai_vision' so cached payloads written before the removal still parse.")
    verification: Optional[Literal["confirmed_both", "confirmed_single", "corrected_to_matched", "conflict", "unverified"]] = Field(default=None, description="Hybrid-pipeline outcome: confirmed_both = both generators agreed, confirmed_single = the two disagreed and the crop verifier picked a side, corrected_to_matched = the verifier looked at the actual crops and found no real difference at all, overriding whatever either generator originally claimed (status is forced to MATCHED), conflict = the verifier could not confirm either side, unverified = single-source finding not yet run through the verifier. Always None since ADR-006 removed the hybrid pipeline; retained so cached payloads written before it still parse.")
    resolution_method: Optional[Literal["entity_handle", "visual_bbox_fallback", "unresolved"]] = Field(default=None, description="How `coordinates` was derived: exact entity-handle lookup, Gemini's normalized visual bbox mapped to CAD space, or not resolved at all.")
    feature: Optional[str] = Field(default=None, description="Sub-item taxonomy key within `category` (e.g. category='title_block', feature='scale') — see services/backend/infrastructure/audit/comparison/taxonomy.py for the canonical list per category. Used to group the checklist panel into named sub-sections instead of one flat list per category. Falls back to 'other' when unset or unrecognized.")

class CategoryAgreement(BaseModel):
    """
    Per-category generator agreement counts, from the removed `hybrid` method (ADR-006) —
    always empty now, and kept because it is present in cached payloads.

    Still a fixed-shape object rather than a dict keyed by category name, for the same
    reason ComparisonDiagnostics isn't a bare dict below: Gemini's structured-output API
    rejects open-ended additionalProperties schemas, and this nests inside
    PhysicalComparisonResponse, which is `execute_gemini_cascade`'s default
    `response_schema`. See CLAUDE.md constraint 1 — and note the removal changed that
    constraint from "fires on every request" to "fires on the first caller that omits a
    schema", which is dormant, not gone.
    """
    category: str
    generator_a_candidates: int = 0
    generator_b_candidates: int = 0
    confirmed_both: int = 0
    confirmed_single: int = 0
    corrected_to_matched: int = 0
    conflicts: int = 0


class ComparisonDiagnostics(BaseModel):
    """Backend-populated confidence/fallback metadata (which AI model actually answered,
    zone-detection fallback warnings, etc.) — not something the comparison model should
    fill in itself; always overwritten server-side after generation, same as
    bill_of_materials' deterministic override. A fixed-field model, not a bare dict:
    Gemini's structured-output API rejects open-ended "additionalProperties" schemas
    (a bare `dict` field breaks response_schema validation with a 400 INVALID_ARGUMENT
    for every request, not just when the field happens to be populated)."""
    model_used: Optional[str] = Field(default=None, description="Which model in the cascade actually produced this comparison (e.g. a Pro->Flash rate-limit fallback).")
    audit_session_id: Optional[str] = Field(default=None, description="The AuditSession this comparison persisted its violations under. The client needs it to request the ADR-010 summary; without it the session id existed only in a log line.")
    zone_detection_warnings: list[str] = Field(default_factory=list, description="Zones where reference/revision bbox detection used different or low-confidence methods.")
    generator_a_candidates: int = Field(default=0, description="Hybrid only: candidate count produced by the deterministic generator before reconciliation.")
    generator_b_candidates: int = Field(default=0, description="Hybrid only: candidate count produced by the AI Vision generator before reconciliation.")
    confirmed_both: int = Field(default=0, description="Hybrid only: findings where both generators agreed, no verifier call needed.")
    confirmed_single: int = Field(default=0, description="Hybrid only: findings where the two generators disagreed and the crop verifier confirmed one side.")
    corrected_to_matched: int = Field(default=0, description="Hybrid only: findings where the crop verifier found no real difference at all, overriding whatever either generator originally claimed and forcing status to MATCHED.")
    conflicts: int = Field(default=0, description="Hybrid only: findings the crop verifier could not confirm either way; flagged CONFLICT for human review.")
    category_agreement: list[CategoryAgreement] = Field(default_factory=list, description="Hybrid only: per-category breakdown of the six counters above — lets a future pass measure whether Generator B is worth running for a given category before building any auto-gating logic on top of it.")

class PhysicalComparisonResponse(BaseModel):
    drawing_views: CategoryComparison
    notes_section: CategoryComparison
    bill_of_materials: CategoryComparison
    title_block: CategoryComparison
    isometric_view: CategoryComparison
    other_engineering_references: CategoryComparison
    canvas_markings: list[CanvasMarking] = Field(default_factory=list, description="Visual checklist coordinates mapping items.")
    diagnostics: Optional[ComparisonDiagnostics] = Field(default=None, description="Backend-populated confidence/fallback metadata, not part of the model's own judgment.")

class SummaryClaimResponse(BaseModel):
    """One grounded sentence plus the finding ids it rests on."""
    text: str
    finding_ids: list[str]


class ComparisonSummaryResponse(BaseModel):
    """ADR-010's outward shape. Deliberately NOT nested into PhysicalComparisonResponse — that
    model is Gemini's `response_schema` and this one is only ever serialized to the desktop app,
    so keeping them apart is what stops a future field here from tripping constraint 1.

    `fallback_text` is always populated. A client that renders it whenever `status != "ok"` is
    always showing something true, which is the point of ADR-010 decision 4: absence of a summary
    is normal operation, not an error state to handle."""
    status: str = Field(..., description="ok | withheld | unavailable | disabled | not_applicable")
    headline: str | None = None
    claims: list[SummaryClaimResponse] = Field(default_factory=list)
    fallback_text: str = Field(..., description="Deterministic template summary. Always present.")
    withheld_reasons: list[str] = Field(default_factory=list)
    withheld_detail: str = ""
    finding_count: int = 0
    model_used: str | None = None
    cached: bool = False


class ViewSummary(BaseModel):
    summary: str = Field(..., description="A detailed summary paragraph for this specific view category.")

class ZoneBBox(BaseModel):
    """One detected template zone's CAD-world bounding box, plus how it was resolved.

    NOT part of any LLM structured-output schema. Unlike PhysicalComparisonResponse and
    everything nested under it, this model is only ever serialized outward to the desktop
    client by GET /drawings/{id}/zones. Do not nest it into PhysicalComparisonResponse —
    see ComparisonDiagnostics' docstring above for why open-ended shapes break Gemini's
    response_schema validation.
    """
    xmin: float
    ymin: float
    xmax: float
    ymax: float
    confidence: str = Field(
        default="unknown",
        description=(
            "How this box was resolved, passed through verbatim from _zone_confidence: "
            "'content_aware' (semantic anchor found, box flood-filled around it — a "
            "measurement), 'percentage_fallback' (no anchor; percentage grid over real "
            "sheet bounds — a plausible guess), or 'percentage_fallback_no_sheet_bounds' "
            "(no sheet bounds at all; the box is the literal (0,0,1000,1000) placeholder "
            "and carries no information). Deliberately not mapped to a narrower enum here "
            "— collapsing the last two would hide the only case the client must refuse to "
            "draw."
        ),
    )


class DrawingZonesResponse(BaseModel):
    """Template-zone boxes for the canvas debug overlay.

    Fixed-field rather than a map: the seven zone keys are a closed set, enumerated in
    table_extractor.default_pct.

    In practice every zone is always populated — extract_dynamic_regions() fills all seven
    from the percentage grid before content-aware detection overrides any of them, so there
    is no "zone not found" case. The fields are Optional purely so a future detector change,
    or a malformed tuple rejected at the boundary, degrades to a missing box rather than a
    500. Client code must not read None as a meaningful signal; the signal is `confidence`.
    """
    drawing_id: str
    render_bounds: Optional[list[float]] = Field(
        default=None,
        description="Flat [xmin, ymin, xmax, ymax] the boxes were computed against, so the "
                    "client can check it still matches the bounds the canvas is rendering "
                    "with before trusting on-screen positions.",
    )
    views: Optional[ZoneBBox] = None
    notes: Optional[ZoneBBox] = None
    bom: Optional[ZoneBBox] = None
    title: Optional[ZoneBBox] = None
    tolerance: Optional[ZoneBBox] = None
    iso: Optional[ZoneBBox] = None
    title_upper_left: Optional[ZoneBBox] = None
    # Optional zone: only non-null on sheets that carry a シム表 shim table.
    shim: Optional[ZoneBBox] = None


class DrawingSummaryResponse(BaseModel):
    drawing_views: ViewSummary = Field(..., description="Origin, alignment, lines, dimensions, holes, chamfers, welds, tolerances, text attrs.")
    notes: ViewSummary = Field(..., description="Standard and special notes.")
    bom: ViewSummary = Field(..., description="Material type, specification, quantity, weight, balloons, remarks, numbering.")
    title_block: ViewSummary = Field(..., description="Machine name, line name, scale, designed by, drawn by, quantity, job/ref numbers, rev code.")
    iso_view: ViewSummary = Field(..., description="Orientation, scale, location.")
    others: ViewSummary = Field(..., description="Tree view properties/link, excel additional information.")
