from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os

import pytest

from cloud.backend.app.demo_auth import DemoAuth


SECRET = "demo-session-secret-0123456789abcdef"


def configure_demo(monkeypatch, *, allow_insecure: str | None = None) -> None:
    monkeypatch.setenv("SG_DEMO_USER", "demo")
    monkeypatch.setenv("SG_DEMO_PASSWORD", "correct horse battery staple")
    monkeypatch.setenv("SG_DEMO_SESSION_SECRET", SECRET)
    if allow_insecure is None:
        monkeypatch.delenv("SG_ALLOW_INSECURE_HTTP", raising=False)
    else:
        monkeypatch.setenv("SG_ALLOW_INSECURE_HTTP", allow_insecure)


def test_incomplete_configuration_returns_explicitly_disabled_auth(monkeypatch):
    monkeypatch.setenv("SG_DEMO_PASSWORD", "should-not-remain")
    monkeypatch.delenv("SG_DEMO_USER", raising=False)
    monkeypatch.delenv("SG_DEMO_SESSION_SECRET", raising=False)

    auth = DemoAuth.from_env()

    assert auth.enabled is False
    assert auth.secure_cookie is True
    assert os.environ.get("SG_DEMO_PASSWORD") is None
    assert auth.verify_login("demo", "should-not-remain") is False


def test_complete_configuration_verifies_password_and_rejects_wrong_credentials(monkeypatch):
    configure_demo(monkeypatch)

    auth = DemoAuth.from_env()

    assert auth.enabled is True
    assert auth.verify_login("demo", "correct horse battery staple") is True
    assert auth.verify_login("demo", "wrong") is False
    assert auth.verify_login("other", "correct horse battery staple") is False
    assert "SG_DEMO_PASSWORD" not in os.environ


def test_session_contains_username_and_expires(monkeypatch):
    configure_demo(monkeypatch)
    auth = DemoAuth.from_env()

    token = auth.issue_session(now=100)

    assert token.count(".") == 1
    assert all(part for part in token.split("."))
    assert all(char.isalnum() or char in "-_." for char in token)
    assert auth.verify_session(token, now=100) == {
        "username": "demo",
        "exp": 100 + auth.session_ttl_seconds,
    }
    assert auth.verify_session(token, now=100 + auth.session_ttl_seconds) is None


def test_session_signature_tampering_is_rejected(monkeypatch):
    configure_demo(monkeypatch)
    auth = DemoAuth.from_env()
    token = auth.issue_session(now=100)
    payload, signature = token.split(".")
    replacement = "A" if signature[0] != "A" else "B"
    tampered = f"{payload}.{replacement}{signature[1:]}"

    assert auth.verify_session(tampered, now=100) is None
    assert auth.verify_session(token + "x", now=100) is None


def test_session_can_bind_a_validated_device_id(monkeypatch):
    configure_demo(monkeypatch)
    auth = DemoAuth.from_env()

    token = auth.issue_session(device_id="sg-0001", now=100)

    assert auth.verify_session(token, now=100) == {
        "username": "demo",
        "exp": 100 + auth.session_ttl_seconds,
        "device_id": "sg-0001",
    }
    for invalid in ("", "has space", "a/b", "x" * 33):
        with pytest.raises(ValueError, match="device id"):
            auth.issue_session(device_id=invalid)


@pytest.mark.parametrize(
    ("setting", "expected"),
    [
        (None, True),
        ("0", True),
        ("false", True),
        ("true", True),
        ("yes", True),
        ("on", True),
        (" 1 ", False),
    ],
)
def test_secure_cookie_is_disabled_only_by_explicit_insecure_http(monkeypatch, setting, expected):
    configure_demo(monkeypatch, allow_insecure=setting)

    assert DemoAuth.from_env().secure_cookie is expected


def test_weak_secret_is_rejected_without_leaking_credentials(monkeypatch):
    monkeypatch.setenv("SG_DEMO_USER", "demo")
    password = "password-that-must-not-appear"
    secret = "too-short"
    monkeypatch.setenv("SG_DEMO_PASSWORD", password)
    monkeypatch.setenv("SG_DEMO_SESSION_SECRET", secret)

    with pytest.raises(ValueError) as exc_info:
        DemoAuth.from_env()

    assert password not in str(exc_info.value)
    assert secret not in str(exc_info.value)
    assert "SG_DEMO_PASSWORD" not in os.environ


def test_disabled_auth_cannot_issue_a_session(monkeypatch):
    monkeypatch.delenv("SG_DEMO_USER", raising=False)
    monkeypatch.delenv("SG_DEMO_PASSWORD", raising=False)
    monkeypatch.delenv("SG_DEMO_SESSION_SECRET", raising=False)
    auth = DemoAuth.from_env()

    with pytest.raises(RuntimeError, match="disabled"):
        auth.issue_session()


def test_session_signature_uses_hmac_sha256(monkeypatch):
    configure_demo(monkeypatch)
    auth = DemoAuth.from_env()
    token = auth.issue_session(now=100)
    encoded_payload, encoded_signature = token.split(".")
    padding = "=" * (-len(encoded_payload) % 4)
    payload = base64.urlsafe_b64decode(encoded_payload + padding)
    padding = "=" * (-len(encoded_signature) % 4)
    signature = base64.urlsafe_b64decode(encoded_signature + padding)
    expected = hmac.new(
        SECRET.encode("utf-8"), encoded_payload.encode("ascii"), hashlib.sha256
    ).digest()

    assert json.loads(payload) == {"exp": 100 + auth.session_ttl_seconds, "username": "demo"}
    assert hmac.compare_digest(signature, expected)
