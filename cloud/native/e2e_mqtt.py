#!/usr/bin/env python3
"""Run an internal numeric-only MQTT uplink/downlink smoke test."""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from pathlib import Path

import paho.mqtt.client as mqtt
from dotenv import load_dotenv


script_path = Path(__file__).resolve()
CLOUD_ROOT = Path.cwd() if script_path.name == "<stdin>" else script_path.parents[1]
load_dotenv(CLOUD_ROOT / ".env")

device_id = f"sg-e2e-{uuid.uuid4().hex[:8]}"
uplink_topic = f"strokeguard/{device_id}/uplink"
downlink_topic = f"strokeguard/{device_id}/downlink"
finished = threading.Event()
result: dict = {}


def fail(message: str) -> None:
    result["error"] = message
    finished.set()


def on_connect(client, userdata, flags, reason_code, properties=None):
    if reason_code.is_failure:
        fail(f"MQTT connect failed: {reason_code}")
        return
    client.subscribe(downlink_topic, qos=1)


def on_subscribe(client, userdata, mid, reason_codes, properties=None):
    if not reason_codes or any(code.is_failure for code in reason_codes):
        fail(f"MQTT subscribe denied: {reason_codes}")
        return
    payload = {
        "scores": {
            "face": 82,
            "speech": 78,
            "tongue": 85,
            "eye": 88,
            "csi": 80,
            "final": 82,
        },
        "level": "normal",
        "reasons": [],
        "veto_by": [],
        "profile": {
            "age": 68,
            "gender": "other",
            "conditions": ["hypertension"],
            "meds": [],
            "stroke_history": False,
        },
        "device_id": device_id,
        "ts": int(time.time()),
    }
    client.publish(uplink_topic, json.dumps(payload), qos=1)


def on_message(client, userdata, message):
    try:
        payload = json.loads(message.payload.decode("utf-8"))
        if not payload.get("advice_text"):
            raise ValueError("downlink advice is empty")
        result.update(
            {
                "result": "MQTT_E2E_OK",
                "level": payload.get("level"),
                "source": payload.get("source"),
                "advice_chars": len(payload["advice_text"]),
            }
        )
    except Exception as exc:
        result["error"] = f"bad downlink: {exc}"
    finished.set()


def main() -> int:
    username = os.environ.get("MQTT_HOST_USER", "")
    password = os.environ.get("MQTT_HOST_PASS", "")
    if not username or not password:
        raise RuntimeError("MQTT host credentials are missing")

    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        protocol=mqtt.MQTTv5,
        client_id=f"sg-e2e-{int(time.time())}",
    )
    client.username_pw_set(username, password)
    client.on_connect = on_connect
    client.on_subscribe = on_subscribe
    client.on_message = on_message
    client.connect("127.0.0.1", 1883, 20)
    client.loop_start()
    try:
        if not finished.wait(25):
            result["error"] = "MQTT E2E timed out"
    finally:
        client.disconnect()
        client.loop_stop()

    if "error" in result:
        print(result["error"])
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
