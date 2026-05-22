from pydantic import BaseModel, Field
from typing import Any, Optional, Generic, TypeVar

T = TypeVar("T")

class ErrorDetail(BaseModel):
    code: str = Field(..., description="Unique machine-readable uppercase error string")
    message: str = Field(..., description="Human-friendly descriptive error message")
    detail: Optional[Any] = Field(None, description="Optional diagnostic error properties or traceback")

class StandardResponse(BaseModel, Generic[T]):
    success: bool = Field(..., description="Indicates if the requested operation succeeded")
    data: Optional[T] = Field(None, description="Response payload")
    error: Optional[ErrorDetail] = Field(None, description="Populated error details if success is false")

class SystemStatusResponse(BaseModel):
    status: str = Field(..., description="E.g., healthy, degraded, offline")
    version: str
    name: str
    timestamp: float

class DatabaseHealthDetails(BaseModel):
    status: str
    latency_ms: float
    connected: bool
    database_name: Optional[str] = None
    error: Optional[str] = None

class StorageHealthDetails(BaseModel):
    status: str
    write_permission: bool
    storage_root: str
    disk_usage: dict
    directories: dict
    error: Optional[str] = None

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
    error_message: Optional[str] = None
    diagnostics: dict
    conversion_duration_seconds: Optional[float] = None
    parsing_duration_seconds: Optional[float] = None
    total_duration_seconds: Optional[float] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

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
    client_name: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
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
    standard_id: Optional[str] = None
    client_name: Optional[str] = None

class AuditSessionResponse(BaseModel):
    id: str
    drawing_id: str
    standard_id: Optional[str] = None
    client_name: Optional[str] = None
    status: str
    compliance_score: Optional[float] = None
    confidence_score: Optional[float] = None
    error_message: Optional[str] = None
    timings: dict
    diagnostics: dict
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

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
    coordinates: Optional[list] = None
    standard_reference: Optional[str] = None
    pen_type: str
    is_resolved: bool
    resolved_at: Optional[datetime] = None
    checker_remarks: Optional[str] = None
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
    active: Optional[bool] = None
    role: Optional[str] = None
    password: Optional[str] = None

