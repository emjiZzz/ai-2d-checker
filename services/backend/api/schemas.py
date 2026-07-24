from typing import Any, TypeVar, Optional, Literal

from pydantic import BaseModel, Field

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
    created_at: datetime
    updated_at: datetime

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
    coordinates: list | None = None
    standard_reference: str | None = None
    pen_type: str
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
    comparison_method: Literal["rag", "rag_ai", "ai_vision", "hybrid"] = Field(
        "rag",
        description="Pipeline to use: rag, rag_ai (Gemini w/ CAD), ai_vision (Gemini image only), or hybrid (dual-generator cross-verification)"
    )

# Room workflow schemas
class RoomCreateRequest(BaseModel):
    name: str = Field(..., description="User-facing room label")
    description: str | None = None
    client_name: str | None = None
    comparison_method: Literal["rag", "rag_ai", "ai_vision", "hybrid"] = Field(
        "rag",
        description="Comparison pipeline for this room (dev-only)"
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
    comparison_method: Literal["rag", "rag_ai", "ai_vision", "hybrid"] = "rag"
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

AnnotationSeverity = Literal["info", "low", "medium", "high", "critical"]
AnnotationPenType = Literal["checker_blue", "amber_gold", "warning_orange", "alert_red", "resolved_green", "resolved_pink"]

class CreateAnnotationRequest(BaseModel):
    review_session_id: str = Field(..., description="Active review session or room id")
    drawing_id: str = Field(..., description="Drawing this annotation is pinned to")
    annotation_type: str = "pin"
    content: str
    severity: AnnotationSeverity = "info"
    coordinates: list[float] | None = Field(None, description="[x, y] world-space pin center")
    target_entity_ids: list[str] = Field(default_factory=list)
    violation_id: str | None = None
    pen_type: AnnotationPenType = "checker_blue"

class UpdateAnnotationRequest(BaseModel):
    content: str | None = None
    status: str | None = None
    severity: AnnotationSeverity | None = None
    coordinates: list[float] | None = None
    pen_type: AnnotationPenType | None = None

class AnnotationResponse(BaseModel):
    id: str
    review_session_id: str
    drawing_id: str
    author_id: str
    annotation_type: str
    content: str
    severity: AnnotationSeverity
    coordinates: list[float] | None = None
    target_entity_ids: list[str]
    violation_id: str | None = None
    status: str
    pen_type: AnnotationPenType
    created_at: datetime
    updated_at: datetime

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
    origin: Optional[Literal["deterministic", "ai_vision"]] = Field(default=None, description="Which generator produced this finding in the hybrid pipeline. None for markings from rag/rag_ai/ai_vision, which have a single source by construction.")
    verification: Optional[Literal["confirmed_both", "confirmed_single", "corrected_to_matched", "conflict", "unverified"]] = Field(default=None, description="Hybrid-pipeline outcome: confirmed_both = both generators agreed, confirmed_single = the two disagreed and the crop verifier picked a side, corrected_to_matched = the verifier looked at the actual crops and found no real difference at all, overriding whatever either generator originally claimed (status is forced to MATCHED), conflict = the verifier could not confirm either side, unverified = single-source finding not yet run through the verifier. None for markings from rag/rag_ai/ai_vision.")
    resolution_method: Optional[Literal["entity_handle", "visual_bbox_fallback", "unresolved"]] = Field(default=None, description="How `coordinates` was derived: exact entity-handle lookup, Gemini's normalized visual bbox mapped to CAD space, or not resolved at all.")
    feature: Optional[str] = Field(default=None, description="Sub-item taxonomy key within `category` (e.g. category='title_block', feature='scale') — see services/backend/infrastructure/audit/comparison/taxonomy.py for the canonical list per category. Used to group the checklist panel into named sub-sections instead of one flat list per category. Falls back to 'other' when unset or unrecognized.")

class CategoryAgreement(BaseModel):
    """
    Per-category generator agreement counts for the hybrid method (docs/hybrid-
    comparison-engine-implementation-plan.md, Phase 8) — a fixed-shape object, not a
    dict keyed by category name, for the same reason ComparisonDiagnostics itself isn't
    a bare dict below: Gemini's structured-output API rejects open-ended
    additionalProperties schemas, and this model nests inside PhysicalComparisonResponse
    which rag_ai/ai_vision also hand to Gemini as response_schema. A list of these,
    one entry per category that had any candidate from either generator, is the
    Gemini-safe equivalent of "a dict by category."
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

class ViewSummary(BaseModel):
    summary: str = Field(..., description="A detailed summary paragraph for this specific view category.")

class DrawingSummaryResponse(BaseModel):
    drawing_views: ViewSummary = Field(..., description="Origin, alignment, lines, dimensions, holes, chamfers, welds, tolerances, text attrs.")
    notes: ViewSummary = Field(..., description="Standard and special notes.")
    bom: ViewSummary = Field(..., description="Material type, specification, quantity, weight, balloons, remarks, numbering.")
    title_block: ViewSummary = Field(..., description="Machine name, line name, scale, designed by, drawn by, quantity, job/ref numbers, rev code.")
    iso_view: ViewSummary = Field(..., description="Orientation, scale, location.")
    others: ViewSummary = Field(..., description="Tree view properties/link, excel additional information.")
