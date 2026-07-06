from typing import Any, TypeVar

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

