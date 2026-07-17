"""Privacy-bounded PushPlus delivery for screening risk reminders."""
from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timezone
from typing import Callable
from urllib.request import Request, urlopen

from .schemas import UplinkPayload

log = logging.getLogger(__name__)

PUSHPLUS_URL = "https://www.pushplus.plus/send"
PUSHPLUS_TIMEOUT_SECONDS = 8
MAX_RESPONSE_BYTES = 64 * 1024


class PushPlusNotifier:
    def __init__(
        self,
        *,
        enabled: bool,
        token: str,
        device_name: str = "",
        opener: Callable = urlopen,
    ) -> None:
        self._configured = bool(enabled and token.strip())
        self._token = token.strip()
        self._device_name = device_name.strip()
        self._opener = opener
        self._limited = False
        self._lock = threading.Lock()

    @classmethod
    def from_env(cls) -> "PushPlusNotifier":
        enabled = os.environ.get("PUSHPLUS_ENABLED", "0").strip().lower()
        return cls(
            enabled=enabled in {"1", "true", "yes", "on"},
            token=os.environ.get("PUSHPLUS_TOKEN", ""),
            device_name=os.environ.get("PUSHPLUS_DEVICE_NAME", ""),
        )

    @property
    def enabled(self) -> bool:
        with self._lock:
            return self._configured and not self._limited

    @staticmethod
    def _score(value: int | None) -> str:
        return "--" if value is None else str(value)

    def _content(self, device_id: str, uplink: UplinkPayload, advice_text: str) -> str:
        scores = uplink.scores
        event_time = datetime.fromtimestamp(uplink.ts, tz=timezone.utc).isoformat()
        display_name = self._device_name or device_id
        return "\n".join((
            "## StrokeGuard risk reminder",
            f"- Device: {display_name} ({device_id})",
            f"- Event time (UTC): {event_time}",
            f"- Level: **{uplink.level}**",
            (
                f"- Scores: F: {self._score(scores.face)} | "
                f"S: {self._score(scores.speech)} | "
                f"T: {self._score(scores.tongue)} | "
                f"E: {self._score(scores.eye)} | "
                f"CSI: {self._score(scores.csi)} | Final: {scores.final}"
            ),
            "",
            advice_text,
            "",
            "> This is a risk reminder, not a diagnosis. For sudden FAST/BE-FAST signs, seek emergency medical care immediately.",
        ))

    def send(self, device_id: str, uplink: UplinkPayload, advice_text: str) -> bool:
        if not self.enabled:
            return False
        payload = {
            "token": self._token,
            "title": f"StrokeGuard {uplink.level} reminder",
            "content": self._content(device_id, uplink, advice_text),
            "template": "markdown",
            "channel": "wechat",
        }
        request = Request(
            PUSHPLUS_URL,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        try:
            with self._opener(request, timeout=PUSHPLUS_TIMEOUT_SECONDS) as response:
                result = json.loads(response.read(MAX_RESPONSE_BYTES).decode("utf-8"))
            code = result.get("code") if isinstance(result, dict) else None
            if code == 200:
                log.info("PushPlus accepted alert for %s level=%s", device_id, uplink.level)
                return True
            if code == 900:
                with self._lock:
                    self._limited = True
                log.error("PushPlus disabled after provider code 900 for %s", device_id)
                return False
            safe_code = code if isinstance(code, int) and not isinstance(code, bool) else "invalid"
            log.warning("PushPlus rejected alert for %s code=%s", device_id, safe_code)
            return False
        except Exception as error:
            log.warning(
                "PushPlus request failed for %s error=%s",
                device_id,
                type(error).__name__,
            )
            return False
