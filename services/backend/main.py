import time
import sys
import asyncio
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from .config import settings
from .logger import logger

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# Import Phase 2 Core and Infrastructure
from .core.security import initialize_local_api_token
from .infrastructure.storage.path_resolver import bootstrap_storage
from .infrastructure.database.connection import db_manager
from .infrastructure.database.indexes import bootstrap_indexes
from .api.middleware import CorrelationIDMiddleware, RequestDurationMiddleware, ExceptionLoggingMiddleware
from .api.v1 import router as api_v1_router
from .infrastructure.database.health import check_database_health
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
    allow_origins=[
        "http://localhost:1420",     # Vite dev server standard Tauri
        "tauri://localhost",         # Production Tauri Windows
        "http://tauri.localhost",    # Production Tauri Linux/macOS
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Middleware: Host verification to strictly enforce localhost-only binding
@app.middleware("http")
async def verify_host(request: Request, call_next):
    host_header = request.headers.get("host", "")
    
    # Strictly permit loopback bindings only to block public network proxies
    allowed_hosts = ["localhost", "127.0.0.1", f"localhost:{settings.PORT}", f"127.0.0.1:{settings.PORT}"]
    
    if host_header not in allowed_hosts and not any(host_header.startswith(h) for h in allowed_hosts):
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
    else:
        logger.warning("FastAPI backend is operating in offline/disconnected fallback mode.")

    # E. Start Background CAD Processing Queue worker
    from .infrastructure.cad.processing_queue import processing_queue
    from .infrastructure.audit.audit_pipeline import audit_queue
    processing_queue.start()
    audit_queue.start()

@app.on_event("shutdown")
async def shutdown_event() -> None:
    logger.info("Shutting down Standalone FastAPI Backend...")
    # Safe shutdown cleanup of database client
    await db_manager.disconnect()
    
    # Graceful stop of background CAD processing worker
    from .infrastructure.cad.processing_queue import processing_queue
    from .infrastructure.audit.audit_pipeline import audit_queue
    await processing_queue.stop()
    await audit_queue.stop()
    
    logger.info("Graceful cleanup of system hooks completed.")

# Include standard v1 routes
app.include_router(api_v1_router)

@app.get("/health")
async def health_check() -> dict:
    """
    Diagnostic healthcheck endpoint. Returns service state details.
    """
    db_health = await check_database_health()
    storage_diag = get_storage_diagnostics()
    
    return {
        "status": "healthy" if db_health["connected"] and storage_diag["write_permission"] else "degraded",
        "version": settings.VERSION,
        "name": settings.PROJECT_NAME,
        "timestamp": time.time(),
        "services": {
            "mongodb": db_health["connected"],
            "storage_root": storage_diag["write_permission"],
            "gemini_api": settings.GEMINI_API_KEY is not None and settings.GEMINI_API_KEY != "YOUR_GEMINI_API_KEY_HERE"
        }
    }
