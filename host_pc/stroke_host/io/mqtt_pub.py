"""host_pc -> 云端 MQTT 上下行客户端.

- Uplink: 每 N 帧或 fusion 状态变化时上传 (只上传数值 + profile)
- Downlink: 订阅 strokeguard/<device>/downlink 拿到 LLM 建议, 回调 UI

隐私铁律:
  - 严禁上传 jpeg_b64 / mfcc / 任何原始媒体
  - 严禁上传 raw 字段中的坐标细节 (只发聚合分)
"""
from __future__ import annotations

import json
import logging
import os
import ssl
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import paho.mqtt.client as mqtt

log = logging.getLogger(__name__)


@dataclass
class MqttConfig:
    host: str = "127.0.0.1"
    port: int = 1883
    tls: bool = False
    ca_cert: Optional[str] = None       # 自签 ca.crt 路径
    insecure: bool = True               # IP + 自签, 关 hostname 校验
    username: Optional[str] = None
    password: Optional[str] = None
    device_id: str = "sg-0001"

    @classmethod
    def from_env(cls) -> "MqttConfig":
        return cls(
            host=os.environ.get("SG_MQTT_HOST", "127.0.0.1"),
            port=int(os.environ.get("SG_MQTT_PORT", "1883")),
            tls=os.environ.get("SG_MQTT_TLS", "0") in ("1", "true", "yes"),
            ca_cert=os.environ.get("SG_MQTT_CA"),
            insecure=os.environ.get("SG_MQTT_INSECURE", "1") in ("1", "true", "yes"),
            username=os.environ.get("SG_MQTT_USER"),
            password=os.environ.get("SG_MQTT_PASS"),
            device_id=os.environ.get("SG_DEVICE_ID", "sg-0001"),
        )


AdviceCb = Callable[[dict], None]   # 回调 downlink 消息 dict


class MqttPublisher:
    """长连接客户端, 后台线程. publish 非阻塞."""

    def __init__(self, cfg: MqttConfig, on_advice: Optional[AdviceCb] = None) -> None:
        self.cfg = cfg
        self._on_advice = on_advice
        self._client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"sg-host-{cfg.device_id}-{int(time.time())}",
        )
        if cfg.username:
            self._client.username_pw_set(cfg.username, cfg.password or "")
        if cfg.tls:
            ca = cfg.ca_cert if cfg.ca_cert and Path(cfg.ca_cert).exists() else None
            self._client.tls_set(
                ca_certs=ca,
                cert_reqs=ssl.CERT_NONE if cfg.insecure else ssl.CERT_REQUIRED,
                tls_version=ssl.PROTOCOL_TLSv1_2,
            )
            if cfg.insecure:
                self._client.tls_insecure_set(True)

        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message
        self._connected = threading.Event()

        self.topic_uplink = f"strokeguard/{cfg.device_id}/uplink"
        self.topic_downlink = f"strokeguard/{cfg.device_id}/downlink"

        # 上传节流状态
        self._last_level: Optional[str] = None
        self._last_up_ts: float = 0.0
        self.n_pub = 0
        self.n_fail = 0

    def start(self) -> None:
        log.info("mqtt connecting %s:%d tls=%s", self.cfg.host, self.cfg.port, self.cfg.tls)
        self._client.connect_async(self.cfg.host, self.cfg.port, keepalive=30)
        self._client.loop_start()

    def stop(self) -> None:
        try:
            self._client.disconnect()
        except Exception:
            pass
        self._client.loop_stop()

    def connected(self) -> bool:
        return self._connected.is_set() and self._client.is_connected()

    # ---- publish ----
    def publish_uplink(self, scores: dict, level: str, reasons: list,
                       veto_by: list, profile: dict,
                       force: bool = False, min_interval_sec: float = 10.0) -> bool:
        """节流规则: level 变化 或 距上次 >= min_interval 或 force=True."""
        now = time.time()
        if not force:
            if level == self._last_level and (now - self._last_up_ts) < min_interval_sec:
                return False
        payload = {
            "scores": scores,
            "level": level,
            "reasons": reasons,
            "veto_by": veto_by,
            "profile": profile,
            "device_id": self.cfg.device_id,
            "ts": int(now),
        }
        try:
            info = self._client.publish(
                self.topic_uplink, json.dumps(payload, ensure_ascii=False),
                qos=1, retain=False,
            )
            if info.rc != mqtt.MQTT_ERR_SUCCESS:
                self.n_fail += 1
                return False
            self.n_pub += 1
            self._last_level = level
            self._last_up_ts = now
            return True
        except Exception as e:
            log.warning("publish err: %s", e)
            self.n_fail += 1
            return False

    # ---- callbacks ----
    def _on_connect(self, client, userdata, flags, rc, props=None):
        if rc == 0:
            self._connected.set()
            log.info("mqtt connected, subscribe %s", self.topic_downlink)
            client.subscribe(self.topic_downlink, qos=1)
        else:
            log.warning("mqtt connect failed rc=%s", rc)

    def _on_disconnect(self, client, userdata, flags, rc, props=None):
        self._connected.clear()
        log.warning("mqtt disconnected rc=%s", rc)

    def _on_message(self, client, userdata, msg):
        try:
            data = json.loads(msg.payload.decode("utf-8"))
        except Exception as e:
            log.debug("bad downlink: %s", e)
            return
        if self._on_advice is not None:
            try:
                self._on_advice(data)
            except Exception:
                log.exception("advice cb err")
