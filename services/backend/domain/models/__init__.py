from .annotation_document import AnnotationDocument
from .audit import AuditResult
from .audit_feedback import AuditFeedbackDocument
from .audit_session import AuditSession
from .audit_violation import AuditViolation
from .client import ClientDocument
from .comparison import Comparison
from .drawing import Drawing
from .drawing_document import DrawingDocument
from .extracted_entity import ExtractedEntity
from .extraction_job import ExtractionJob
from .report import Report
from .role_permissions import RolePermissionsDocument
from .room import Room
from .standard import Standard
from .standard_chunk import StandardChunk
from .standard_document import StandardDocument
from .user_account import UserAccountDocument
from .user_session import UserSessionDocument
from .zone_template import ZoneTemplateDocument
from .ground_truth import GroundTruthMarking, ManualCheckSession

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
    AuditFeedbackDocument,
    UserAccountDocument,
    UserSessionDocument,
    RolePermissionsDocument,
    ClientDocument,
    Room,
    AnnotationDocument,
    ZoneTemplateDocument,
    ManualCheckSession,
    GroundTruthMarking,
]
