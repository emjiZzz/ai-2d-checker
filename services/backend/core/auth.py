import base64
import hashlib
import hmac
import json
import os
import secrets
from datetime import datetime, timedelta
from typing import Any

# PBKDF2 Configuration
ITERATIONS = 100000
HASH_NAME = "sha256"
SALT_BYTES = 16

SESSION_KEY_FILE_NAME = ".session-key"
_session_signing_key: bytes | None = None

def hash_password(password: str) -> str:
    """
    Hashes a password using PBKDF2-HMAC-SHA256 with a secure random salt.
    Returns: salt[base64]:hashed[base64]
    """
    salt = os.urandom(SALT_BYTES)
    key = hashlib.pbkdf2_hmac(HASH_NAME, password.encode("utf-8"), salt, ITERATIONS)
    
    salt_b64 = base64.b64encode(salt).decode("utf-8")
    key_b64 = base64.b64encode(key).decode("utf-8")
    
    return f"{salt_b64}:{key_b64}"

def verify_password(password: str, hashed_value: str) -> bool:
    """
    Verifies a password against a PBKDF2-HMAC-SHA256 hash.
    """
    try:
        salt_b64, key_b64 = hashed_value.split(":")
        salt = base64.b64decode(salt_b64.encode("utf-8"))
        stored_key = base64.b64decode(key_b64.encode("utf-8"))
        
        test_key = hashlib.pbkdf2_hmac(HASH_NAME, password.encode("utf-8"), salt, ITERATIONS)
        return secrets.compare_digest(stored_key, test_key)
    except Exception:
        return False


# Alias — api/routers/auth.py's create/update-user endpoints call
# get_password_hash(), which never existed in this module (only
# hash_password did). Pre-existing bug, unrelated to the Phase A session-token
# fix this file was otherwise touched for — noted here rather than silently
# left broken since this file was already open. Those two call sites were not
# otherwise part of this remediation plan; see completion log.
get_password_hash = hash_password


def _get_session_signing_key() -> bytes:
    """
    Loads (or generates + persists) the server-only secret used to sign session
    tokens.

    This is intentionally NOT derived from device/environment values the way
    core/encryption.py's AES256GCM._derive_device_key() is. That derivation is
    fine for at-rest storage encryption (its actual purpose), but this module
    previously reused the same encryptor to *encrypt* session tokens as a stand-in
    for authenticity — and COMPUTERNAME/USERNAME are not secret, so any local
    process could derive the same key and forge a session for any username
    without a password. See docs/security-remediation-implementation-plan.md,
    Phase A, for the full writeup.

    Same generate-once-persist-encrypted-at-rest pattern as
    core/security.py::initialize_local_api_token — the persisted *file* is
    still fine to protect with AES256GCM (it's read back into memory and
    compared, never derived from guessable input), only the *token signing*
    use case was the wrong fit for that primitive.
    """
    global _session_signing_key
    if _session_signing_key is not None:
        return _session_signing_key

    # Local imports to avoid import-order/circular-dependency issues, matching
    # the pattern already used in core/security.py for the same reason.
    from .encryption import encryptor
    from ..infrastructure.storage.path_resolver import get_storage_root
    from ..logger import logger

    secure_dir = get_storage_root() / "secure"
    secure_dir.mkdir(parents=True, exist_ok=True)
    key_file = secure_dir / SESSION_KEY_FILE_NAME

    key_hex: str | None = None
    if key_file.exists():
        try:
            encrypted_content = key_file.read_text(encoding="utf-8").strip()
            key_hex = encryptor.decrypt(encrypted_content)
        except Exception as e:
            logger.error(f"Failed to read/decrypt persisted session signing key: {str(e)}")

    if not key_hex:
        key_hex = secrets.token_hex(32)
        try:
            encrypted_content = encryptor.encrypt(key_hex)
            key_file.write_text(encrypted_content, encoding="utf-8")
            logger.info(f"Generated new session signing key, persisted (encrypted) to: {key_file}")
        except Exception as e:
            logger.error(f"Failed to encrypt and persist new session signing key: {str(e)}")

    _session_signing_key = bytes.fromhex(key_hex)
    return _session_signing_key


def create_session_token(payload: dict[str, Any], expires_delta_minutes: int = 1440) -> tuple[str, datetime]:
    """
    Generates an HMAC-SHA256 signed local session token.

    NOT encrypted on purpose — the payload (username/role/exp/jti) doesn't need
    to be secret from the person holding it, it needs to be unforgeable by
    them. A signed-but-readable token is the correct primitive for that; see
    docs/security-remediation-implementation-plan.md Phase A for why this
    replaced the previous AES-GCM-encrypted, device-key-derived scheme.

    Returns: (signed_token, expires_at_datetime)
    """
    expires_at = datetime.utcnow() + timedelta(minutes=expires_delta_minutes)
    full_payload = {
        **payload,
        "exp": expires_at.isoformat(),
        "jti": secrets.token_hex(16)
    }

    payload_bytes = json.dumps(full_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    payload_b64 = base64.urlsafe_b64encode(payload_bytes).decode("utf-8")

    key = _get_session_signing_key()
    signature = hmac.new(key, payload_b64.encode("utf-8"), hashlib.sha256).hexdigest()

    token = f"{payload_b64}.{signature}"
    return token, expires_at


def verify_session_token(token: str) -> dict[str, Any]:
    """
    Verifies an HMAC-SHA256 signed session token and returns its payload.
    Raises ValueError if the signature is invalid, the token is malformed, or
    it has expired.

    Signature is verified BEFORE anything in the payload (including `exp`) is
    trusted — an attacker-controlled `exp` in an unsigned/mis-signed payload
    must never be evaluated.
    """
    try:
        payload_b64, sep, signature = token.partition(".")
        if not sep or not payload_b64 or not signature:
            raise ValueError("Malformed session token.")

        key = _get_session_signing_key()
        expected_signature = hmac.new(key, payload_b64.encode("utf-8"), hashlib.sha256).hexdigest()

        if not hmac.compare_digest(expected_signature, signature):
            raise ValueError("Session token signature verification failed.")

        payload_bytes = base64.urlsafe_b64decode(payload_b64.encode("utf-8"))
        payload = json.loads(payload_bytes)

        exp_str = payload.get("exp")
        if not exp_str:
            raise ValueError("Token signature is missing expiration metadata.")

        expires_at = datetime.fromisoformat(exp_str)
        if expires_at < datetime.utcnow():
            raise ValueError("Token has expired.")

        return payload
    except Exception as e:
        raise ValueError(f"Unauthorized: Session token verification failed: {str(e)}")
