from __future__ import annotations

import os
import sys
import types
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[2]
AUTH_FAILURE_DETAIL = "\u8d26\u53f7\u6216\u5bc6\u7801\u9519\u8bef"
PASSWORD = "StrongPass123!"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SG_AUTH_DB", str(tmp_path / "auth.db"))
    monkeypatch.setenv("SG_PAIRING_SECRET", "test-pairing-secret")
    monkeypatch.setenv("SG_INITIAL_ADMIN_USER", "admin")
    monkeypatch.setenv("SG_INITIAL_ADMIN_PASSWORD", PASSWORD)

    class Advisor:
        available = False
        model = ""

    class Influx:
        def close(self):
            pass

        def ping(self):
            return False

    class Bridge:
        def __init__(self, *args):
            self.latest = {}

        def start(self):
            pass

        def stop(self):
            pass

        def connected(self):
            return False

    influx_module = types.ModuleType("cloud.backend.app.db_influx")
    influx_module.InfluxWriter = Influx
    llm_module = types.ModuleType("cloud.backend.app.llm_advice")
    llm_module.DoubaoAdvisor = Advisor
    mqtt_module = types.ModuleType("cloud.backend.app.mqtt_bridge")
    mqtt_module.MqttBridge = Bridge
    monkeypatch.setitem(sys.modules, "cloud.backend.app.db_influx", influx_module)
    monkeypatch.setitem(sys.modules, "cloud.backend.app.llm_advice", llm_module)
    monkeypatch.setitem(sys.modules, "cloud.backend.app.mqtt_bridge", mqtt_module)
    sys.modules.pop("cloud.backend.app.main", None)
    from cloud.backend.app import main

    with TestClient(main.app, base_url="https://testserver") as test_client:
        yield test_client


def login(client: TestClient, username: str, password: str = PASSWORD, *, pc: bool = False):
    response = client.post(
        "/api/auth/login",
        json={"username": username, "password": password, "client": "pc" if pc else "browser"},
    )
    assert response.status_code == 200
    return response


def test_bootstraps_initial_admin_without_retaining_plaintext_password(client):
    assert os.environ.get("SG_INITIAL_ADMIN_PASSWORD") is None

    response = login(client, "admin")

    assert response.json()["user"] == {
        "id": 1,
        "username": "admin",
        "role": "admin",
        "is_active": True,
    }


def test_browser_login_uses_httponly_cookie_without_returning_token(client):
    response = login(client, "admin")

    assert response.json()["access_token"] is None
    cookie = response.headers["set-cookie"].lower()
    assert "sg_session=" in cookie
    assert "httponly" in cookie
    assert "samesite=strict" in cookie
    assert "secure" in cookie


def test_pc_login_returns_token_that_authenticates_bearer_requests(client):
    response = login(client, "admin", pc=True)
    token = response.json()["access_token"]

    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert token
    assert me.status_code == 200
    assert me.json()["username"] == "admin"


def test_login_failure_is_generic_and_rate_limited(client):
    responses = [
        client.post("/api/auth/login", json={"username": "missing", "password": "bad"})
        for _ in range(6)
    ]

    assert responses[0].status_code == 401
    assert responses[0].json()["detail"] == AUTH_FAILURE_DETAIL
    assert responses[-1].status_code == 429


def test_admin_creates_lists_and_deactivates_user(client):
    admin = login(client, "admin")
    created = client.post(
        "/api/admin/users",
        cookies=admin.cookies,
        json={"username": "family1", "password": PASSWORD},
    )

    assert created.status_code == 201
    assert created.json()["username"] == "family1"
    assert client.get("/api/admin/users", cookies=admin.cookies).json() == [
        {"id": 1, "username": "admin", "role": "admin", "is_active": True},
        {"id": 2, "username": "family1", "role": "user", "is_active": True},
    ]

    user = login(client, "family1")
    assert client.get("/api/admin/users", cookies=user.cookies).status_code == 403

    disabled = client.patch("/api/admin/users/2", cookies=admin.cookies, json={"is_active": False})
    assert disabled.status_code == 200
    assert disabled.json()["is_active"] is False
    assert client.get("/api/auth/me", cookies=user.cookies).status_code == 401

    failed_login = client.post(
        "/api/auth/login", json={"username": "family1", "password": PASSWORD}
    )
    assert failed_login.status_code == 401
    assert failed_login.json()["detail"] == AUTH_FAILURE_DETAIL
