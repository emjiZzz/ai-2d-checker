from .drawing import Drawing
from .audit import AuditResult
from .comparison import Comparison
from .report import Report
from .standard import Standard
from .drawing_document import DrawingDocument
from .extraction_job import ExtractionJob
from .extracted_entity import ExtractedEntity
from .standard_document import StandardDocument
from .standard_chunk import StandardChunk
from .audit_session import AuditSession
from .audit_violation import AuditViolation
from .user_account import UserAccountDocument
from .user_session import UserSessionDocument
from .role_permissions import RolePermissionsDocument

# Document list for typed Beanie initialization mapping
__all_models__ = [
    Drawing,
    AuditResult,
    Comparison,
    Report,
    Standard,
    DrawingDocument,
    ExtractionJob,
    ExtractedEntity,
    StandardDocument,
    StandardChunk,
    AuditSession,
    AuditViolation,
    UserAccountDocument,
    UserSessionDocument,
    RolePermissionsDocument
]
