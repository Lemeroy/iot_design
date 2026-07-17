"""EMQX MQTT uplink-to-advice bridge."""
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
from .alert_policy import AlertCoordinator
from .llm_advice import DoubaoAdvisor
from .pushplus import PushPlusNotifier
from .schemas import DownlinkPayload, UplinkPayload

log = logging.getLogger(__name__)

TOPIC_UPLINK = "strokeguard/+/uplink"
TOPIC_DOWNLINK_FMT = "strokeguard/{device_id}/downlink"
DEVICE_RE = re.compile(r"^strokeguard/([^/]+)/uplink$")


class MqttBridge:
    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        advisor: DoubaoAdvisor,
        influx: InfluxWriter,
        pushplus: PushPlusNotifier | None = None,
    ) -> None:
        self._loop = loop
        self._advisor = advisor
        self._influx = influx
        self._pushplus = pushplus or PushPlusNotifier(enabled=False, token="")
        self._alerts = AlertCoordinator()

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
        self.latest = {}
        self._cache_lock = threading.RLock()

    def cache_snapshot(self, device_id: str) -> dict | None:
        """Return a consistent, isolated view of one device's latest cache."""
        with self._cache_lock:
            cache = self.latest.get(device_id)
            return dict(cache) if isinstance(cache, dict) else None

    @staticmethod
    def _invalidate_advice_locked(cache: dict) -> None:
        generation = int(cache.get("generation", 0))
        cache["advice_barrier_generation"] = generation + 1
        for key in (
            "advice", "last_advice_ts", "pending_uplink", "pending_generation",
            "force_advice_level", "force_advice_generation",
        ):
            cache.pop(key, None)

    def invalidate_advice(self, device_id: str) -> None:
        """Invalidate advice from the previous guided screening."""
        with self._cache_lock:
            cache = self.latest.setdefault(device_id, {})
            self._invalidate_advice_locked(cache)

    @staticmethod
    def _advice_is_retained(last_advice_ts: object, now: int) -> bool:
        return (
            isinstance(last_advice_ts, int)
            and 0 <= now - last_advice_ts <= 300
        )

    def _is_stopping(self) -> bool:
        stop = getattr(self, "_stop", None)
        return stop is not None and stop.is_set()

    def _schedule_advice_worker(self, device_id: str, token: object) -> None:
        worker = self._advice_worker(device_id, token)
        try:
            asyncio.run_coroutine_threadsafe(worker, self._loop)
        except Exception:
            worker.close()
            log.exception("could not schedule advice worker for %s", device_id)
            with self._cache_lock:
                cache = self.latest.get(device_id)
                if isinstance(cache, dict) and cache.get("advice_worker") is token:
                    cache.pop("advice_worker", None)
                    cache.pop("pending_uplink", None)
                    cache.pop("pending_generation", None)

    def connected(self) -> bool:
        return self._connected.is_set() and self._client.is_connected()

    def publish_screening_control(self, device_id: str, action: str) -> bool:
        if action not in {"start", "cancel"} or not self.connected():
            return False
        topic = TOPIC_DOWNLINK_FMT.format(device_id=device_id)
        payload = json.dumps(
            {"type": "screening_control", "action": action},
            ensure_ascii=True,
            separators=(",", ":"),
        )
        info = self._client.publish(topic, payload, qos=1, retain=False)
        accepted = getattr(info, "rc", mqtt.MQTT_ERR_SUCCESS) == mqtt.MQTT_ERR_SUCCESS
        alerts = getattr(self, "_alerts", None)
        if accepted and isinstance(alerts, AlertCoordinator):
            if action == "start":
                alerts.start(device_id)
            else:
                alerts.cancel(device_id)
                with self._cache_lock:
                    cache = self.latest.get(device_id)
                    if isinstance(cache, dict):
                        cache.pop("force_advice_level", None)
                        cache.pop("force_advice_generation", None)
        return accepted

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
        except Exception as error:
            log.warning("bad uplink json from %s: %s", device_id, error)
            return
        try:
            up = UplinkPayload(**payload)
        except Exception as error:
            log.warning("uplink schema error from %s: %s", device_id, error)
            return
        if up.device_id != device_id:
            log.warning("uplink device mismatch topic=%s", device_id)
            return

        received_at = time.time()
        worker_token = None
        with self._cache_lock:
            cache = self.latest.setdefault(device_id, {})
            previous = cache.get("uplink")
            previous_stage = (
                previous.screening_stage
                if isinstance(previous, UplinkPayload) else 0
            )
            if up.screening_stage == 1 and previous_stage != 1:
                self._invalidate_advice_locked(cache)
                alerts = getattr(self, "_alerts", None)
                if isinstance(alerts, AlertCoordinator):
                    alerts.start(device_id)
            elif up.screening_stage == 7:
                alerts = getattr(self, "_alerts", None)
                if isinstance(alerts, AlertCoordinator):
                    alerts.cancel(device_id)
                cache.pop("force_advice_level", None)
                cache.pop("force_advice_generation", None)
            generation = int(cache.get("generation", 0)) + 1
            cache["generation"] = generation
            cache["uplink"] = up
            cache["received_at"] = received_at
            advice_eligible = (
                up.level != "insufficient"
                and up.screening_stage not in {1, 2, 3, 4, 5, 7}
            )
            alerts = getattr(self, "_alerts", None)
            alert_level = alerts.observe(device_id, up.level) if isinstance(
                alerts, AlertCoordinator
            ) else None
            if alert_level is not None and advice_eligible:
                cache["force_advice_level"] = alert_level
                cache["force_advice_generation"] = generation
            if advice_eligible:
                cache["pending_uplink"] = up
                cache["pending_generation"] = generation
                if cache.get("advice_worker") is None:
                    worker_token = object()
                    cache["advice_worker"] = worker_token

        try:
            self._influx.write_uplink(
                device_id=up.device_id,
                scores=up.scores,
                level=up.level,
                profile=up.profile,
                ts_sec=up.ts,
            )
        except Exception:
            log.exception("could not write uplink for %s", device_id)

        if worker_token is not None:
            self._schedule_advice_worker(device_id, worker_token)

    # ---- async LLM ----
    async def _advice_worker(self, device_id: str, token: object) -> None:
        """Iteratively drain one device's newest pending advice generation."""
        try:
            while True:
                with self._cache_lock:
                    cache = self.latest.get(device_id)
                    if not isinstance(cache, dict) or cache.get("advice_worker") is not token:
                        return
                    up = cache.pop("pending_uplink", None)
                    generation = cache.pop("pending_generation", None)
                    last_advice_ts = cache.get("last_advice_ts")
                    force_level = cache.get("force_advice_level")
                    force_generation = cache.get("force_advice_generation")

                if not isinstance(up, UplinkPayload) or not isinstance(generation, int):
                    return

                now = int(time.time())
                force_advice = (
                    force_level == up.level
                    and isinstance(force_generation, int)
                    and generation >= force_generation
                )
                if self._advice_is_retained(last_advice_ts, now) and not force_advice:
                    continue

                try:
                    advice_text, latency = await asyncio.to_thread(
                        self._advisor.generate,
                        up.scores,
                        up.level,
                        up.profile,
                        up.reasons,
                    )
                    advice_source = self._advisor.model if self._advisor.available else "fallback"
                except Exception:
                    log.exception("advisor err")
                    advice_text = (
                        "Advice service is temporarily unavailable; follow the displayed risk "
                        "level and call 120 for sudden symptoms."
                    )
                    latency = 0
                    advice_source = "fallback"

                down = DownlinkPayload(
                    level=up.level,
                    advice_text=advice_text,
                    ts=now,
                    source=advice_source,
                )
                accepted = False
                alert_uplink = None
                topic = TOPIC_DOWNLINK_FMT.format(device_id=device_id)
                with self._cache_lock:
                    cache = self.latest.get(device_id)
                    if not isinstance(cache, dict):
                        return
                    barrier = cache.get("advice_barrier_generation", 0)
                    if not isinstance(barrier, int):
                        barrier = 0
                    previous_generation = cache.get("advice_generation", 0)
                    if not isinstance(previous_generation, int):
                        previous_generation = 0
                    if generation >= barrier and generation >= previous_generation:
                        try:
                            self._client.publish(
                                topic, down.model_dump_json(), qos=1, retain=False
                            )
                        except Exception:
                            log.exception(
                                "could not publish advice for %s generation %s",
                                device_id, generation,
                            )
                        else:
                            cache["advice"] = down
                            cache["advice_generation"] = generation
                            cache["last_advice_ts"] = down.ts
                            accepted = True
                            current_force_level = cache.get("force_advice_level")
                            current_force_generation = cache.get("force_advice_generation")
                            if (
                                current_force_level == up.level
                                and isinstance(current_force_generation, int)
                                and generation >= current_force_generation
                            ):
                                cache.pop("force_advice_level", None)
                                cache.pop("force_advice_generation", None)
                                alerts = getattr(self, "_alerts", None)
                                if isinstance(alerts, AlertCoordinator):
                                    alerts.mark_dispatched(device_id, up.level)
                                alert_uplink = up

                if not accepted:
                    log.info(
                        "discard stale advice for %s generation %s",
                        device_id, generation,
                    )
                    continue

                log.info("downlink -> %s (%d ms, %d chars)", topic, latency, len(advice_text))

                if alert_uplink is not None:
                    pushplus = getattr(self, "_pushplus", None)
                    if pushplus is not None:
                        try:
                            await asyncio.to_thread(
                                pushplus.send, device_id, alert_uplink, advice_text
                            )
                        except Exception:
                            log.exception("PushPlus worker failed for %s", device_id)

                try:
                    self._influx.write_advice(device_id, up.level, advice_text, latency)
                except Exception:
                    log.exception("could not write advice for %s generation %s", device_id, generation)
        finally:
            replacement_token = None
            with self._cache_lock:
                cache = self.latest.get(device_id)
                if isinstance(cache, dict) and cache.get("advice_worker") is token:
                    cache.pop("advice_worker", None)
                    if (
                        not self._is_stopping()
                        and isinstance(cache.get("pending_uplink"), UplinkPayload)
                        and isinstance(cache.get("pending_generation"), int)
                    ):
                        replacement_token = object()
                        cache["advice_worker"] = replacement_token
            if replacement_token is not None:
                self._schedule_advice_worker(device_id, replacement_token)
