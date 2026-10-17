"""Encrypt the Gmail refresh token at rest (Fernet; key from env / SSM)."""

import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_config


class CryptoError(RuntimeError):
    pass


def _fernet() -> Fernet:
    key = get_config().token_encryption_key
    if not key:
        raise CryptoError("TOKEN_ENCRYPTION_KEY is not set")
    try:
        return Fernet(key)
    except ValueError:
        raise CryptoError("TOKEN_ENCRYPTION_KEY is not a valid Fernet key") from None


def encrypt(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken:
        raise CryptoError("Stored Gmail token can't be decrypted (key changed?)") from None


def derived_secret(purpose: str) -> bytes:
    """A separate secret for signing things (e.g. OAuth state), derived from the key."""
    key = get_config().token_encryption_key
    if not key:
        raise CryptoError("TOKEN_ENCRYPTION_KEY is not set")
    return hashlib.sha256(f"{purpose}:{key}".encode()).digest()
