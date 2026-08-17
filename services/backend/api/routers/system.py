import time
from fastapi import APIRouter, Depends
from ..dependencies import get_auth_token
from ..schemas import StandardResponse
from ...infrastructure.database.connection import db_manager
from ...infrastructure.database.health import check_database_health
from ...infrastructure.storage.storage_health import get_storage_diagnostics

router = APIRouter(prefix="/system", tags=["System & Admin Metrics"])


@router.get(
    "/database",
    response_model=StandardResponse[dict],
    summary="Get Database System Metrics",
    dependencies=[Depends(get_auth_token)]
)
async def get_system_database_metrics():
    """
    Returns database connection and health metrics for the admin dashboard.
    """
    health = await check_database_health()
    mode = "disconnected"
    if db_manager.is_connected:
        mode = "local_fallback" if db_manager.is_fallback else "cloud_primary"

    return StandardResponse(
        success=True,
        data={
            "connected": db_manager.is_connected,
            "mode": mode,
            "is_fallback": db_manager.is_fallback,
            "health": health,
            "timestamp": time.time()
        }
    )


@router.get(
    "/storage",
    response_model=StandardResponse[dict],
    summary="Get Storage System Metrics",
    dependencies=[Depends(get_auth_token)]
)
async def get_system_storage_metrics():
    """
    Returns filesystem and storage diagnostics for the admin dashboard.
    """
    diag = get_storage_diagnostics()
    return StandardResponse(
        success=True,
        data={
            "storage": diag,
            "timestamp": time.time()
        }
    )
