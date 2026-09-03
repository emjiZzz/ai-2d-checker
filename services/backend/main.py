import asyncio
import logging
import sys
import time

from fastapi import FastAPI, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import settings
from .logger import logger

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# Suppress repetitive 200 OK /health logs from standard Uvicorn access stream
class HealthCheckLogFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        return not ("/health" in msg and "200" in msg)

logging.getLogger("uvicorn.access").addFilter(HealthCheckLogFilter())

# Import Phase 2 Core and Infrastructure
from .api.middleware import (
    CorrelationIDMiddleware,
    ExceptionLoggingMiddleware,
    RequestDurationMiddleware,
)
from .api.v1 import router as api_v1_router
from .core.security import initialize_local_api_token
from .infrastructure.database.connection import db_manager
from .infrastructure.database.health import check_database_health
from .infrastructure.database.indexes import bootstrap_indexes
from .infrastructure.storage.path_resolver import bootstrap_storage
from .infrastructure.storage.storage_health import get_storage_diagnostics

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Offline-first secure local drawing validation and compliance backend"
)

# Add Phase 2 Hardened Middlewares in order
app.add_middleware(ExceptionLoggingMiddleware)
app.add_middleware(RequestDurationMiddleware)
app.add_middleware(CorrelationIDMiddleware)

# Configure CORS - Allowed scopes for local Tauri client
app.add_middleware(
    CORSMiddleware,
    # A packaged Tauri app presents `tauri://localhost` (Windows) or `http://tauri.localhost`,
    # NOT the backend's own address — so serving a LAN needs no per-server origin, and these
    # three cover every installed client regardless of which machine the backend runs on.
    #
    # `CORS_ORIGINS` exists for anything else (a browser pointed at the server, a second client).
    # Added to the defaults, never replacing them, so an installed app keeps working whatever the
    # variable says.
    allow_origins=[
        "http://localhost:1420",     # Vite dev server standard Tauri
        "tauri://localhost",         # Production Tauri Windows
        "http://tauri.localhost",    # Production Tauri Linux/macOS
    ] + [o.strip() for o in (settings.CORS_ORIGINS or "").split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Middleware: Host verification.
#
# The hostname is matched EXACTLY. A previous version accepted any Host that merely *started
# with* an allowed value, which let `localhost.attacker.com` through — precisely the DNS-rebinding
# case this check exists to stop. Do not reintroduce a prefix/substring match here.
#
# ## Serving a LAN
#
# The default stays loopback-only, so a developer checkout and any existing deployment behave
# exactly as before. `ALLOWED_HOSTS` adds names for the shared-server deployment, e.g.
#
#     ALLOWED_HOSTS=192.168.200.105,kmti-server
#
# ⚠ Names are ADDED to the loopback set, never replace it: the server must keep answering its own
# health checks and anything running on the box. And each entry is matched exactly by the same
# rule above — a wildcard here would hand back the DNS-rebinding hole the exact match closed.
_EXTRA_ALLOWED_HOSTS = {
    h.strip().lower()
    for h in (settings.ALLOWED_HOSTS or "").split(",")
    if h.strip()
}
ALLOWED_HOST_NAMES = frozenset({"localhost", "127.0.0.1", "::1"} | _EXTRA_ALLOWED_HOSTS)


def _hostname_of(host_header: str) -> str:
    """Reduce a Host header to its bare hostname, lowercased.

    The port is deliberately not validated: it is the port we are already listening on, so it
    carries no authorization meaning, and pinning it would break any run under a non-default
    SIDECAR_PORT. The hostname is the part an attacker controls, so that is the part checked.
    """
    host = host_header.strip().lower()
    if host.startswith("["):                       # bracketed IPv6, e.g. [::1]:8080
        return host[1:].split("]", 1)[0]
    return host.rsplit(":", 1)[0] if host.count(":") == 1 else host


@app.middleware("http")
async def verify_host(request: Request, call_next):
    host_header = request.headers.get("host", "")

    if _hostname_of(host_header) not in ALLOWED_HOST_NAMES:
        logger.warning(f"Rejected request with unauthorized Host header: {host_header}")
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"detail": "Access Forbidden: Standalone backend only accepts localhost requests."}
        )

    return await call_next(request)

@app.on_event("startup")
async def startup_event() -> None:
    logger.info(f"Starting {settings.PROJECT_NAME} v{settings.VERSION}")
    
    # A. Path traversal / Storage root bootstrap
    if not bootstrap_storage():
        logger.critical("Storage infrastructure bootstrap failed. Exiting startup process.")
        raise RuntimeError("Failed to bootstrap storage directories.")
        
    # B. Security Core: Initialize Dynamic Local Auth API Token
    initialize_local_api_token()
    
    # C. MongoDB Connection with Motor + Beanie
    # If MongoDB is down, we operate in disconnected fallback mode
    db_success = await db_manager.connect(max_retries=3, initial_delay=1.0)
    if db_success:
        # D. Index bootstrapping
        await bootstrap_indexes()

        # D2. Retrieval indexes (R1, ADR-008). Builds only collections with no usable index,
        # so a normal restart costs nothing. Never fatal — the app serves without retrieval,
        # and `retrieval.query()` reports a missing index rather than returning [] as though
        # it had searched.
        # Imported here rather than at module scope, matching section E below: startup
        # imports are deferred so that importing `main` stays cheap and side-effect free.
        from .infrastructure.retrieval.service import bootstrap_retrieval_indexes  # noqa: PLC0415

        for collection, result in (await bootstrap_retrieval_indexes()).items():
            if result.built:
                logger.info(f"[retrieval] Built '{collection}': {result.n_records} record(s).")
            else:
                logger.info(f"[retrieval] '{collection}' not built: {result.reason}.")
                
        # D3. Cloud & Local Database Auto-Sync Worker
        from .infrastructure.database.sync_manager import sync_manager
        sync_manager.start()
    else:
        logger.warning("FastAPI backend is operating in offline/disconnected fallback mode.")

    # E. Start Background CAD Processing Queue worker
    from .infrastructure.audit.audit_pipeline import audit_queue
    from .infrastructure.cad.processing_queue import processing_queue
    from .infrastructure.cad.summarization_queue import summarization_queue
    processing_queue.start()
    audit_queue.start()
    summarization_queue.start()
    await processing_queue.recover_orphaned_jobs()

@app.on_event("shutdown")
async def shutdown_event() -> None:
    logger.info("Shutting down Standalone FastAPI Backend...")
    # Safe shutdown cleanup of background auto-sync worker
    try:
        from .infrastructure.database.sync_manager import sync_manager
        await sync_manager.stop()
    except Exception as e:
        logger.warning(f"Error stopping database sync manager: {e}")

    # Safe shutdown cleanup of database client
    await db_manager.disconnect()
    
    # Graceful stop of background CAD processing worker
    from .infrastructure.audit.audit_pipeline import audit_queue
    from .infrastructure.cad.processing_queue import processing_queue
    from .infrastructure.cad.summarization_queue import summarization_queue
    await processing_queue.stop()
    await audit_queue.stop()
    await summarization_queue.stop()
    
    logger.info("Graceful cleanup of system hooks completed.")

# Include standard v1 routes
app.include_router(api_v1_router)

@app.get("/")
@app.head("/")
async def root_ping() -> dict:
    """Root discovery endpoint for load balancers and platform probers."""
    return {
        "status": "online",
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "docs": "/docs",
        "health": "/health"
    }

@app.get("/health")
async def health_check(response: Response) -> dict:
    """
    Diagnostic healthcheck endpoint. Returns service state details.
    Returns HTTP 503 Service Unavailable when the database is disconnected or storage
    is unwritable, preventing cloud platforms (like Render) from falsely reporting a broken
    deployment as live.
    """
    # Repair the installed-client token if it has gone missing since startup. This endpoint is
    # the right place for exactly two reasons: it needs no token itself (so it still works in the
    # very state that needs repairing), and the desktop client already polls it every few
    # seconds. A missing token is otherwise invisible -- /health keeps answering 200, so the app
    # reports itself CONNECTED while every authenticated call 401s, which is precisely how this
    # was shipped twice. Cheap: a stat, and a write only when the file is actually absent.
    from .core.security import ensure_token_published

    ensure_token_published()

    db_health = await check_database_health()
    storage_diag = get_storage_diagnostics()
    
    is_healthy = bool(db_health["connected"] and storage_diag["write_permission"])
    if not is_healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        "status": "healthy" if is_healthy else "degraded",
        "version": settings.VERSION,
        "name": settings.PROJECT_NAME,
        "timestamp": time.time(),
        "services": {
            "mongodb": db_health["connected"],
            "storage_root": storage_diag["write_permission"],
            "gemini_api": settings.GEMINI_API_KEY is not None and settings.GEMINI_API_KEY != "YOUR_GEMINI_API_KEY_HERE",
            "openai_api": settings.OPENAI_API_KEY is not None and settings.OPENAI_API_KEY != "YOUR_OPENAI_API_KEY_HERE"
        }
    }
