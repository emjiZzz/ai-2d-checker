import contextvars
import json
import logging
import sys
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .config import settings

# Thread-safe context variable for request correlation IDs
correlation_id_var = contextvars.ContextVar("correlation_id", default=None)

class SafeRedactor:
    """
    Utility helper to search and redact sensitive variables/tokens from log statements.
    """
    @staticmethod
    def redact(message: str) -> str:
        if not isinstance(message, str):
            return str(message)
        
        # Dynamically redact settings credentials if defined
        try:
            if settings.API_TOKEN and settings.API_TOKEN in message:
                message = message.replace(settings.API_TOKEN, "********")
            if settings.GEMINI_API_KEY and settings.GEMINI_API_KEY in message:
                message = message.replace(settings.GEMINI_API_KEY, "********")
            if settings.OPENAI_API_KEY and settings.OPENAI_API_KEY in message:
                message = message.replace(settings.OPENAI_API_KEY, "********")
        except Exception:
            pass  # Avoid circular load crashes during bootstrap
        return message

class JSONFormatter(logging.Formatter):
    """
    Structured JSON Formatter for production audit trail and machine scraping.
    """
    def format(self, record: logging.LogRecord) -> str:
        clean_msg = SafeRedactor.redact(record.getMessage())
        
        log_object = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": clean_msg,
            "filename": record.filename,
            "line_number": record.lineno,
        }
        
        # Inject context correlation ID if available
        correlation_id = correlation_id_var.get()
        if correlation_id:
            log_object["correlation_id"] = correlation_id
            
        if record.exc_info:
            log_object["exception"] = self.formatException(record.exc_info)
            
        return json.dumps(log_object)

class ConsoleFormatter(logging.Formatter):
    """
    Developer-friendly formatted console logger with secret redaction and correlation ID tags.
    """
    def format(self, record: logging.LogRecord) -> str:
        clean_msg = SafeRedactor.redact(record.getMessage())
        corr_id = correlation_id_var.get()
        corr_str = f" [{corr_id}]" if corr_id else ""
        
        asctime = self.formatTime(record, "%H:%M:%S")
        return f"[{asctime}]{corr_str} [{record.levelname}] ({record.name}) {clean_msg}"

def setup_logger() -> logging.Logger:
    logger = logging.getLogger("ai_2d_checker")
    logger.setLevel(getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO))
    
    # Block duplicate handlers during fast api reloads
    if logger.handlers:
        return logger

    # Strictly output to logs/backend hierarchy
    log_dir = Path(settings.STORAGE_ROOT) / "logs" / "backend"
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # 1. Stdout Console Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(ConsoleFormatter())
    logger.addHandler(console_handler)
    
    # 2. Production-hardened Rotating JSON File Handler
    import os
    pid = os.getpid()
    log_file = log_dir / f"backend_{pid}.log"
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=5 * 1024 * 1024,  # 5 Megabytes
        backupCount=5,
        encoding="utf-8"
    )
    file_handler.setFormatter(JSONFormatter())
    logger.addHandler(file_handler)
    
    return logger

logger = setup_logger()
