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
    comparison_method: Literal["rag", "rag_ai", "ai_vision"] = Field(
        "rag",
        description="Pipeline to use: rag, rag_ai (Gemini w/ CAD), or ai_vision (Gemini image only)"
    )

# Room workflow schemas
class RoomCreateRequest(BaseModel):
    name: str = Field(..., description="User-facing room label")
    description: str | None = None
    client_name: str | None = None
    comparison_method: Literal["rag", "rag_ai", "ai_vision"] = Field(
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
    comparison_method: Literal["rag", "rag_ai", "ai_vision"] = "rag"
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
    status: Literal["MATCHED", "CHANGED", "ADDED", "REMOVED"] = Field(..., description="Audit status for this specific text marking.")
    details: str = Field(..., description="Short explanation of the check result for this element.")
    category: Literal["drawing_views", "notes_section", "bill_of_materials", "title_block", "isometric_view"] = Field(
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
