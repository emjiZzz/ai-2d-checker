import os
import secrets
from pathlib import Path
from fastapi import Header, HTTPException, status
from ..config import settings
from ..logger import logger

# Secure Config & API Token Management
TOKEN_FILE_NAME = ".api-token"

def initialize_local_api_token() -> str:
    """
    Returns the local security authentication token.
    If none is set in env variables, generates a cryptographically secure token
    and writes it to storage/secure/ for Tauri client retrieval.
    """
    token = settings.API_TOKEN
    
    # Ensure storage/secure folder exists
    secure_dir = Path(settings.STORAGE_ROOT) / "secure"
    secure_dir.mkdir(parents=True, exist_ok=True)
    token_file = secure_dir / TOKEN_FILE_NAME

    if not token:
        if token_file.exists():
            try:
                encrypted_content = token_file.read_text(encoding="utf-8").strip()
                from .encryption import encryptor
                token = encryptor.decrypt(encrypted_content)
                logger.info("Loaded and decrypted persisted dynamic API Token from secure local storage.")
            except Exception as e:
                logger.error(f"Failed to read or decrypt persisted token: {str(e)}")

        if not token:
            token = secrets.token_hex(32)
            try:
                from .encryption import encryptor
                encrypted_content = encryptor.encrypt(token)
                # Restrict permissions on Windows/Unix where possible
                token_file.write_text(encrypted_content, encoding="utf-8")
                logger.info(f"Generated secure encrypted dynamic API Token saved to: {token_file}")
            except Exception as e:
                logger.error(f"Failed to encrypt and persist dynamically generated API Token: {str(e)}")

    # Update config settings with active token
    settings.API_TOKEN = token
    return token

def verify_api_token(authorization: str | None = Header(None, description="API Security Bearer Token")) -> str:
    """
    FastAPI dependency validating requests contain the exact matching localhost token.
    Rejects unauthorized queries with 401.
    """
    if not settings.API_TOKEN:
        # If token was not initialized, initialize it now
        initialize_local_api_token()

    if not authorization:
        logger.warning("Rejected API request: Missing Authorization header.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access Denied: Missing Authorization Header."
        )

    expected_prefix = "Bearer "
    if not authorization.startswith(expected_prefix):
        logger.warning("Rejected API request: Authorization header missing Bearer prefix.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication scheme. Bearer prefix required."
        )

    provided_token = authorization[len(expected_prefix):].strip()
    if not secrets.compare_digest(provided_token, settings.API_TOKEN or ""):
        logger.warning("Rejected API request: Unauthorized API Token provided.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access Denied: Invalid security API Token."
        )

    return provided_token

# Dual-Layer Path Traversal Protection
def validate_sandboxed_path(user_path: str | Path) -> Path:
    """
    Canonical absolute path resolver. Validates path stays bounded inside the storage root directory.
    Blocks all path traversal attempts (../), symlink escapes, and invalid absolute outside boundaries.
    """
    storage_root = Path(settings.STORAGE_ROOT).resolve()
    target_path = Path(user_path).resolve()
    
    # 1. Traversal check: check target resolved absolute path starts strictly with storage_root
    try:
        # Check if target_path is inside storage_root
        target_path.relative_to(storage_root)
    except ValueError:
        logger.error(
            f"Path Traversal Attempt Blocked: Resolved path '{target_path}' "
            f"escapes storage root boundary '{storage_root}'."
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Access Denied: Path escapes the sandboxed workspace directory."
        )

    # 2. Block direct traversal strings in path
    if ".." in str(user_path):
        logger.error(f"Path Traversal Attempt Blocked: Path contains invalid traversal operators: {user_path}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Access Denied: Path contains illegal traversal operators."
        )

    return target_path

# Secret Masking Utilities
def mask_secret(value: str | None) -> str:
    """
    Mask sensitive secrets (e.g. Gemini key or local token) before writing to diagnostics logs.
    """
    if not value:
        return "None"
    if len(value) <= 8:
        return "********"
    return f"{value[:4]}...{value[-4:]}"
