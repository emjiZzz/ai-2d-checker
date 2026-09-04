import time
from fastapi import APIRouter, Depends, status
from ..dependencies import get_auth_token
from ...infrastructure.database.connection import db_manager
from ...infrastructure.database.sync_manager import sync_manager
from ...infrastructure.database.health import check_database_health
from ..schemas import StandardResponse

router = APIRouter(prefix="/database", tags=["Database & Cloud Sync"])


@router.get(
    "/status",
    response_model=StandardResponse[dict],
    summary="Get Database Connection & Cloud Sync Status",
    dependencies=[Depends(get_auth_token)]
)
async def get_database_status():
    """
    Returns the current database connection state (Cloud Primary vs Local Fallback)
    and sync diagnostics.
    """
    db_health = await check_database_health()
    sync_status = sync_manager.get_status()

    mode = "disconnected"
    if db_manager.is_connected:
        mode = "local_fallback" if db_manager.is_fallback else "cloud_primary"

    storage_stats = {
        "data_size_mb": 0.0,
        "storage_size_mb": 0.0,
        "objects_count": 0,
        "limit_mb": 512.0,
        "usage_percent": 0.0,
        "is_free_tier": True,
        "tier_name": "MongoDB Atlas M0 (Free Tier)",
        "is_warning": False,
    }

    if db_manager.is_connected and db_manager.db is not None:
        try:
            raw_stats = await db_manager.db.command("dbStats")
            data_size_bytes = raw_stats.get("dataSize", 0)
            storage_size_bytes = raw_stats.get("storageSize", 0)
            objects_count = raw_stats.get("objects", 0)

            data_size_mb = round(data_size_bytes / (1024 * 1024), 2)
            storage_size_mb = round(storage_size_bytes / (1024 * 1024), 2)
            limit_mb = 512.0  # Free tier default quota
            usage_percent = round((data_size_mb / limit_mb) * 100, 1)

            is_cloud = bool(db_manager.active_uri and "mongodb+srv://" in db_manager.active_uri)

            storage_stats = {
                "data_size_mb": data_size_mb,
                "storage_size_mb": storage_size_mb,
                "objects_count": objects_count,
                "limit_mb": limit_mb if is_cloud else None,
                "usage_percent": usage_percent if is_cloud else None,
                "is_free_tier": is_cloud and (limit_mb == 512.0),
                "tier_name": "MongoDB Atlas M0 (Free Tier - 512MB Limit)" if is_cloud else "Local MongoDB Server (Unlimited)",
                "is_warning": is_cloud and (usage_percent >= 60.0 or data_size_mb >= 300.0),
            }
        except Exception:
            pass

    return StandardResponse(
        success=True,
        data={
            "connected": db_manager.is_connected,
            "mode": mode,
            "is_fallback": db_manager.is_fallback,
            "active_uri": db_manager.active_uri.split("@")[-1] if db_manager.active_uri else None,
            "health": db_health,
            "storage": storage_stats,
            "sync": sync_status,
            "timestamp": time.time()
        }
    )


@router.post(
    "/sync",
    response_model=StandardResponse[dict],
    summary="Trigger Manual Database Sync Between Local and Cloud",
    dependencies=[Depends(get_auth_token)]
)
async def trigger_database_sync():
    """
    Triggers an immediate bidirectional sync between Local MongoDB and Cloud MongoDB.
    """
    result = await sync_manager.sync_all(force=True)
    return StandardResponse(
        success=result.get("success", False),
        data=result
    )
