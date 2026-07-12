from __future__ import annotations

from contextlib import contextmanager
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import socket
import threading
import time

import pytest
from keyring.errors import KeyringError

from stroke_host.config.profile_loader import DeviceEndpoint, UserProfile
from stroke_host.io.device_config_client import (
    DeviceConfigClient,
    DeviceConfigError,
)


TOKEN = "unit-test-manager-token"


def response_payload(device_id: str = "sg-test", revision: int = 4) -> dict:
    return {
        "schema_version": 1,
        "revision": revision,
        "device_id": device_id,
        "profile": {
            "age": 68,
            "gender": "M",
            "conditions": ["hypertension"],
            "meds": ["aspirin"],
            "stroke_history": False,
        },
        "readonly": {
            "face_danger": 30,
            "mouth_angle_danger_deg": 20,
            "speech_danger": 35,
        },
        "capabilities": ["profile_write"],
    }


class FakeHandler(BaseHTTPRequestHandler):
    status = 200
    payload: object = response_payload()
    delay = 0.0
    requests: list[dict] = []

    def _handle(self) -> None:
        if self.delay:
            time.sleep(self.delay)
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length) if length else b""
        type(self).requests.append({
            "method": self.command,
            "path": self.path,
            "authorization": self.headers.get("Authorization"),
            "content_type": self.headers.get("Content-Type"),
            "body": body,
        })
        encoded = (
            self.payload if isinstance(self.payload, bytes)
            else json.dumps(self.payload).encode("utf-8")
        )
        self.send_response(self.status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        try:
            self.wfile.write(encoded)
        except (BrokenPipeError, ConnectionResetError):
            pass

    do_GET = _handle
    do_PUT = _handle

    def log_message(self, *_args) -> None:
        return


@contextmanager
def fake_server():
    FakeHandler.status = 200
    FakeHandler.payload = response_payload()
    FakeHandler.delay = 0.0
    FakeHandler.requests = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.fixture
def keyring_store(monkeypatch):
    values = {}
    monkeypatch.setattr(
        "keyring.set_password",
        lambda service, account, value: values.__setitem__((service, account), value),
    )
    monkeypatch.setattr(
        "keyring.get_password",
        lambda service, account: values.get((service, account)),
    )
    return values


def client_for(server, timeout: float = 2.0) -> DeviceConfigClient:
    endpoint = DeviceEndpoint(host="127.0.0.1", port=server.server_port)
    client = DeviceConfigClient("sg-test", endpoint, timeout=timeout)
    client.set_token(TOKEN)
    return client


def test_get_uses_exact_private_endpoint_and_bearer_header(keyring_store):
    with fake_server() as server:
        response = client_for(server).get_config()

    assert response.device_id == "sg-test"
    assert response.revision == 4
    request = FakeHandler.requests[-1]
    assert request == {
        "method": "GET",
        "path": "/api/v1/config",
        "authorization": f"Bearer {TOKEN}",
        "content_type": None,
        "body": b"",
    }


def test_put_sends_only_version_revision_and_profile(keyring_store):
    with fake_server() as server:
        FakeHandler.payload = response_payload(revision=5)
        profile = UserProfile(
            age=69,
            gender="F",
            conditions=["hypertension"],
            meds=[],
            stroke_history=True,
        )
        response = client_for(server).put_profile(profile, expected_revision=4)

    assert response.revision == 5
    request = FakeHandler.requests[-1]
    assert request["method"] == "PUT"
    assert request["path"] == "/api/v1/config"
    assert request["content_type"] == "application/json"
    assert json.loads(request["body"]) == {
        "schema_version": 1,
        "expected_revision": 4,
        "profile": profile.model_dump(mode="json"),
    }


@pytest.mark.parametrize(
    ("status", "kind"),
    [(401, "auth"), (409, "conflict")],
)
def test_http_statuses_become_bounded_errors(keyring_store, status, kind):
    with fake_server() as server:
        FakeHandler.status = status
        FakeHandler.payload = {"error": "server detail must not leak"}
        with pytest.raises(DeviceConfigError) as caught:
            client_for(server).get_config()
    assert caught.value.kind == kind
    assert "server detail" not in str(caught.value)
    assert TOKEN not in str(caught.value)


def test_malformed_or_wrong_device_response_is_rejected(keyring_store):
    with fake_server() as server:
        FakeHandler.payload = b"not-json"
        with pytest.raises(DeviceConfigError, match="响应") as malformed:
            client_for(server).get_config()
        assert malformed.value.kind == "response"

        FakeHandler.payload = response_payload(device_id="sg-other")
        with pytest.raises(DeviceConfigError) as mismatch:
            client_for(server).get_config()
        assert mismatch.value.kind == "device_mismatch"


def test_timeout_is_wrapped_without_leaking_token(keyring_store):
    with fake_server() as server:
        FakeHandler.delay = 0.2
        with pytest.raises(DeviceConfigError) as caught:
            client_for(server, timeout=0.03).get_config()
    assert caught.value.kind == "network"
    assert TOKEN not in str(caught.value)


def test_public_dns_result_is_refused_before_request(keyring_store, monkeypatch):
    FakeHandler.requests = []
    endpoint = DeviceEndpoint(host="127.0.0.1", port=80)
    client = DeviceConfigClient("sg-test", endpoint)
    client.set_token(TOKEN)
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 80))
        ],
    )
    with pytest.raises(DeviceConfigError) as caught:
        client.get_config()
    assert caught.value.kind == "endpoint"
    assert not FakeHandler.requests


def test_missing_token_is_reported_without_network_access(keyring_store):
    client = DeviceConfigClient(
        "sg-test", DeviceEndpoint(host="127.0.0.1", port=80)
    )
    with pytest.raises(DeviceConfigError) as caught:
        client.get_config()
    assert caught.value.kind == "missing_token"


def test_keyring_backend_error_is_bounded(monkeypatch):
    monkeypatch.setattr(
        "keyring.get_password",
        lambda *_args: (_ for _ in ()).throw(KeyringError("backend detail")),
    )
    client = DeviceConfigClient(
        "sg-test", DeviceEndpoint(host="127.0.0.1", port=80)
    )
    with pytest.raises(DeviceConfigError) as caught:
        client.get_config()
    assert caught.value.kind == "keyring"
    assert "backend detail" not in str(caught.value)
