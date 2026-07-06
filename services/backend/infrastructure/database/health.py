import time

from ...logger import logger
from .connection import db_manager


async def check_database_health() -> dict:
    """
    Run diagnostic latency roundtrip tests against the local database engine.
    """
    if not db_manager.is_connected or db_manager.client is None:
        logger.info("Database connection not active. Attempting dynamic diagnostic reconnect...")
        success = await db_manager.connect(max_retries=1, initial_delay=0.1)
        if not success:
            return {
                "status": "unreachable",
                "latency_ms": -1,
                "connected": False,
                "error": "MongoDB connection has not been initialized."
            }

    start_time = time.time()
    try:
        # Perform dynamic latency ping
        await db_manager.client.admin.command("ping")
        latency_ms = (time.time() - start_time) * 1000
        
        return {
            "status": "healthy",
            "latency_ms": round(latency_ms, 2),
            "connected": True,
            "database_name": db_manager.db.name if db_manager.db is not None else None
        }
    except Exception as e:
        logger.warning(f"Database latency healthcheck failed: {str(e)}")
        return {
            "status": "degraded",
            "latency_ms": -1,
            "connected": False,
            "error": str(e)
        }
