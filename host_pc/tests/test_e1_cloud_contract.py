import asyncio
import importlib
import json
import sys
import threading
import types
from pathlib import Path

import pytest
from pydantic import ValidationError


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from cloud.backend.app.schemas import UplinkPayload


def valid_payload():
    return {
        "schema_version": 1,
        "scores": {
            "face": None,
            "speech": None,
            "tongue": None,
            "eye": None,
            "csi": 80,
            "final": 0,
        },
        "level": "insufficient",
        "profile": {
            "age": 68,
            "gender": "other",
            "conditions": [],
            "meds": [],
            "stroke_history": False,
        },
        "reasons": ["avail weight sum 0.08 < 0.50"],
        "veto_by": [],
        "device_id": "sg-0001",
        "ts": 1783760000,
        "seq": 1,
    }


@pytest.mark.parametrize(
    "field,value",
    [
        ("jpeg_b64", "/9j/"),
        ("mfcc", [[0.1]]),
        ("landmarks", [[1, 2]]),
        ("roi", "raw"),
    ],
)
def test_uplink_rejects_raw_or_unknown_fields(field, value):
    payload = valid_payload()
    payload[field] = value
    with pytest.raises(ValidationError):
        UplinkPayload(**payload)


def test_uplink_accepts_versioned_numeric_payload():
    parsed = UplinkPayload(**valid_payload())
    assert parsed.schema_version == 1
    assert parsed.seq == 1
    assert parsed.scores.csi == 80


def test_bridge_checks_topic_device_before_storage():
    source = (ROOT / "cloud" / "backend" / "app" / "mqtt_bridge.py").read_text(
        encoding="utf-8"
    )
    check = "if up.device_id != device_id:"
    assert check in source
    assert source.index(check) < source.index("self._influx.write_uplink")


def test_bridge_records_received_at_only_after_validating_uplink(monkeypatch):
    fake_influx_module = types.ModuleType("cloud.backend.app.db_influx")
    fake_influx_module.InfluxWriter = object
    monkeypatch.setitem(sys.modules, "cloud.backend.app.db_influx", fake_influx_module)
    sys.modules.pop("cloud.backend.app.mqtt_bridge", None)
    mqtt_bridge = importlib.import_module("cloud.backend.app.mqtt_bridge")

    class Influx:
        @staticmethod
        def write_uplink(*args, **kwargs):
            return None

    bridge = mqtt_bridge.MqttBridge.__new__(mqtt_bridge.MqttBridge)
    bridge.latest = {}
    bridge._cache_lock = threading.RLock()
    bridge._influx = Influx()
    bridge._loop = object()
    monkeypatch.setattr(mqtt_bridge.time, "time", lambda: 1234.5)

    def discard(coro, loop):
        coro.close()

    monkeypatch.setattr(mqtt_bridge.asyncio, "run_coroutine_threadsafe", discard)

    for topic, payload in (
        ("invalid/topic", valid_payload()),
        ("strokeguard/sg-0001/uplink", b"not-json"),
        ("strokeguard/sg-0001/uplink", {"device_id": "sg-0001"}),
        ("strokeguard/sg-0001/uplink", {**valid_payload(), "device_id": "sg-0002"}),
    ):
        encoded = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
        bridge._on_message(None, None, types.SimpleNamespace(topic=topic, payload=encoded))
        assert bridge.latest == {}

    bridge._on_message(
        None,
        None,
        types.SimpleNamespace(
            topic="strokeguard/sg-0001/uplink",
            payload=json.dumps(valid_payload()).encode("utf-8"),
        ),
    )

    assert bridge.latest["sg-0001"]["received_at"] == 1234.5


def test_bridge_cache_snapshot_returns_an_isolated_copy(monkeypatch):
    fake_influx_module = types.ModuleType("cloud.backend.app.db_influx")
    fake_influx_module.InfluxWriter = object
    monkeypatch.setitem(sys.modules, "cloud.backend.app.db_influx", fake_influx_module)
    sys.modules.pop("cloud.backend.app.mqtt_bridge", None)
    mqtt_bridge = importlib.import_module("cloud.backend.app.mqtt_bridge")

    bridge = mqtt_bridge.MqttBridge.__new__(mqtt_bridge.MqttBridge)
    bridge._cache_lock = threading.RLock()
    bridge.latest = {"sg-0001": {"uplink": UplinkPayload(**valid_payload()), "received_at": 1234.5}}

    snapshot = bridge.cache_snapshot("sg-0001")

    assert snapshot == bridge.latest["sg-0001"]
    assert snapshot is not bridge.latest["sg-0001"]
    snapshot["received_at"] = 0
    assert bridge.cache_snapshot("sg-0001")["received_at"] == 1234.5


def test_bridge_discards_advice_when_a_newer_uplink_arrives_during_generation(monkeypatch):
    fake_influx_module = types.ModuleType("cloud.backend.app.db_influx")
    fake_influx_module.InfluxWriter = object
    monkeypatch.setitem(sys.modules, "cloud.backend.app.db_influx", fake_influx_module)
    sys.modules.pop("cloud.backend.app.mqtt_bridge", None)
    mqtt_bridge = importlib.import_module("cloud.backend.app.mqtt_bridge")

    started = threading.Event()
    release = threading.Event()

    class BlockingAdvisor:
        available = True
        model = "test-advisor"

        @staticmethod
        def generate(*args):
            started.set()
            assert release.wait(timeout=1)
            return "stale advice", 12

    class Client:
        published = []

        def publish(self, topic, payload, **kwargs):
            self.published.append((topic, json.loads(payload)))

    class Influx:
        advice_writes = []

        @staticmethod
        def write_uplink(*args, **kwargs):
            return None

        @staticmethod
        def write_advice(*args):
            Influx.advice_writes.append(args)

    bridge = mqtt_bridge.MqttBridge.__new__(mqtt_bridge.MqttBridge)
    bridge.latest = {}
    bridge._cache_lock = threading.RLock()
    bridge._advisor = BlockingAdvisor()
    bridge._client = Client()
    bridge._influx = Influx()
    bridge._loop = object()
    monkeypatch.setattr(mqtt_bridge.time, "time", lambda: 1234.5)

    scheduled = []

    def schedule(coro, loop):
        scheduled.append(coro)

    monkeypatch.setattr(mqtt_bridge.asyncio, "run_coroutine_threadsafe", schedule)

    first = valid_payload()
    second = {**valid_payload(), "seq": 2, "ts": 1783760001}
    bridge._on_message(
        None,
        None,
        types.SimpleNamespace(topic="strokeguard/sg-0001/uplink", payload=json.dumps(first).encode("utf-8")),
    )

    task = threading.Thread(target=lambda: asyncio.run(scheduled.pop()))
    task.start()
    assert started.wait(timeout=1)

    bridge._on_message(
        None,
        None,
        types.SimpleNamespace(topic="strokeguard/sg-0001/uplink", payload=json.dumps(second).encode("utf-8")),
    )
    scheduled.pop().close()
    release.set()
    task.join(timeout=1)

    assert not task.is_alive()
    assert bridge.latest["sg-0001"]["uplink"].seq == 2
    assert "advice" not in bridge.latest["sg-0001"]
    assert bridge._client.published == []
    assert bridge._influx.advice_writes == []


def test_bridge_fallback_hides_provider_exception(monkeypatch):
    fake_influx_module = types.ModuleType("cloud.backend.app.db_influx")
    fake_influx_module.InfluxWriter = object
    monkeypatch.setitem(sys.modules, "cloud.backend.app.db_influx", fake_influx_module)
    sys.modules.pop("cloud.backend.app.mqtt_bridge", None)
    mqtt_bridge = importlib.import_module("cloud.backend.app.mqtt_bridge")

    class FailingAdvisor:
        available = True
        model = "provider-endpoint"

        @staticmethod
        def generate(*args):
            raise RuntimeError("sensitive provider request id")

    class Client:
        published = None

        def publish(self, topic, payload, **kwargs):
            self.published = (topic, json.loads(payload))

    class Influx:
        @staticmethod
        def write_advice(*args):
            return None

    bridge = mqtt_bridge.MqttBridge.__new__(mqtt_bridge.MqttBridge)
    uplink = UplinkPayload(**valid_payload())
    bridge.latest = {"sg-0001": {"uplink": uplink, "generation": 1}}
    bridge._cache_lock = threading.RLock()
    bridge._advisor = FailingAdvisor()
    bridge._client = Client()
    bridge._influx = Influx()

    asyncio.run(bridge._handle_advice("sg-0001", uplink, 1))

    _, downlink = bridge._client.published
    assert downlink["source"] == "fallback"
    assert "sensitive provider" not in downlink["advice_text"]
    assert "request id" not in downlink["advice_text"]
    assert "120" in downlink["advice_text"]
