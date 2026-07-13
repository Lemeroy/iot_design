from __future__ import annotations

import hashlib
import hmac
import re
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError


_PASSWORD_HASHER = PasswordHasher()
_PAIRING_CODE_RE = re.compile(r"\d{6}")


def hash_password(password: str) -> str:
    if not isinstance(password, str) or not password:
        raise ValueError("password is required")
    return _PASSWORD_HASHER.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _PASSWORD_HASHER.verify(password_hash, password)
    except (InvalidHashError, VerificationError):
        return False


def password_needs_rehash(password_hash: str) -> bool:
    try:
        return _PASSWORD_HASHER.check_needs_rehash(password_hash)
    except InvalidHashError:
        return False


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def hash_session_token(token: str) -> str:
    if not isinstance(token, str) or not token:
        raise ValueError("session token is required")
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def hash_pairing_code(secret: bytes, code: str) -> str:
    if not isinstance(secret, bytes) or not secret:
        raise ValueError("pairing secret is required")
    if not isinstance(code, str) or not _PAIRING_CODE_RE.fullmatch(code):
        raise ValueError("pairing code must contain six digits")
    return hmac.new(secret, code.encode("ascii"), hashlib.sha256).hexdigest()
