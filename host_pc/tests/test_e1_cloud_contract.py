import asyncio
import importlib
import json
import sys
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
    bridge.latest = {}
    bridge._advisor = FailingAdvisor()
    bridge._client = Client()
    bridge._influx = Influx()

    asyncio.run(bridge._handle_advice("sg-0001", UplinkPayload(**valid_payload())))

    _, downlink = bridge._client.published
    assert downlink["source"] == "fallback"
    assert "sensitive provider" not in downlink["advice_text"]
    assert "request id" not in downlink["advice_text"]
    assert "120" in downlink["advice_text"]
