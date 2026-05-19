import os
import base64
import uuid
import hashlib
import platform
from typing import Optional
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from ..logger import logger

class AES256GCM:
    def __init__(self, key: Optional[bytes] = None):
        """
        Initialize AES-256-GCM cipher.
        If no key is provided, it derives a stable, device-bound key.
        """
        if key is None:
            self.key = self._derive_device_key()
        else:
            if len(key) != 32:
                raise ValueError("AES-256 key must be exactly 32 bytes.")
            self.key = key
        self.aesgcm = AESGCM(self.key)

    def _derive_device_key(self) -> bytes:
        """
        Derive a stable, machine-bound 32-byte key from hardware attributes.
        This matches the Rust side implementation exactly to ensure cross-platform compatibility.
        """
        try:
            computer = (os.getenv("COMPUTERNAME") or os.getenv("HOSTNAME") or "").strip()
            user = (os.getenv("USERNAME") or os.getenv("USER") or "").strip()
            system = platform.system().lower()
            if system == "darwin":
                system = "macos"
            
            # Combine to form unique machine signature salt
            signature = f"ai-2d-checker-device-salt-{computer}-{user}-{system}"
            
            # Hash signature using SHA-256 to generate 256-bit key
            return hashlib.sha256(signature.encode("utf-8")).digest()
        except Exception as e:
            logger.error(f"Failed to derive device-bound key, falling back to a static salt: {str(e)}")
            return hashlib.sha256(b"ai-2d-checker-static-fallback-salt-key-material").digest()

    def encrypt(self, plaintext: str) -> str:
        """
        Encrypts a plaintext UTF-8 string.
        Returns a base64 encoded string format: base64(nonce[12B] + ciphertext).
        """
        if not plaintext:
            return ""
        # 12-byte cryptographically secure random nonce
        nonce = os.urandom(12)
        # Encrypt the plaintext bytes
        ciphertext = self.aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
        # Concat nonce and ciphertext
        combined = nonce + ciphertext
        return base64.b64encode(combined).decode("utf-8")

    def decrypt(self, encrypted_base64: str) -> str:
        """
        Decrypts a base64 encoded payload of format: base64(nonce[12B] + ciphertext).
        Returns the original decrypted plaintext UTF-8 string.
        """
        if not encrypted_base64:
            return ""
        try:
            combined = base64.b64decode(encrypted_base64.encode("utf-8"))
            if len(combined) < 12:
                raise ValueError("Ciphertext payload is too short, missing valid GCM nonce.")
            
            nonce = combined[:12]
            ciphertext = combined[12:]
            
            decrypted_bytes = self.aesgcm.decrypt(nonce, ciphertext, None)
            return decrypted_bytes.decode("utf-8")
        except Exception as e:
            logger.error(f"Decryption failed: {str(e)}")
            raise ValueError(f"AES decryption error: {str(e)}")

# Singleton instance using stable device key
encryptor = AES256GCM()
