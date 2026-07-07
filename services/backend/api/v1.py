import time
from fastapi import APIRouter
from ..config import settings
from .routers import auth, drawings, standards, audits, copilot, analytics
from .schemas import StandardResponse, SystemStatusResponse
from ..infrastructure.database.health import check_database_health
from ..infrastructure.storage.storage_health import get_storage_diagnostics

router = APIRouter(prefix="/api/v1")


@router.get(
    "/health",
    response_model=StandardResponse[SystemStatusResponse],
    summary="Global health status checker"
)
async def global_health():
    """
    Diagnostic healthcheck endpoint. Returns system and sidecar status details.
    Does not require authentication to allow the frontend connection manager to check connectivity.
    """
    db_health = await check_database_health()
    storage_diag = get_storage_diagnostics()
    
    return StandardResponse(
        success=True,
        data=SystemStatusResponse(
            status="healthy" if db_health["connected"] and storage_diag["write_permission"] else "degraded",
            version=settings.VERSION,
            name=settings.PROJECT_NAME,
            timestamp=time.time()
        )
    )

# Register sub-routers under the main v1 path
router.include_router(auth.router)
router.include_router(drawings.router)
router.include_router(standards.router)
router.include_router(audits.router)
router.include_router(copilot.router)
router.include_router(analytics.router)
