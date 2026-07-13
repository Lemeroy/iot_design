from __future__ import annotations

import os
import sys
import types
import warnings
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
import importlib
from pathlib import Path

import pytest
with warnings.catch_warnings():
    warnings.filterwarnings(
        "ignore",
        message=r"^Using `httpx` with `starlette\.testclient` is deprecated; install `httpx2` instead\.$",
    )
    from fastapi.testclient import TestClient

from cloud.backend.app.auth_api import MAX_LOGIN_FAILURES, LoginRateLimiter, bootstrap_auth_store


ROOT = Path(__file__).resolve().parents[2]
AUTH_FAILURE_DETAIL = "\u8d26\u53f7\u6216\u5bc6\u7801\u9519\u8bef"
PASSWORD = "StrongPass123!"
SESSION_COOKIE = "sg_session"

@pytest.fixture
def app_client(tmp_path, monkeypatch):
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
    @contextmanager
    def build(*, auth_configured: bool):
        if auth_configured:
            monkeypatch.setenv("SG_AUTH_DB", str(tmp_path / "auth.db"))
            monkeypatch.setenv("SG_PAIRING_SECRET", "test-pairing-secret")
            monkeypatch.setenv("SG_INITIAL_ADMIN_USER", "admin")
            monkeypatch.setenv("SG_INITIAL_ADMIN_PASSWORD", PASSWORD)
        else:
            for name in (
                "SG_AUTH_DB",
                "SG_PAIRING_SECRET",
                "SG_INITIAL_ADMIN_USER",
                "SG_INITIAL_ADMIN_PASSWORD",
            ):
                monkeypatch.delenv(name, raising=False)
        monkeypatch.setitem(sys.modules, "cloud.backend.app.db_influx", influx_module)
        monkeypatch.setitem(sys.modules, "cloud.backend.app.llm_advice", llm_module)
        monkeypatch.setitem(sys.modules, "cloud.backend.app.mqtt_bridge", mqtt_module)
        sys.modules.pop("cloud.backend.app.main", None)
        main = importlib.import_module("cloud.backend.app.main")
        with TestClient(main.app, base_url="https://testserver") as test_client:
            yield test_client

    return build


@pytest.fixture
def client(app_client):
    with app_client(auth_configured=True) as test_client:
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


@pytest.mark.parametrize(
    "missing_name, password",
    [("SG_INITIAL_ADMIN_USER", PASSWORD), (None, "")],
)
def test_bootstrap_clears_initial_password_for_incomplete_initial_admin_config(
    tmp_path, monkeypatch, missing_name, password
):
    monkeypatch.setenv("SG_AUTH_DB", str(tmp_path / "auth.db"))
    monkeypatch.setenv("SG_PAIRING_SECRET", "test-pairing-secret")
    monkeypatch.setenv("SG_INITIAL_ADMIN_USER", "admin")
    monkeypatch.setenv("SG_INITIAL_ADMIN_PASSWORD", password)
    if missing_name:
        monkeypatch.delenv(missing_name)

    assert bootstrap_auth_store() is None
    assert os.environ.get("SG_INITIAL_ADMIN_PASSWORD") is None


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


def test_sessions_are_bound_to_their_login_client_transport(client):
    browser = login(client, "admin")
    browser_token = browser.cookies[SESSION_COOKIE]

    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {browser_token}"}).status_code == 401
    assert client.get("/api/auth/me").status_code == 200

    client.cookies.clear()
    pc = login(client, "admin", pc=True)
    pc_token = pc.json()["access_token"]
    assert "set-cookie" not in pc.headers
    client.cookies.set(SESSION_COOKIE, pc_token, domain="testserver.local", path="/")
    assert client.get("/api/auth/me").status_code == 401


def test_logout_revokes_the_current_browser_session(client):
    login(client, "admin")

    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/auth/me").status_code == 401


def test_missing_auth_configuration_disables_auth_without_stopping_cloud_lifespan(app_client):
    with app_client(auth_configured=False) as disabled_client:
        health = disabled_client.get("/health")
        advice = disabled_client.post(
            "/advice",
            json={
                "scores": {"final": 0},
                "level": "normal",
                "profile": {"age": 68},
                "reasons": [],
            },
        )

        assert health.status_code == 200
        assert health.json() == {"status": "ok", "mqtt": True, "influx": True, "llm": False}
        assert advice.status_code == 200
        assert disabled_client.post("/api/auth/login", json={"username": "a", "password": "b"}).status_code == 503
        assert disabled_client.get("/api/auth/me").status_code == 503
        assert disabled_client.get("/api/admin/users").status_code == 503
        assert disabled_client.get("/api/devices").status_code == 503


def test_login_failure_is_generic_and_rate_limited(client):
    responses = [
        client.post("/api/auth/login", json={"username": "missing", "password": "bad"})
        for _ in range(6)
    ]

    assert responses[0].status_code == 401
    assert responses[0].json()["detail"] == AUTH_FAILURE_DETAIL
    assert responses[-1].status_code == 429


def test_login_limiter_reserves_no_more_than_allowed_concurrent_failures():
    limiter = LoginRateLimiter()
    workers = MAX_LOGIN_FAILURES * 4

    def fail_once(_: int) -> bool:
        try:
            attempt = limiter.begin_attempt("127.0.0.1", "admin")
        except Exception as error:
            assert getattr(error, "status_code", None) == 429
            return False
        limiter.complete_attempt(attempt, failed=True)
        return True

    with ThreadPoolExecutor(max_workers=workers) as executor:
        results = list(executor.map(fail_once, range(workers)))

    assert results.count(True) == MAX_LOGIN_FAILURES
    assert results.count(False) == workers - MAX_LOGIN_FAILURES


def test_admin_creates_lists_and_deactivates_user(client):
    admin = login(client, "admin")
    admin_token = admin.cookies[SESSION_COOKIE]
    created = client.post(
        "/api/admin/users",
        json={"username": "family1", "password": PASSWORD},
    )

    assert created.status_code == 201
    assert created.json()["username"] == "family1"
    assert client.get("/api/admin/users").json() == [
        {"id": 1, "username": "admin", "role": "admin", "is_active": True},
        {"id": 2, "username": "family1", "role": "user", "is_active": True},
    ]

    user = login(client, "family1")
    user_token = user.cookies[SESSION_COOKIE]
    assert client.get("/api/admin/users").status_code == 403

    _set_browser_cookie(client, admin_token)
    disabled = client.patch("/api/admin/users/2", json={"is_active": False})
    assert disabled.status_code == 200
    assert disabled.json()["is_active"] is False
    _set_browser_cookie(client, user_token)
    assert client.get("/api/auth/me").status_code == 401

    failed_login = client.post(
        "/api/auth/login", json={"username": "family1", "password": PASSWORD}
    )
    assert failed_login.status_code == 401
    assert failed_login.json()["detail"] == AUTH_FAILURE_DETAIL


def test_admin_create_rejects_invalid_input_and_duplicate_normalized_username(client):
    login(client, "admin")

    for payload in ({"username": "   ", "password": PASSWORD}, {"username": "family1", "password": ""}):
        assert client.post("/api/admin/users", json=payload).status_code == 422

    assert client.post(
        "/api/admin/users", json={"username": "Family1", "password": PASSWORD}
    ).status_code == 201
    assert client.post(
        "/api/admin/users", json={"username": " family1 ", "password": PASSWORD}
    ).status_code == 409


def _set_browser_cookie(client: TestClient, token: str) -> None:
    client.cookies.clear()
    client.cookies.set(SESSION_COOKIE, token, domain="testserver.local", path="/")
