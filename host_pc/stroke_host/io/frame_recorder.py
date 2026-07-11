"""帧落盘 + 24h 自动清理.

结构:
    data/session_YYYYMMDD_HHMMSS/frames.jsonl.enc     每行: base64(AES-GCM(json))
    data/session_YYYYMMDD_HHMMSS/manifest.json        明文元数据 (device_id, start_ts)

清理:
    后台线程每 30 分钟扫描 data/ 下所有 session_*, mtime 早于 24h 则整目录删除.

隐私边界:
    M1a 只落 heartbeat + csi_score, 无音视频原始数据.
    加密使用 utils.crypto.AesGcm (keyring 管理 master key).
"""
from __future__ import annotations

import base64
import json
import logging
import shutil
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from ..utils.crypto import AesGcm
from .cdc_reader import Frame

log = logging.getLogger(__name__)

RETENTION_SEC = 24 * 3600
SWEEP_INTERVAL_SEC = 30 * 60


class FrameRecorder:
    def __init__(self, root: str | Path = "data", device_id: str = "sg-0001") -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.device_id = device_id
        self._aes = AesGcm()
        self._session_dir: Optional[Path] = None
        self._fp = None
        self._sweep_thread: Optional[threading.Thread] = None
        self._stop_evt = threading.Event()
        self._lock = threading.Lock()

    # ---------- lifecycle ----------
    def open(self) -> None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._session_dir = self.root / f"session_{ts}"
        self._session_dir.mkdir(parents=True, exist_ok=True)

        manifest = {
            "device_id": self.device_id,
            "start_ts": int(time.time()),
            "version": "m1a-0.1",
        }
        (self._session_dir / "manifest.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )
        self._fp = (self._session_dir / "frames.jsonl.enc").open("ab")

        # 启动清理线程
        self._stop_evt.clear()
        self._sweep_thread = threading.Thread(
            target=self._sweep_loop, name="rec-sweep", daemon=True
        )
        self._sweep_thread.start()
        log.info("recorder opened: %s", self._session_dir)

    def close(self) -> None:
        self._stop_evt.set()
        with self._lock:
            if self._fp:
                self._fp.close()
                self._fp = None
        if self._sweep_thread and self._sweep_thread.is_alive():
            self._sweep_thread.join(timeout=2)
        log.info("recorder closed")

    def __enter__(self) -> "FrameRecorder":
        self.open()
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ---------- write ----------
    def write(self, frame: Frame) -> None:
        rec = {
            "t": frame.ts_recv,
            "type": frame.type,
            "payload_b64": base64.b64encode(frame.payload).decode("ascii"),
        }
        plaintext = json.dumps(rec, separators=(",", ":")).encode("utf-8")
        blob = self._aes.encrypt(plaintext, aad=self.device_id.encode())
        line = base64.b64encode(blob) + b"\n"
        with self._lock:
            if self._fp is None:
                raise RuntimeError("recorder not opened")
            self._fp.write(line)
            self._fp.flush()

    # ---------- 24h sweep ----------
    def _sweep_once(self) -> int:
        cutoff = time.time() - RETENTION_SEC
        deleted = 0
        for p in self.root.glob("session_*"):
            try:
                if not p.is_dir():
                    continue
                if p == self._session_dir:
                    continue
                if p.stat().st_mtime < cutoff:
                    shutil.rmtree(p, ignore_errors=True)
                    deleted += 1
                    log.info("sweep: removed %s", p.name)
            except OSError as e:
                log.warning("sweep err on %s: %s", p, e)
        return deleted

    def _sweep_loop(self) -> None:
        # 启动时先扫一次
        self._sweep_once()
        while not self._stop_evt.wait(SWEEP_INTERVAL_SEC):
            self._sweep_once()

    # ---------- helper for tests ----------
    def sweep_now(self) -> int:
        return self._sweep_once()
