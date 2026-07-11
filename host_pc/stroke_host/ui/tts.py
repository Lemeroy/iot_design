"""pyttsx3 语音播报 (SAPI5, Windows 自带).

设计:
  - 独立后台线程 + queue.Queue, 主线程 speak() 只入队, 永不阻塞 UI
  - 相同文本冷却时间内不重复播报 (COOLDOWN_SEC)
  - stop() 幂等, 支持进程退出前排空
  - pyttsx3 未装时降级为 no-op, 打印 log
"""
from __future__ import annotations

import logging
import queue
import threading
import time
from typing import Optional

log = logging.getLogger(__name__)

COOLDOWN_SEC = 3.0
QUEUE_MAX = 8


class TtsWorker:
    def __init__(self, rate: int = 180, volume: float = 1.0,
                 voice_id: Optional[str] = None) -> None:
        self._q: queue.Queue[Optional[str]] = queue.Queue(maxsize=QUEUE_MAX)
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._engine = None
        self._last_text: Optional[str] = None
        self._last_ts: float = 0.0
        self._rate = rate
        self._volume = volume
        self._voice_id = voice_id
        self._available = False

    # ---- lifecycle ----
    def open(self) -> None:
        try:
            import pyttsx3
        except ImportError:
            log.warning("pyttsx3 not installed, TTS disabled")
            return
        try:
            self._engine = pyttsx3.init()
            self._engine.setProperty("rate", self._rate)
            self._engine.setProperty("volume", self._volume)
            if self._voice_id:
                self._engine.setProperty("voice", self._voice_id)
            else:
                # 尝试选中文语音
                for v in self._engine.getProperty("voices"):
                    name = (v.name or "").lower()
                    if "chinese" in name or "zh" in name or "huihui" in name:
                        self._engine.setProperty("voice", v.id)
                        break
            self._available = True
        except Exception as e:
            log.warning("pyttsx3 init failed: %s", e)
            self._engine = None
            return

        self._thread = threading.Thread(target=self._loop, name="tts", daemon=True)
        self._thread.start()
        log.info("TTS worker started")

    def close(self) -> None:
        self._stop.set()
        try:
            self._q.put_nowait(None)
        except queue.Full:
            pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
        if self._engine is not None:
            try:
                self._engine.stop()
            except Exception:
                pass
        self._engine = None

    def __enter__(self) -> "TtsWorker":
        self.open()
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ---- speak ----
    @property
    def available(self) -> bool:
        return self._available

    def speak(self, text: str, *, force: bool = False) -> None:
        """入队播报; 同文本冷却期内被丢弃 (除非 force=True)."""
        if not text or not self._available:
            return
        now = time.time()
        if not force and text == self._last_text and (now - self._last_ts) < COOLDOWN_SEC:
            return
        try:
            self._q.put_nowait(text)
            self._last_text = text
            self._last_ts = now
        except queue.Full:
            log.debug("tts queue full, drop: %s", text)

    def _loop(self) -> None:
        assert self._engine is not None
        while not self._stop.is_set():
            try:
                text = self._q.get(timeout=0.5)
            except queue.Empty:
                continue
            if text is None:
                break
            try:
                self._engine.say(text)
                self._engine.runAndWait()
            except Exception as e:
                log.debug("tts speak err: %s", e)
