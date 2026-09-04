from fastapi import APIRouter, Depends
from pydantic import BaseModel
from ...domain.models.audit_session import AuditSession
from ...domain.models.audit_violation import AuditViolation
from ...domain.models.drawing_document import DrawingDocument
from ..dependencies import get_auth_token
from ..schemas import StandardResponse

router = APIRouter()


class AnalyticsTrendPoint(BaseModel):
    timestamp: float
    session_id: str
    drawing_name: str
    compliance_score: float
    violations_count: int


@router.get(
    "/analytics/compliance-trends",
    response_model=StandardResponse[list[AnalyticsTrendPoint]],
    summary="Retrieve standard compliance trends over time for analytics charts",
    dependencies=[Depends(get_auth_token)]
)
async def get_compliance_trends(limit: int = 20):
    """
    Queries historical completed AuditSessions and maps compliance trends
    suitable for UI line charts and dashboards.
    """
    sessions = await AuditSession.find(
        AuditSession.status == "completed"
    ).sort(-AuditSession.completed_at).limit(limit).to_list()

    trend_points = []
    for s in reversed(sessions):  # Chronological order
        drawing = await DrawingDocument.get(s.drawing_id)
        # Count violations
        v_count = await AuditViolation.find(AuditViolation.audit_session_id == str(s.id)).count()
        trend_points.append(
            AnalyticsTrendPoint(
                timestamp=s.completed_at.timestamp() if s.completed_at else s.started_at.timestamp(),
                session_id=str(s.id),
                drawing_name=drawing.file_name if drawing else "Unknown Drawing",
                compliance_score=s.compliance_score,
                violations_count=v_count
            )
        )

    return StandardResponse(success=True, data=trend_points)
