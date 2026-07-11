#!/usr/bin/env python3
"""Initialize local InfluxDB and EMQX without exposing credentials in argv."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request


def request_json(method: str, url: str, payload: dict | None = None, token: str = ""):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            body = response.read()
            return response.status, json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        body = exc.read()
        parsed = json.loads(body) if body else {}
        return exc.code, parsed


def required(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        raise RuntimeError(f"missing environment variable: {name}")
    return value


def setup_influx() -> None:
    base = "http://127.0.0.1:8086"
    status, state = request_json("GET", f"{base}/api/v2/setup")
    if status != 200:
        raise RuntimeError(f"InfluxDB setup status failed: HTTP {status}")
    if not state.get("allowed", False):
        print("InfluxDB: already initialized")
        return
    payload = {
        "username": required("INFLUX_ADMIN_USER"),
        "password": required("INFLUX_ADMIN_PASS"),
        "org": required("INFLUX_ORG"),
        "bucket": required("INFLUX_BUCKET"),
        "token": required("INFLUX_TOKEN"),
        "retentionPeriodSeconds": 90 * 24 * 60 * 60,
    }
    status, _ = request_json("POST", f"{base}/api/v2/setup", payload)
    if status not in (200, 201):
        raise RuntimeError(f"InfluxDB setup failed: HTTP {status}")
    print("InfluxDB: initialized")


def setup_emqx() -> None:
    base = "http://127.0.0.1:18083/api/v5"
    status, login = request_json(
        "POST",
        f"{base}/login",
        {"username": "admin", "password": required("EMQX_DASHBOARD_PASS")},
    )
    if status != 200 or not login.get("token"):
        raise RuntimeError(f"EMQX dashboard login failed: HTTP {status}")
    token = login["token"]
    auth_id = urllib.parse.quote("password_based:built_in_database", safe=":")
    users_url = f"{base}/authentication/{auth_id}/users"
    for user_var, password_var in (
        ("MQTT_APP_USER", "MQTT_APP_PASS"),
        ("MQTT_HOST_USER", "MQTT_HOST_PASS"),
    ):
        username = required(user_var)
        payload = {
            "user_id": username,
            "password": required(password_var),
            "is_superuser": False,
        }
        status, _ = request_json("POST", users_url, payload, token)
        if status == 409:
            user_url = f"{users_url}/{urllib.parse.quote(username, safe='')}"
            status, _ = request_json(
                "PUT",
                user_url,
                {"password": payload["password"], "is_superuser": False},
                token,
            )
        if status not in (200, 201, 204):
            raise RuntimeError(f"EMQX user setup failed for {user_var}: HTTP {status}")
    print("EMQX: MQTT users ready")


def main() -> int:
    actions = {"influx": setup_influx, "emqx": setup_emqx}
    if len(sys.argv) != 2 or sys.argv[1] not in actions:
        print("usage: bootstrap.py influx|emqx", file=sys.stderr)
        return 2
    actions[sys.argv[1]]()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
