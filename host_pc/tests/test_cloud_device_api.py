from __future__ import annotations

import importlib
import sys
import types
import warnings
from contextlib import contextmanager

import pytest

with warnings.catch_warnings():
    warnings.filterwarnings(
        "ignore",
        message=r"^Using `httpx` with `starlette\.testclient` is deprecated; install `httpx2` instead\.$",
    )
    from fastapi.testclient import TestClient

from cloud.backend.app.auth_store import AuthStore, UserRecord
from cloud.backend.app.security import hash_password


PASSWORD = "StrongPass123!"
PAIRING_ERROR_DETAIL = "\u7ed1\u5b9a\u7801\u65e0\u6548\u6216\u5df2\u8fc7\u671f"


@pytest.fixture
def client(tmp_path, monkeypatch):
    class Advisor:
        available = False
        model = ""

        def generate(self, *args):
            return "safe advice", 1

    class Influx:
        def close(self):
            pass

        def ping(self):
            return True

    class Bridge:
        def __init__(self, *args):
            self.latest = {}

        def start(self):
            pass

        def stop(self):
            pass

        def connected(self):
            return True

    influx_module = types.ModuleType("cloud.backend.app.db_influx")
    influx_module.InfluxWriter = Influx
    llm_module = types.ModuleType("cloud.backend.app.llm_advice")
    llm_module.DoubaoAdvisor = Advisor
    mqtt_module = types.ModuleType("cloud.backend.app.mqtt_bridge")
    mqtt_module.MqttBridge = Bridge
    monkeypatch.setenv("SG_AUTH_DB", str(tmp_path / "auth.db"))
    monkeypatch.setenv("SG_PAIRING_SECRET", "test-pairing-secret")
    monkeypatch.setenv("SG_INITIAL_ADMIN_USER", "admin")
    monkeypatch.setenv("SG_INITIAL_ADMIN_PASSWORD", PASSWORD)
    monkeypatch.setitem(sys.modules, "cloud.backend.app.db_influx", influx_module)
    monkeypatch.setitem(sys.modules, "cloud.backend.app.llm_advice", llm_module)
    monkeypatch.setitem(sys.modules, "cloud.backend.app.mqtt_bridge", mqtt_module)
    sys.modules.pop("cloud.backend.app.main", None)
    main = importlib.import_module("cloud.backend.app.main")
    with TestClient(main.app, base_url="https://testserver") as test_client:
        yield test_client


@pytest.fixture
def store(client) -> AuthStore:
    return client.app.state.auth_store


@pytest.fixture
def admin(store) -> UserRecord:
    return store.get_user(1)


@pytest.fixture
def user_a(store) -> UserRecord:
    return store.create_user("family-a", hash_password(PASSWORD), "user")


@pytest.fixture
def user_b(store) -> UserRecord:
    return store.create_user("family-b", hash_password(PASSWORD), "user")


def session(store: AuthStore, user: UserRecord) -> dict[str, str]:
    token = store.create_session(user.id, expires_at=2_000_000_000, client_type="pc")
    return {"Authorization": f"Bearer {token}"}


def device_ids(response) -> list[str]:
    assert response.status_code == 200
    return [device["device_id"] for device in response.json()]


def test_users_see_only_owned_devices_and_cannot_probe_other_tenants(
    client, store, user_a, user_b
):
    store.register_device("sg-a")
    store.register_device("sg-b")
    store.assign_device("sg-a", user_a.id)
    store.assign_device("sg-b", user_b.id)

    assert device_ids(client.get("/api/devices", headers=session(store, user_a))) == ["sg-a"]
    other = client.get("/api/devices/sg-b/latest", headers=session(store, user_a))
    missing = client.get("/api/devices/missing/latest", headers=session(store, user_a))

    assert other.status_code == missing.status_code == 404
    assert other.json()["detail"] == missing.json()["detail"] == "\u8bbe\u5907\u4e0d\u5b58\u5728"
    assert client.get("/devices/sg-b/latest").status_code == 404


def test_pairing_code_expires_after_ten_minutes(client, store, admin, user_a, monkeypatch):
    store.register_device("sg-a", now=100)
    code = store.create_pairing_code("sg-a", admin.id, now=100)
    monkeypatch.setattr("cloud.backend.app.auth_store.time.time", lambda: 701)

    response = client.post(
        "/api/devices/pair", headers=session(store, user_a), json={"code": code}
    )

    assert response.status_code == 422
    assert response.json()["detail"] == PAIRING_ERROR_DETAIL


def test_pairing_is_single_use_and_device_lists_never_expose_plaintext_codes(
    client, store, admin, user_a, user_b, tmp_path
):
    store.register_device("sg-a")
    code_response = client.post(
        "/api/admin/devices/sg-a/pairing-code", headers=session(store, admin)
    )

    assert code_response.status_code == 201
    code = code_response.json()["code"]
    assert code.isdecimal() and len(code) == 6
    assert code.encode("ascii") not in (tmp_path / "auth.db").read_bytes()
    assert code not in str(client.get("/api/admin/devices", headers=session(store, admin)).json())

    claimed = client.post(
        "/api/devices/pair", headers=session(store, user_a), json={"code": code}
    )
    repeated = client.post(
        "/api/devices/pair", headers=session(store, user_b), json={"code": code}
    )

    assert claimed.status_code == 200
    assert claimed.json()["device_id"] == "sg-a"
    assert repeated.status_code == 422
    assert repeated.json()["detail"] == PAIRING_ERROR_DETAIL
    assert code not in str(client.get("/api/devices", headers=session(store, user_a)).json())


def test_only_administrators_can_create_pairing_codes_or_unbind_devices(
    client, store, admin, user_a, user_b
):
    store.register_device("sg-a")

    assert (
        client.post(
            "/api/admin/devices/sg-a/pairing-code", headers=session(store, user_a)
        ).status_code
        == 403
    )
    created = client.post(
        "/api/admin/devices/sg-a/pairing-code", headers=session(store, admin)
    )
    assert created.status_code == 201
    assert client.post(
        "/api/devices/pair", headers=session(store, user_a), json={"code": created.json()["code"]}
    ).status_code == 200

    assert (
        client.delete("/api/admin/devices/sg-a/owner", headers=session(store, user_a)).status_code
        == 403
    )
    assert client.delete("/api/admin/devices/sg-a/owner", headers=session(store, admin)).status_code == 204

    replacement = client.post(
        "/api/admin/devices/sg-a/pairing-code", headers=session(store, admin)
    )
    assert replacement.status_code == 201
    assert client.post(
        "/api/devices/pair",
        headers=session(store, user_b),
        json={"code": replacement.json()["code"]},
    ).status_code == 200
