"""AES-256-GCM wrapper with Windows keyring (Credential Manager) backing.

Key生成一次, 存于用户凭据管理器, service='StrokeGuard', username='master-key'.
不再落盘明文 key.
"""
from __future__ import annotations

import base64
import os
import secrets

import keyring
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_SERVICE = "StrokeGuard"
_ACCOUNT = "master-key"


def _load_or_create_key() -> bytes:
    b64 = keyring.get_password(_SERVICE, _ACCOUNT)
    if b64:
        try:
            key = base64.b64decode(b64)
            if len(key) == 32:
                return key
        except Exception:
            pass
    # 生成新 key
    key = secrets.token_bytes(32)
    keyring.set_password(_SERVICE, _ACCOUNT, base64.b64encode(key).decode("ascii"))
    return key


class AesGcm:
    """薄封装, 每次 encrypt 生成随机 12B nonce, 拼接在密文前."""

    def __init__(self, key: bytes | None = None) -> None:
        self._aes = AESGCM(key if key is not None else _load_or_create_key())

    def encrypt(self, plaintext: bytes, aad: bytes | None = None) -> bytes:
        nonce = os.urandom(12)
        ct = self._aes.encrypt(nonce, plaintext, aad)
        return nonce + ct

    def decrypt(self, blob: bytes, aad: bytes | None = None) -> bytes:
        if len(blob) < 13:
            raise ValueError("ciphertext too short")
        nonce, ct = blob[:12], blob[12:]
        return self._aes.decrypt(nonce, ct, aad)
