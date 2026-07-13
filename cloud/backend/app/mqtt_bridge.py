"""EMQX MQTT 桥: sub uplink -> Influx + LLM -> pub downlink.

线程模型: 独立线程跑 paho-mqtt loop, 用 asyncio.run_coroutine_threadsafe 把
LLM 生成任务丢到 FastAPI 的 event loop 里执行 (避免阻塞 MQTT 心跳).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import threading
import time
import paho.mqtt.client as mqtt

from .db_influx import InfluxWriter
from .llm_advice import DoubaoAdvisor
from .schemas import DownlinkPayload, UplinkPayload

log = logging.getLogger(__name__)

TOPIC_UPLINK = "strokeguard/+/uplink"
TOPIC_DOWNLINK_FMT = "strokeguard/{device_id}/downlink"
DEVICE_RE = re.compile(r"^strokeguard/([^/]+)/uplink$")


class MqttBridge:
    def __init__(self,
                 loop: asyncio.AbstractEventLoop,
                 advisor: DoubaoAdvisor,
                 influx: InfluxWriter) -> None:
        self._loop = loop
        self._advisor = advisor
        self._influx = influx

        self.host = os.environ.get("MQTT_HOST", "emqx")
        self.port = int(os.environ.get("MQTT_PORT", "1883"))
        self.user = os.environ.get("MQTT_USER", "")
        self.pwd = os.environ.get("MQTT_PASS", "")
        self._client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"sg-backend-{int(time.time())}",
        )
        if self.user:
            self._client.username_pw_set(self.user, self.pwd)
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message

        self._connected = threading.Event()
        self._stop = threading.Event()

        # 最新缓存 (只保内存, InfluxDB 保长历史)
        self.latest = {}  # device_id -> {"uplink": UplinkPayload, "advice": DownlinkPayload}
        self._cache_lock = threading.RLock()

    def cache_snapshot(self, device_id: str) -> dict | None:
        """Return a consistent, isolated view of one device's latest cache."""
        with self._cache_lock:
            cache = self.latest.get(device_id)
            return dict(cache) if isinstance(cache, dict) else None

    def _generation_is_current(self, device_id: str, generation: int) -> bool:
        with self._cache_lock:
            cache = self.latest.get(device_id)
            return isinstance(cache, dict) and cache.get("generation") == generation

    def connected(self) -> bool:
        return self._connected.is_set() and self._client.is_connected()

    def start(self) -> None:
        log.info("mqtt bridge connecting %s:%d as %s", self.host, self.port, self.user or "-")
        self._client.connect_async(self.host, self.port, keepalive=30)
        self._client.loop_start()

    def stop(self) -> None:
        self._stop.set()
        try:
            self._client.disconnect()
        except Exception:
            pass
        self._client.loop_stop()

    # ---- paho callbacks ----
    def _on_connect(self, client, userdata, flags, rc, props=None):
        if rc == 0:
            self._connected.set()
            log.info("mqtt connected, subscribe %s", TOPIC_UPLINK)
            client.subscribe(TOPIC_UPLINK, qos=1)
        else:
            log.warning("mqtt connect failed rc=%s", rc)

    def _on_disconnect(self, client, userdata, flags, rc, props=None):
        self._connected.clear()
        log.warning("mqtt disconnected rc=%s", rc)

    def _on_message(self, client, userdata, msg):
        m = DEVICE_RE.match(msg.topic)
        if not m:
            return
        device_id = m.group(1)
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except Exception as e:
            log.warning("bad uplink json from %s: %s", device_id, e)
            return
        try:
            up = UplinkPayload(**payload)
        except Exception as e:
            log.warning("uplink schema error from %s: %s", device_id, e)
            return
        if up.device_id != device_id:
            log.warning("uplink device mismatch topic=%s", device_id)
            return

        # Influx 写入放本线程 (轻量)
        # Store receipt time only after JSON, schema, and topic-device validation.
        received_at = time.time()
        with self._cache_lock:
            cache = self.latest.setdefault(device_id, {})
            generation = int(cache.get("generation", 0)) + 1
            cache["generation"] = generation
            cache["uplink"] = up
            cache["received_at"] = received_at
            cache.pop("advice", None)

        self._influx.write_uplink(
            device_id=up.device_id, scores=up.scores,
            level=up.level, profile=up.profile, ts_sec=up.ts,
        )

        # 缓存

        # LLM 调用: 交给 asyncio loop 做, 避免阻塞 mqtt 线程
        asyncio.run_coroutine_threadsafe(
            self._handle_advice(device_id, up, generation), self._loop
        )

    # ---- async LLM ----
    async def _handle_advice(self, device_id: str, up: UplinkPayload, generation: int) -> None:
        # 简单节流: normal 级别每 60s 才发一次建议, warning/danger 立即
        with self._cache_lock:
            cache = self.latest.get(device_id)
            if not isinstance(cache, dict) or cache.get("generation") != generation:
                return
            last_advice_ts = cache.get("last_advice_ts")
        now = int(time.time())
        if (
            up.level == "normal"
            and isinstance(last_advice_ts, int)
            and (now - last_advice_ts) < 60
        ):
            return

        try:
            advice_text, latency = await asyncio.to_thread(
                self._advisor.generate,
                up.scores, up.level, up.profile, up.reasons,
            )
            advice_source = self._advisor.model if self._advisor.available else "fallback"
        except Exception as e:
            log.exception("advisor err")
            advice_text = "建议服务暂时不可用；请以镜端风险提示为准，如有突发症状立即拨打120。"
            latency = 0
            advice_source = "fallback"

        down = DownlinkPayload(
            level=up.level,
            advice_text=advice_text,
            ts=now,
            source=advice_source,
        )
        with self._cache_lock:
            cache = self.latest.get(device_id)
            if not isinstance(cache, dict) or cache.get("generation") != generation:
                return
            cache["advice"] = down
            cache["last_advice_ts"] = down.ts

        # 发布 downlink
        if not self._generation_is_current(device_id, generation):
            return
        topic = TOPIC_DOWNLINK_FMT.format(device_id=device_id)
        self._client.publish(topic, down.model_dump_json(), qos=1, retain=False)
        log.info("downlink -> %s (%d ms, %d chars)", topic, latency, len(advice_text))

        # Influx 记录 advice
        if not self._generation_is_current(device_id, generation):
            return
        self._influx.write_advice(device_id, up.level, advice_text, latency)
