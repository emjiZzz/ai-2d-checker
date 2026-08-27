import os
import sys
from pathlib import Path
import pytest
from fastapi import HTTPException

# Add services package to PYTHONPATH dynamically
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.backend.core.security import validate_sandboxed_path, initialize_local_api_token, verify_api_token
from services.backend.core.encryption import AES256GCM
from services.backend.infrastructure.storage.path_resolver import bootstrap_storage, get_storage_root
from services.backend.infrastructure.database.connection import DatabaseConnectionManager
from services.backend.config import settings

def test_config_validation():
    """
    Test standard configuration settings load correctly.
    """
    assert settings.PROJECT_NAME is not None
    assert settings.VERSION is not None
    assert settings.STORAGE_ROOT is not None

def test_encryption_roundtrip():
    """
    Test AES-256-GCM encryption/decryption helper functions.
    Ensures that data is correctly encrypted/decrypted and matches original payload.
    """
    cipher = AES256GCM()
    secret = "SuperSecret_Key123!?"
    
    # 1. Run encryption
    encrypted = cipher.encrypt(secret)
    assert encrypted != secret
    assert len(encrypted) > 0
    
    # 2. Run decryption
    decrypted = cipher.decrypt(encrypted)
    assert decrypted == secret

def test_path_traversal_rejection():
    """
    Test that sandboxed path traversal checks correctly reject illegal operations.
    """
    root = get_storage_root()
    bootstrap_storage()
    
    # 1. Valid paths inside root should pass
    valid_path = root / "uploads" / "drawing.dwg"
    resolved = validate_sandboxed_path(valid_path)
    assert resolved.resolve() == valid_path.resolve()
    
    # 2. Paths with '..' escaping the sandbox should be rejected
    escape_path = root / ".." / "unauthorized.txt"
    with pytest.raises(HTTPException) as exc_info:
        validate_sandboxed_path(escape_path)
    assert exc_info.value.status_code == 400

    # 3. Path strings containing literal '..' should be rejected
    literal_escape = "./storage/uploads/../../etc/passwd"
    with pytest.raises(HTTPException) as exc_info_lit:
        validate_sandboxed_path(literal_escape)
    assert exc_info_lit.value.status_code == 400

def test_storage_bootstrap():
    """
    Test directory bootstrapping and write permission checks.
    """
    success = bootstrap_storage()
    assert success is True
    
    root = get_storage_root()
    assert (root / "uploads").exists()
    assert (root / "secure").exists()
    assert (root / "temp").exists()
    assert (root / "logs" / "backend").exists()
    assert (root / "logs" / "app").exists()

@pytest.mark.asyncio
async def test_database_retry_handling():
    """Retry limits and exponential backoff, with no reachable database of either kind.

    ⚠ **Both URIs have to be dead, not just the primary.** `connect()` tries `MONGO_URI` and then
    falls back to `MONGO_FALLBACK_URI`, which defaults to `mongodb://127.0.0.1:27017` — the local
    MongoDB most developers here have running. Pointing only the primary at a dead port therefore
    asserted "the connection failed" on a machine where it had just succeeded through the
    fallback, so this test passed or failed according to whether `mongod` was up. That is the
    environment-dependence this repo has paid for before: a red test for a reason unrelated to the
    code under test.
    """
    manager = DatabaseConnectionManager()

    old_uri, old_fallback = settings.MONGO_URI, settings.MONGO_FALLBACK_URI
    # Two DIFFERENT dead ports, so the fallback is a genuinely separate candidate -- `connect`
    # skips it when it matches the primary, which would leave only one attempt to count.
    settings.MONGO_URI = "mongodb://127.0.0.1:9999"
    settings.MONGO_FALLBACK_URI = "mongodb://127.0.0.1:9998"

    try:
        success = await manager.connect(max_retries=2, initial_delay=0.1)
        assert success is False
        assert manager.is_connected is False
        # The counters ACCUMULATE across candidates rather than resetting per URI, so two dead
        # candidates at two retries each is four. Written as the product rather than as `4` so
        # the assertion says which quantity it is checking -- `max_retries` is honoured per
        # candidate, which is the actual contract, and a bare 4 would hide a change in either
        # factor behind a change in the other.
        candidates = 2
        assert manager.retry_count == 2 * candidates
        assert manager.total_attempts == 2 * candidates
    finally:
        settings.MONGO_URI = old_uri
        settings.MONGO_FALLBACK_URI = old_fallback

def test_token_auth_validation():
    """
    Test dynamic API token creation, encryption on disk, and bearer verification.
    """
    token = initialize_local_api_token()
    assert token is not None
    assert len(token) > 0
    
    # 1. Verify that verified bearer token works
    valid_header = f"Bearer {token}"
    verified = verify_api_token(valid_header)
    assert verified == token
    
    # 2. Reject bad scheme
    with pytest.raises(HTTPException) as bad_scheme:
        verify_api_token(f"Token {token}")
    assert bad_scheme.value.status_code == 401
    
    # 3. Reject bad token
    with pytest.raises(HTTPException) as bad_token:
        verify_api_token("Bearer InvalidTokenValue123")
    assert bad_token.value.status_code == 401
