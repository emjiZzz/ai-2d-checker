import os
import base64
import hashlib
import secrets
import json
from datetime import datetime, timedelta
from typing import Dict, Any, Tuple
from .encryption import encryptor

# PBKDF2 Configuration
ITERATIONS = 100000
HASH_NAME = "sha256"
SALT_BYTES = 16

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

def create_jwt_token(payload: Dict[str, Any], expires_delta_minutes: int = 1440) -> Tuple[str, datetime]:
    """
    Generates a secure, AES-256 encrypted local session token.
    Returns: (encrypted_base64_token, expires_at_datetime)
    """
    expires_at = datetime.utcnow() + timedelta(minutes=expires_delta_minutes)
    full_payload = {
        **payload,
        "exp": expires_at.isoformat(),
        "jti": secrets.token_hex(16)
    }
    
    serialized = json.dumps(full_payload)
    encrypted = encryptor.encrypt(serialized)
    return encrypted, expires_at

def verify_jwt_token(token: str) -> Dict[str, Any]:
    """
    Decrypts and validates an AES-256 encrypted session token.
    Raises ValueError if invalid or expired.
    """
    try:
        decrypted = encryptor.decrypt(token)
        payload = json.loads(decrypted)
        
        # Check expiration
        exp_str = payload.get("exp")
        if not exp_str:
            raise ValueError("Token signature is missing expiration metadata.")
            
        expires_at = datetime.fromisoformat(exp_str)
        if expires_at < datetime.utcnow():
            raise ValueError("Token has expired.")
            
        return payload
    except Exception as e:
        raise ValueError(f"Unauthorized: Session token verification failed: {str(e)}")
