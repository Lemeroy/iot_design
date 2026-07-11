"""InfluxDB 2.x writer (仅数值评分, 不含原始媒体)."""
from __future__ import annotations

import logging
import os
import time
from typing import Optional

from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

from .schemas import Profile, Scores

log = logging.getLogger(__name__)


class InfluxWriter:
    def __init__(self,
                 url: Optional[str] = None,
                 token: Optional[str] = None,
                 org: Optional[str] = None,
                 bucket: Optional[str] = None) -> None:
        self.url = url or os.environ.get("INFLUX_URL", "http://influxdb:8086")
        self.token = token or os.environ.get("INFLUX_TOKEN", "")
        self.org = org or os.environ.get("INFLUX_ORG", "strokeguard")
        self.bucket = bucket or os.environ.get("INFLUX_BUCKET", "scores")
        self._client: Optional[InfluxDBClient] = None
        self._write_api = None
        self.available = bool(self.token)
        if self.available:
            try:
                self._client = InfluxDBClient(
                    url=self.url, token=self.token, org=self.org,
                    timeout=10_000,
                )
                self._write_api = self._client.write_api(write_options=SYNCHRONOUS)
                log.info("Influx connected url=%s org=%s bucket=%s",
                         self.url, self.org, self.bucket)
            except Exception as e:
                log.exception("Influx init failed: %s", e)
                self.available = False
        else:
            log.warning("INFLUX_TOKEN missing, writes will be skipped")

    def ping(self) -> bool:
        if not self.available or self._client is None:
            return False
        try:
            return self._client.ping()
        except Exception:
            return False

    def write_uplink(self, device_id: str, scores: Scores, level: str,
                     profile: Profile, ts_sec: int) -> None:
        if not self.available or self._write_api is None:
            return
        try:
            point = (
                Point("stroke_uplink")
                .tag("device_id", device_id)
                .tag("level", level)
                .tag("gender", profile.gender)
                .tag("stroke_history", "yes" if profile.stroke_history else "no")
                .field("face", int(scores.face if scores.face is not None else -1))
                .field("speech", int(scores.speech if scores.speech is not None else -1))
                .field("tongue", int(scores.tongue if scores.tongue is not None else -1))
                .field("eye", int(scores.eye if scores.eye is not None else -1))
                .field("csi", int(scores.csi if scores.csi is not None else -1))
                .field("final", int(scores.final))
                .field("age", int(profile.age))
                .time(ts_sec * 1_000_000_000, WritePrecision.NS)
            )
            self._write_api.write(bucket=self.bucket, org=self.org, record=point)
        except Exception as e:
            log.warning("influx write failed: %s", e)

    def write_advice(self, device_id: str, level: str,
                     advice_text: str, latency_ms: int) -> None:
        if not self.available or self._write_api is None:
            return
        try:
            point = (
                Point("stroke_advice")
                .tag("device_id", device_id)
                .tag("level", level)
                .field("advice_text", advice_text)
                .field("latency_ms", int(latency_ms))
                .time(int(time.time() * 1_000_000_000), WritePrecision.NS)
            )
            self._write_api.write(bucket=self.bucket, org=self.org, record=point)
        except Exception as e:
            log.warning("influx write advice failed: %s", e)

    def close(self) -> None:
        try:
            if self._write_api is not None:
                self._write_api.close()
            if self._client is not None:
                self._client.close()
        except Exception:
            pass
