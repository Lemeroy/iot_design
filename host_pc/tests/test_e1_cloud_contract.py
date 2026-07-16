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


def test_edge_contract_supports_strict_screening_control_and_stage_uplink():
    header = (ROOT / "firmware_esp32" / "main" / "cloud_contract.h").read_text(
        encoding="utf-8"
    )
    source = (ROOT / "firmware_esp32" / "main" / "cloud_contract.c").read_text(
        encoding="utf-8"
    )
    app = (ROOT / "firmware_esp32" / "main" / "app_main.c").read_text(
        encoding="utf-8"
    )

    for token in (
        "sg_cloud_parse_screening_control",
        '"screening_control"',
        '"start"',
        '"cancel"',
        '"screening_stage"',
    ):
        assert token in header or token in source
    assert "sg_camera_coprocessor_stage" in app
    assert "last_published_stage" in app
    for forbidden in ("jpeg_b64", "mfcc", "landmarks", '"roi"'):
        assert forbidden not in source.lower()
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


def test_bridge_keeps_completed_advice_when_a_newer_uplink_arrives_during_generation(monkeypatch):
    fake_influx_module = types.ModuleType("cloud.backend.app.db_influx")
    fake_influx_module.InfluxWriter = object
    monkeypatch.setitem(sys.modules, "cloud.backend.app.db_influx", fake_influx_module)
    sys.modules.pop("cloud.backend.app.mqtt_bridge", None)
    mqtt_bridge = importlib.import_module("cloud.backend.app.mqtt_bridge")

    started = threading.Event()
    release_first = threading.Event()
    second_started = threading.Event()
    release_second = threading.Event()

    class BlockingAdvisor:
        available = True
        model = "test-advisor"
        calls = 0

        @staticmethod
        def generate(*args):
            BlockingAdvisor.calls += 1
            if BlockingAdvisor.calls == 1:
                started.set()
                assert release_first.wait(timeout=1)
                return "stale advice", 12
            second_started.set()
            assert release_second.wait(timeout=1)
            return "current advice", 12

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
    second = {**valid_payload(), "level": "warning", "seq": 2, "ts": 1783760001}
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
    assert len(scheduled) == 0
    release_first.set()
    assert second_started.wait(timeout=1)

    assert bridge.latest["sg-0001"]["uplink"].seq == 2
    assert bridge.latest["sg-0001"]["uplink"].level == "warning"
    stale_advice = bridge.latest["sg-0001"]["advice"]
    assert stale_advice.advice_text == "stale advice"
    assert stale_advice.level == "insufficient"
    assert bridge._client.published == [
        ("strokeguard/sg-0001/downlink", {
            "schema_version": 1,
            "level": "insufficient",
            "advice_text": "stale advice",
            "ts": 1234,
            "source": "test-advisor",
        })
    ]
    assert bridge._influx.advice_writes == [("sg-0001", "insufficient", "stale advice", 12)]

    release_second.set()
    task.join(timeout=1)

    assert not task.is_alive()
    advice = bridge.latest["sg-0001"]["advice"]
    assert advice.advice_text == "current advice"
    assert advice.level == "warning"
    assert bridge._client.published == [
        ("strokeguard/sg-0001/downlink", {
            "schema_version": 1,
            "level": "insufficient",
            "advice_text": "stale advice",
            "ts": 1234,
            "source": "test-advisor",
        }),
        ("strokeguard/sg-0001/downlink", {
            "schema_version": 1,
            "level": "warning",
            "advice_text": "current advice",
            "ts": 1234,
            "source": "test-advisor",
        })
    ]
    assert bridge._influx.advice_writes == [
        ("sg-0001", "insufficient", "stale advice", 12),
        ("sg-0001", "warning", "current advice", 12),
    ]
    assert "await self._advice_worker" not in (
        (ROOT / "cloud" / "backend" / "app" / "mqtt_bridge.py").read_text(encoding="utf-8")
    )


def test_bridge_many_rapid_uplinks_schedule_one_worker_and_keep_newest_pending(monkeypatch):
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

    scheduled = []

    def schedule(coro, loop):
        scheduled.append(coro)

    monkeypatch.setattr(mqtt_bridge.asyncio, "run_coroutine_threadsafe", schedule)
    for seq in range(1, 21):
        payload = {**valid_payload(), "seq": seq, "ts": 1783760000 + seq}
        bridge._on_message(
            None,
            None,
            types.SimpleNamespace(
                topic="strokeguard/sg-0001/uplink",
                payload=json.dumps(payload).encode("utf-8"),
            ),
        )

    assert len(scheduled) == 1
    cache = bridge.latest["sg-0001"]
    assert cache["generation"] == 20
    assert cache["pending_generation"] == 20
    assert cache["pending_uplink"].seq == 20
    scheduled.pop().close()


def test_bridge_scheduler_failure_clears_its_pending_work_and_allows_a_later_uplink(monkeypatch):
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

    attempted = []

    def reject(coro, loop):
        attempted.append(coro)
        raise RuntimeError("event loop is closed")

    monkeypatch.setattr(mqtt_bridge.asyncio, "run_coroutine_threadsafe", reject)
    bridge._on_message(
        None,
        None,
        types.SimpleNamespace(
            topic="strokeguard/sg-0001/uplink", payload=json.dumps(valid_payload()).encode("utf-8")
        ),
    )

    cache = bridge.latest["sg-0001"]
    assert "advice_worker" not in cache
    assert "pending_uplink" not in cache
    assert "pending_generation" not in cache
    assert attempted[0].cr_frame is None

    scheduled = []
    monkeypatch.setattr(
        mqtt_bridge.asyncio, "run_coroutine_threadsafe", lambda coro, loop: scheduled.append(coro)
    )
    bridge._on_message(
        None,
        None,
        types.SimpleNamespace(
            topic="strokeguard/sg-0001/uplink",
            payload=json.dumps({**valid_payload(), "seq": 2}).encode("utf-8"),
        ),
    )

    assert len(scheduled) == 1
    assert bridge.latest["sg-0001"]["pending_generation"] == 2
    scheduled.pop().close()


def test_bridge_publish_and_influx_failures_do_not_strand_newer_pending_work(monkeypatch):
    fake_influx_module = types.ModuleType("cloud.backend.app.db_influx")
    fake_influx_module.InfluxWriter = object
    monkeypatch.setitem(sys.modules, "cloud.backend.app.db_influx", fake_influx_module)
    sys.modules.pop("cloud.backend.app.mqtt_bridge", None)
    mqtt_bridge = importlib.import_module("cloud.backend.app.mqtt_bridge")

    first_started = threading.Event()
    release_first = threading.Event()

    class Advisor:
        available = True
        model = "test-advisor"
        calls = []

        @staticmethod
        def generate(scores, level, profile, reasons):
            Advisor.calls.append(level)
            if level == "insufficient":
                first_started.set()
                assert release_first.wait(timeout=1)
            return f"advice-{level}", 12

    class Client:
        calls = 0
        published = []

        def publish(self, topic, payload, **kwargs):
            Client.calls += 1
            if Client.calls == 1:
                raise RuntimeError("mqtt unavailable")
            Client.published.append(json.loads(payload))

    class Influx:
        calls = 0

        @staticmethod
        def write_uplink(*args, **kwargs):
            return None

        @staticmethod
        def write_advice(*args):
            Influx.calls += 1
            if Influx.calls == 1:
                raise RuntimeError("influx unavailable")

    bridge = mqtt_bridge.MqttBridge.__new__(mqtt_bridge.MqttBridge)
    bridge.latest = {}
    bridge._cache_lock = threading.RLock()
    bridge._advisor = Advisor()
    bridge._client = Client()
    bridge._influx = Influx()
    bridge._loop = object()

    scheduled = []
    monkeypatch.setattr(mqtt_bridge.asyncio, "run_coroutine_threadsafe", lambda coro, loop: scheduled.append(coro))

    bridge._on_message(
        None,
        None,
        types.SimpleNamespace(topic="strokeguard/sg-0001/uplink", payload=json.dumps(valid_payload()).encode("utf-8")),
    )
    task = threading.Thread(target=lambda: asyncio.run(scheduled.pop()))
    task.start()
    assert first_started.wait(timeout=1)
    bridge._on_message(
        None,
        None,
        types.SimpleNamespace(
            topic="strokeguard/sg-0001/uplink",
            payload=json.dumps({**valid_payload(), "level": "warning", "seq": 2}).encode("utf-8"),
        ),
    )
    release_first.set()
    task.join(timeout=1)

    assert not task.is_alive()
    assert Advisor.calls == ["insufficient", "warning"]
    assert Client.published[-1]["advice_text"] == "advice-warning"
    assert "advice_worker" not in bridge.latest["sg-0001"]
    assert "pending_uplink" not in bridge.latest["sg-0001"]


def test_bridge_cancelled_worker_clears_its_token_and_schedules_one_replacement(monkeypatch):
    fake_influx_module = types.ModuleType("cloud.backend.app.db_influx")
    fake_influx_module.InfluxWriter = object
    monkeypatch.setitem(sys.modules, "cloud.backend.app.db_influx", fake_influx_module)
    sys.modules.pop("cloud.backend.app.mqtt_bridge", None)
    mqtt_bridge = importlib.import_module("cloud.backend.app.mqtt_bridge")

    class Advisor:
        available = True
        model = "test-advisor"

        @staticmethod
        def generate(*args):
            return "unused", 0

    class Influx:
        @staticmethod
        def write_uplink(*args, **kwargs):
            return None

        @staticmethod
        def write_advice(*args, **kwargs):
            return None

    bridge = mqtt_bridge.MqttBridge.__new__(mqtt_bridge.MqttBridge)
    bridge.latest = {}
    bridge._cache_lock = threading.RLock()
    bridge._advisor = Advisor()
    bridge._client = types.SimpleNamespace(publish=lambda *args, **kwargs: None)
    bridge._influx = Influx()
    bridge._loop = object()

    scheduled = []
    monkeypatch.setattr(mqtt_bridge.asyncio, "run_coroutine_threadsafe", lambda coro, loop: scheduled.append(coro))

    async def scenario():
        started = asyncio.Event()
        release = asyncio.Event()
        calls = 0

        async def controlled_to_thread(*args):
            nonlocal calls
            calls += 1
            if calls == 1:
                started.set()
                await release.wait()
            return "advice", 12

        monkeypatch.setattr(mqtt_bridge.asyncio, "to_thread", controlled_to_thread)
        bridge._on_message(
            None,
            None,
            types.SimpleNamespace(topic="strokeguard/sg-0001/uplink", payload=json.dumps(valid_payload()).encode("utf-8")),
        )
        worker = asyncio.create_task(scheduled.pop())
        await started.wait()
        bridge._on_message(
            None,
            None,
            types.SimpleNamespace(
                topic="strokeguard/sg-0001/uplink",
                payload=json.dumps({**valid_payload(), "level": "warning", "seq": 2}).encode("utf-8"),
            ),
        )
        worker.cancel()
        with pytest.raises(asyncio.CancelledError):
            await worker
        assert len(scheduled) == 1
        await scheduled.pop()

    asyncio.run(scenario())

    assert "advice_worker" not in bridge.latest["sg-0001"]
    assert bridge.latest["sg-0001"]["advice"].level == "warning"


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

    uplink = UplinkPayload(**valid_payload())
    token = object()
    bridge = mqtt_bridge.MqttBridge.__new__(mqtt_bridge.MqttBridge)
    bridge.latest = {
        "sg-0001": {
            "uplink": uplink,
            "generation": 1,
            "pending_uplink": uplink,
            "pending_generation": 1,
            "advice_worker": token,
        }
    }
    bridge._cache_lock = threading.RLock()
    bridge._advisor = FailingAdvisor()
    bridge._client = Client()
    bridge._influx = Influx()

    asyncio.run(bridge._advice_worker("sg-0001", token))

    _, downlink = bridge._client.published
    assert downlink["source"] == "fallback"
    assert "sensitive provider" not in downlink["advice_text"]
    assert "request id" not in downlink["advice_text"]
    assert "120" in downlink["advice_text"]
