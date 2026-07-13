"""Single-account authentication for the preliminary remote monitor demo."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import time
from dataclasses import dataclass
from typing import Any


_PASSWORD_SALT_BYTES = 16
_PASSWORD_DK_BYTES = 32
_PASSWORD_SCRYPT_N = 2**14
_PASSWORD_SCRYPT_R = 8
_PASSWORD_SCRYPT_P = 1
_MIN_SESSION_SECRET_BYTES = 32
_SESSION_TTL_SECONDS = 3600
_DEVICE_ID_RE = re.compile(r"[A-Za-z0-9_-]{1,32}")


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip() == "1"


def _encode_segment(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _decode_segment(value: str) -> bytes | None:
    try:
        padding = "=" * (-len(value) % 4)
        decoded = base64.urlsafe_b64decode(value + padding)
    except (TypeError, ValueError):
        return None
    if _encode_segment(decoded) != value:
        return None
    return decoded


def _valid_device_id(device_id: Any) -> bool:
    return isinstance(device_id, str) and _DEVICE_ID_RE.fullmatch(device_id) is not None


@dataclass(frozen=True, slots=True)
class DemoAuth:
    """Configuration and in-process credentials for the one demo account."""

    username: str | None
    _password_salt: bytes | None
    _password_digest: bytes | None
    _session_secret: bytes | None
    secure_cookie: bool
    session_ttl_seconds: int = _SESSION_TTL_SECONDS
    enabled: bool = True

    @classmethod
    def from_env(cls) -> "DemoAuth":
        """Build auth from environment, disabling it when required config is absent.

        The plaintext password is deliberately removed in the outer ``finally``
        so it is cleared for disabled, invalid, and successful initialization.
        """
        try:
            secure_cookie = not _env_flag("SG_ALLOW_INSECURE_HTTP")
            username = os.environ.get("SG_DEMO_USER")
            password = os.environ.get("SG_DEMO_PASSWORD")
            secret_text = os.environ.get("SG_DEMO_SESSION_SECRET")

            if not username or not password or not secret_text:
                return cls._disabled(secure_cookie)

            session_secret = secret_text.encode("utf-8")
            if len(session_secret) < _MIN_SESSION_SECRET_BYTES:
                raise ValueError("demo session secret is too weak")

            password_salt = secrets.token_bytes(_PASSWORD_SALT_BYTES)
            password_digest = hashlib.scrypt(
                password.encode("utf-8"),
                salt=password_salt,
                n=_PASSWORD_SCRYPT_N,
                r=_PASSWORD_SCRYPT_R,
                p=_PASSWORD_SCRYPT_P,
                dklen=_PASSWORD_DK_BYTES,
            )
            return cls(
                username=username,
                _password_salt=password_salt,
                _password_digest=password_digest,
                _session_secret=session_secret,
                secure_cookie=secure_cookie,
            )
        finally:
            os.environ.pop("SG_DEMO_PASSWORD", None)

    @classmethod
    def _disabled(cls, secure_cookie: bool) -> "DemoAuth":
        return cls(
            username=None,
            _password_salt=None,
            _password_digest=None,
            _session_secret=None,
            secure_cookie=secure_cookie,
            enabled=False,
        )

    @property
    def is_enabled(self) -> bool:
        return self.enabled

    @property
    def disabled(self) -> bool:
        return not self.enabled

    def verify_login(self, username: str, password: str) -> bool:
        """Return whether the supplied credentials match the demo account."""
        if not self.enabled:
            return False

        supplied_username = username.encode("utf-8") if isinstance(username, str) else b""
        configured_username = self.username.encode("utf-8") if self.username else b""
        username_matches = hmac.compare_digest(supplied_username, configured_username)

        supplied_password = password.encode("utf-8") if isinstance(password, str) else b""
        password_digest = hashlib.scrypt(
            supplied_password,
            salt=self._password_salt,
            n=_PASSWORD_SCRYPT_N,
            r=_PASSWORD_SCRYPT_R,
            p=_PASSWORD_SCRYPT_P,
            dklen=_PASSWORD_DK_BYTES,
        )
        password_matches = hmac.compare_digest(password_digest, self._password_digest)
        return username_matches and password_matches

    def issue_session(self, device_id: str | None = None, *, now: float | None = None) -> str:
        """Issue an HMAC-SHA256 signed, URL-safe stateless session token."""
        if not self.enabled or self._session_secret is None or self.username is None:
            raise RuntimeError("demo authentication is disabled")
        if device_id is not None and not _valid_device_id(device_id):
            raise ValueError("invalid device id")

        claims: dict[str, Any] = {
            "exp": int(time.time() if now is None else now) + self.session_ttl_seconds,
            "username": self.username,
        }
        if device_id is not None:
            claims["device_id"] = device_id
        payload = json.dumps(claims, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode(
            "ascii"
        )
        encoded_payload = _encode_segment(payload)
        signature = hmac.new(
            self._session_secret,
            encoded_payload.encode("ascii"),
            hashlib.sha256,
        ).digest()
        return f"{encoded_payload}.{_encode_segment(signature)}"

    def verify_session(self, token: str, *, now: float | None = None) -> dict[str, Any] | None:
        """Return validated claims, or ``None`` for any invalid or expired token."""
        if not self.enabled or self._session_secret is None or not isinstance(token, str):
            return None
        parts = token.split(".")
        if len(parts) != 2 or not all(parts):
            return None

        encoded_payload, encoded_signature = parts
        payload = _decode_segment(encoded_payload)
        signature = _decode_segment(encoded_signature)
        if payload is None or signature is None:
            return None
        expected_signature = hmac.new(
            self._session_secret,
            encoded_payload.encode("ascii"),
            hashlib.sha256,
        ).digest()
        if not hmac.compare_digest(signature, expected_signature):
            return None

        try:
            claims = json.loads(payload.decode("ascii"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None
        if not isinstance(claims, dict):
            return None
        if set(claims) - {"exp", "username", "device_id"}:
            return None

        username = claims.get("username")
        expiry = claims.get("exp")
        if not isinstance(username, str) or not isinstance(expiry, int) or isinstance(expiry, bool):
            return None
        if self.username is None or not hmac.compare_digest(
            username.encode("utf-8"), self.username.encode("utf-8")
        ):
            return None
        if expiry <= (time.time() if now is None else now):
            return None

        device_id = claims.get("device_id")
        if "device_id" in claims and not _valid_device_id(device_id):
            return None
        validated = {"username": username, "exp": expiry}
        if device_id is not None:
            validated["device_id"] = device_id
        return validated
