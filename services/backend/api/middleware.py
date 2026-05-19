import time
import uuid
from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from ..logger import logger, correlation_id_var

class CorrelationIDMiddleware(BaseHTTPMiddleware):
    """
    Middleware that generates/extracts a unique correlation ID for each incoming request,
    stores it in contextvars for logging, and returns it in the X-Correlation-ID response header.
    """
    async def dispatch(self, request: Request, call_next) -> Response:
        # Extract correlation ID from headers or generate new one
        corr_id = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())
        
        # Set token in context var
        token = correlation_id_var.set(corr_id)
        
        try:
            response = await call_next(request)
            response.headers["X-Correlation-ID"] = corr_id
            return response
        finally:
            correlation_id_var.reset(token)

class RequestDurationMiddleware(BaseHTTPMiddleware):
    """
    Middleware that measures the request execution time and logs standard access metrics.
    """
    async def dispatch(self, request: Request, call_next) -> Response:
        start_time = time.time()
        
        response = await call_next(request)
        
        duration = time.time() - start_time
        logger.info(
            f"Access: {request.method} {request.url.path} - "
            f"Status: {response.status_code} - "
            f"Duration: {duration:.4f}s"
        )
        response.headers["X-Process-Time"] = f"{duration:.4f}s"
        return response

class ExceptionLoggingMiddleware(BaseHTTPMiddleware):
    """
    Global exception handler middleware. Captures any unhandled exceptions,
    logs them with traceback in JSON, and returns a unified JSON error payload.
    """
    async def dispatch(self, request: Request, call_next) -> Response:
        try:
            return await call_next(request)
        except Exception as e:
            logger.exception(f"Unhandled API error while processing '{request.url.path}': {str(e)}")
            
            # Unified error response format
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={
                    "success": False,
                    "error": {
                        "code": "INTERNAL_SERVER_ERROR",
                        "message": "An unexpected error occurred on the local server.",
                        "detail": str(e)
                    }
                }
            )
