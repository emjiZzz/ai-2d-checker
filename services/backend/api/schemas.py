from typing import Any, TypeVar, Optional

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
    session_token: str = Field(..., description="AES-256 encrypted active session identifier")
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

class UpdateUserRequest(BaseModel):
    active: bool | None = None
    role: str | None = None
    password: str | None = None

class PhysicalComparisonRequest(BaseModel):
    reference_drawing_id: str
    drawing_id: str

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

from typing import Literal

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

class PhysicalComparisonResponse(BaseModel):
    drawing_views: CategoryComparison
    notes_section: CategoryComparison
    bill_of_materials: CategoryComparison
    title_block: CategoryComparison
    isometric_view: CategoryComparison
    other_engineering_references: CategoryComparison
    canvas_markings: list[CanvasMarking] = Field(default_factory=list, description="Visual checklist coordinates mapping items.")



