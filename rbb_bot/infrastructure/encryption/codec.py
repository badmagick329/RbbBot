"""Authenticated application-level encryption for persisted RBB content."""

import base64
import hashlib
import hmac
import os
from functools import lru_cache

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes

from rbb_bot.settings.config import get_data_encryption_key


class DataEncryptionError(RuntimeError):
    """Raised when encrypted application data cannot be safely used."""


class DataEncryptionService:
    """Encrypt values and generate non-reversible exact-match lookup tokens."""

    PREFIX = "rbb:v1:"
    _AAD = b"rbb-bot:data:v1"

    def __init__(self, encoded_key: str):
        try:
            key = base64.urlsafe_b64decode(encoded_key.encode("ascii"))
        except (UnicodeEncodeError, ValueError) as exc:
            raise DataEncryptionError(
                "RBB_DATA_ENCRYPTION_KEY must be URL-safe base64"
            ) from exc
        if len(key) != 32:
            raise DataEncryptionError(
                "RBB_DATA_ENCRYPTION_KEY must decode to exactly 32 bytes"
            )

        self._cipher = AESGCM(key)
        self._lookup_key = HKDF(
            algorithm=hashes.SHA256(), length=32, salt=None, info=b"rbb-bot:lookup:v1"
        ).derive(key)

    def encrypt(self, value: str) -> str:
        nonce = os.urandom(12)
        ciphertext = self._cipher.encrypt(nonce, value.encode("utf-8"), self._AAD)
        encoded = base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii")
        return f"{self.PREFIX}{encoded}"

    def decrypt(self, value: str) -> str:
        if not value.startswith(self.PREFIX):
            raise DataEncryptionError("Stored value is not valid RBB ciphertext")
        try:
            payload = base64.urlsafe_b64decode(
                value[len(self.PREFIX) :].encode("ascii")
            )
            nonce, ciphertext = payload[:12], payload[12:]
            if len(nonce) != 12 or not ciphertext:
                raise ValueError("invalid ciphertext payload")
            return self._cipher.decrypt(nonce, ciphertext, self._AAD).decode("utf-8")
        except (InvalidTag, UnicodeDecodeError, ValueError) as exc:
            raise DataEncryptionError(
                "Could not authenticate stored encrypted data"
            ) from exc

    def lookup_token(self, value: str) -> str:
        return hmac.new(
            self._lookup_key, value.encode("utf-8"), hashlib.sha256
        ).hexdigest()


@lru_cache(maxsize=1)
def get_data_encryption_service() -> DataEncryptionService:
    return DataEncryptionService(get_data_encryption_key())


def reset_data_encryption_service() -> None:
    """Test helper for callers that replace the runtime environment."""
    get_data_encryption_service.cache_clear()
