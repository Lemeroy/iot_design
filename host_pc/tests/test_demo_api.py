from __future__ import annotations

import asyncio
import secrets
import time

import httpx
import pytest

from cloud.backend.app.demo_auth import DemoAuth
from cloud.backend.app.demo_api import DEMO_SESSION_COOKIE
from cloud.backend.app.schemas import DownlinkPayload, Profile, Scores, UplinkPayload


def _payload(*, device_id: str = "sg-0001", ts: int = 1) -> UplinkPayload:
    return UplinkPayload(
        scores=Scores(face=None, speech=71, tongue=None, eye=None, csi=84, final=76),
        level="warning",
        reasons=["score threshold"],
        veto_by=["eye"],
        profile=Profile(age=68, gender="other", conditions=["private"], meds=[]),
        device_id=device_id,
        ts=ts,
    )


def _advice() -> DownlinkPayload:
    return DownlinkPayload(
        level="warning",
        advice_text="Generated advice.",
        source="test-advisor",
        ts=2,
    )


@pytest.fixture
def demo_app(monkeypatch):
    import cloud.backend.app.main as main

    password = secrets.token_urlsafe(24)
    monkeypatch.setenv("SG_DEMO_USER", "demo-user")
    monkeypatch.setenv("SG_DEMO_PASSWORD", password)
    monkeypatch.setenv("SG_DEMO_SESSION_SECRET", secrets.token_urlsafe(48))
    monkeypatch.delenv("SG_ALLOW_INSECURE_HTTP", raising=False)
    auth = DemoAuth.from_env()

    class TestBridge:
        def __init__(self):
            self.latest = {}

        def cache_snapshot(self, device_id):
            cache = self.latest.get(device_id)
            return dict(cache) if isinstance(cache, dict) else None

    bridge = TestBridge()
    monkeypatch.setattr(main, "_demo_auth", auth)
    monkeypatch.setattr(main, "_bridge", bridge)
    return main.app, bridge, password


def _run(scenario):
    return asyncio.run(scenario())


async def _client(app):
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="https://demo.test",
    )


def test_demo_api_requires_a_signed_session(demo_app):
    app, _, _ = demo_app

    async def scenario():
        async with await _client(app) as client:
            for method, path in (
                ("get", "/demo/api/session"),
                ("post", "/demo/api/connect"),
                ("post", "/demo/api/disconnect"),
                ("get", "/demo/api/device"),
            ):
                body = {"device_id": "sg-0001"} if path.endswith("/connect") else {}
                response = await client.request(method, path, json=body)
                assert response.status_code == 401

    _run(scenario)


def test_demo_login_failure_is_generic(demo_app):
    app, _, _ = demo_app

    async def scenario():
        async with await _client(app) as client:
            response = await client.post(
                "/demo/api/login",
                json={"username": "wrong-user", "password": secrets.token_urlsafe(24)},
            )

            assert response.status_code == 401
            assert response.json() == {"detail": "invalid username or password"}
            assert DEMO_SESSION_COOKIE not in response.cookies

    _run(scenario)


@pytest.mark.parametrize(
    "body",
    [
        b"",
        b'{"username":"not-closed',
        b"[]",
        b"null",
        b'"not an object"',
    ],
)
def test_demo_login_rejects_invalid_json_with_generic_credentials_error(demo_app, body):
    app, _, _ = demo_app

    async def scenario():
        async with await _client(app) as client:
            response = await client.post(
                "/demo/api/login",
                content=body,
                headers={"content-type": "application/json"},
            )

            assert response.status_code == 401
            assert response.json() == {"detail": "invalid username or password"}
            if body:
                assert body.decode("utf-8", errors="replace") not in response.text
            assert DEMO_SESSION_COOKIE not in response.cookies

    _run(scenario)


def test_demo_login_issues_a_secure_http_only_unbound_session(demo_app):
    app, _, password = demo_app

    async def scenario():
        async with await _client(app) as client:
            response = await client.post(
                "/demo/api/login", json={"username": "demo-user", "password": password}
            )

            assert response.status_code == 200
            assert response.json() == {"authenticated": True, "device_id": None}
            set_cookie = response.headers["set-cookie"]
            assert "HttpOnly" in set_cookie
            assert "SameSite=strict" in set_cookie
            assert "Secure" in set_cookie

            session = await client.get("/demo/api/session")
            assert session.json() == {"authenticated": True, "device_id": None}

    _run(scenario)


@pytest.mark.parametrize("device_id", ["", "bad id", "sg/0001", "x" * 33])
def test_demo_connect_rejects_invalid_device_ids(demo_app, device_id):
    app, _, password = demo_app

    async def scenario():
        async with await _client(app) as client:
            await client.post("/demo/api/login", json={"username": "demo-user", "password": password})
            response = await client.post("/demo/api/connect", json={"device_id": device_id})
            assert response.status_code == 422

    _run(scenario)


def test_demo_connect_rejects_unknown_and_offline_devices(demo_app):
    app, bridge, password = demo_app
    bridge.latest["sg-offline"] = {"uplink": _payload(device_id="sg-offline"), "received_at": time.time() - 31}

    async def scenario():
        async with await _client(app) as client:
            await client.post("/demo/api/login", json={"username": "demo-user", "password": password})

            unknown = await client.post("/demo/api/connect", json={"device_id": "sg-unknown"})
            assert unknown.status_code == 404

            offline = await client.post("/demo/api/connect", json={"device_id": "sg-offline"})
            assert offline.status_code == 409

    _run(scenario)


def test_demo_connect_binds_an_online_device_and_disconnect_clears_the_binding(demo_app):
    app, bridge, password = demo_app
    bridge.latest["sg-0001"] = {"uplink": _payload(), "received_at": time.time()}

    async def scenario():
        async with await _client(app) as client:
            await client.post("/demo/api/login", json={"username": "demo-user", "password": password})

            connected = await client.post("/demo/api/connect", json={"device_id": "sg-0001"})
            assert connected.status_code == 200
            assert connected.json() == {"authenticated": True, "device_id": "sg-0001"}

            disconnected = await client.post("/demo/api/disconnect")
            assert disconnected.status_code == 200
            assert disconnected.json() == {"authenticated": True, "device_id": None}
            assert (await client.get("/demo/api/device")).status_code == 409

    _run(scenario)


def test_demo_api_reads_device_state_from_bridge_snapshot(demo_app):
    app, _, password = demo_app
    snapshot = {"uplink": _payload(), "received_at": time.time(), "advice": _advice()}

    class SnapshotOnlyBridge:
        @staticmethod
        def cache_snapshot(device_id):
            return dict(snapshot) if device_id == "sg-0001" else None

    import cloud.backend.app.main as main

    main._bridge = SnapshotOnlyBridge()

    async def scenario():
        async with await _client(app) as client:
            await client.post("/demo/api/login", json={"username": "demo-user", "password": password})
            connected = await client.post("/demo/api/connect", json={"device_id": "sg-0001"})
            assert connected.status_code == 200

            response = await client.get("/demo/api/device")
            assert response.status_code == 200
            assert response.json()["received_at"] == snapshot["received_at"]

    _run(scenario)


def test_legacy_latest_endpoint_reads_the_bridge_snapshot(demo_app):
    app, _, _ = demo_app
    snapshot = {"uplink": _payload(ts=42), "advice": _advice()}

    class SnapshotOnlyBridge:
        @staticmethod
        def cache_snapshot(device_id):
            return dict(snapshot) if device_id == "sg-0001" else None

        @property
        def latest(self):
            raise AssertionError("latest endpoint must use cache_snapshot")

    import cloud.backend.app.main as main

    main._bridge = SnapshotOnlyBridge()

    async def scenario():
        async with await _client(app) as client:
            response = await client.get("/devices/sg-0001/latest")

            assert response.status_code == 200
            assert response.json() == {
                "device_id": "sg-0001",
                "last_uplink_ts": 42,
                "last_advice": {
                    "schema_version": 1,
                    "level": "warning",
                    "advice_text": "Generated advice.",
                    "ts": 2,
                    "source": "test-advisor",
                },
                "latest_scores": {
                    "face": None,
                    "speech": 71,
                    "tongue": None,
                    "eye": None,
                    "csi": 84,
                    "final": 76,
                },
                "latest_level": "warning",
            }

    _run(scenario)


def test_demo_device_returns_only_monitoring_data_and_latest_advice(demo_app):
    app, bridge, password = demo_app
    bridge.latest["sg-0001"] = {
        "uplink": _payload(ts=1),
        "received_at": time.time(),
        "advice": _advice(),
        "unrelated": "must not be exposed",
    }

    async def scenario():
        async with await _client(app) as client:
            await client.post("/demo/api/login", json={"username": "demo-user", "password": password})
            await client.post("/demo/api/connect", json={"device_id": "sg-0001"})
            response = await client.get("/demo/api/device")

            assert response.status_code == 200
            data = response.json()
            assert set(data) == {
                "device_id",
                "online",
                "received_at",
                "scores",
                "level",
                "reasons",
                "veto_by",
                "advice",
            }
            assert data["online"] is True
            assert data["scores"] == {
                "face": None,
                "speech": 71,
                "tongue": None,
                "eye": None,
                "csi": 84,
                "final": 76,
            }
            assert data["level"] == "warning"
            assert data["reasons"] == ["score threshold"]
            assert data["veto_by"] == ["eye"]
            assert data["advice"] == {
                "advice_text": "Generated advice.",
                "source": "test-advisor",
                "ts": 2,
            }
            serialized = response.text
            for forbidden in ("profile", "conditions", "meds", "schema_version", "unrelated"):
                assert forbidden not in serialized

    _run(scenario)
