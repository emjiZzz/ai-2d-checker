import asyncio
import time

from ...logger import logger
from .connection import db_manager

PING_TIMEOUT_SEC = 5.0


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
        # Bounded rather than bare: this endpoint needs no token and the desktop client polls it
        # to decide whether to fail over, so a ping that hangs takes the failover with it.
        await asyncio.wait_for(
            db_manager.client.admin.command("ping"), timeout=PING_TIMEOUT_SEC
        )
        latency_ms = (time.time() - start_time) * 1000
        
        return {
            "status": "healthy",
            "latency_ms": round(latency_ms, 2),
            "connected": True,
            "database_name": db_manager.db.name if db_manager.db is not None else None
        }
    except TimeoutError:
        logger.warning(
            f"Database healthcheck ping exceeded {PING_TIMEOUT_SEC}s; reporting degraded."
        )
        return {
            "status": "degraded",
            "latency_ms": -1,
            "connected": False,
            "error": f"ping timed out after {PING_TIMEOUT_SEC}s",
        }
    except Exception as e:
        logger.warning(f"Database latency healthcheck failed: {str(e)}")
        return {
            "status": "degraded",
            "latency_ms": -1,
            "connected": False,
            "error": str(e)
        }
