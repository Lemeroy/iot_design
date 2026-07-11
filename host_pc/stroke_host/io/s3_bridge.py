"""S3Bridge · PC 与 ESP32-S3 之间的 USB-CDC 双向桥.

用途:
  - 后台线程持续读 CDC, 把帧按类型分派 (heartbeat / fusion)
  - 前台可随时 send_scores() 把感知分发给 S3, 再 wait_fusion() 拿回融合结果
  - 断线自动重连 (可选, M4 阶段先不做)

线程模型:
  - _rx_thread 独占 serial.read
  - send_scores / send_frame 从任意线程调用 (pyserial 允许 read/write 并发)
  - 用 queue.Queue + Event 做等待

用法:
    bridge = S3Bridge("COM3")
    bridge.start()
    bridge.send_scores({"face":78,"speech":92,...}, seq=42)
    f = bridge.wait_fusion(seq=42, timeout=0.5)   # 或 pop_latest_fusion(timeout)
    if f: print(f["final"], f["level"])
    ...
    bridge.stop()
"""
from __future__ import annotations

import logging
import queue
import threading
import time
from typing import Callable, Optional

from .cdc_reader import (
    CdcReader,
    Frame,
    TYPE_FUSION,
    TYPE_HEARTBEAT,
)

log = logging.getLogger(__name__)


class S3Bridge:
    def __init__(self, port: str, baudrate: int = 115200,
                 on_heartbeat: Optional[Callable[[dict], None]] = None,
                 fusion_history: int = 32) -> None:
        self._reader = CdcReader(port, baudrate)
        self._rx_thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._fusion_q: queue.Queue = queue.Queue(maxsize=fusion_history)
        # seq -> fusion dict, 用于 wait_fusion(seq=..)
        self._by_seq: dict[int, dict] = {}
        self._by_seq_lock = threading.Lock()
        self._new_fusion = threading.Event()
        self._on_heartbeat = on_heartbeat
        self.n_heartbeats = 0
        self.n_fusion = 0
        self.n_bad = 0

    # ---- lifecycle ----
    def start(self) -> None:
        self._reader.open()
        self._stop.clear()
        self._rx_thread = threading.Thread(
            target=self._rx_loop, name="s3-bridge-rx", daemon=True)
        self._rx_thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._rx_thread and self._rx_thread.is_alive():
            self._rx_thread.join(timeout=2.0)
        self._reader.close()

    # ---- TX ----
    def send_scores(self, scores: dict, seq: int = 0) -> None:
        self._reader.send_scores(scores, seq=seq)

    # ---- RX ----
    def _rx_loop(self) -> None:
        try:
            for frame in self._reader.frames():
                if self._stop.is_set():
                    break
                self._dispatch(frame)
        except Exception as e:
            log.error("s3 rx loop crashed: %s", e)

    def _dispatch(self, frame: Frame) -> None:
        obj = frame.json
        if not isinstance(obj, dict):
            self.n_bad += 1
            return
        t = obj.get("type")
        if frame.type == TYPE_HEARTBEAT or t == "heartbeat":
            self.n_heartbeats += 1
            if self._on_heartbeat:
                try:
                    self._on_heartbeat(obj)
                except Exception as e:
                    log.debug("heartbeat cb err: %s", e)
        elif frame.type == TYPE_FUSION or t == "fusion":
            self.n_fusion += 1
            seq = obj.get("seq")
            if isinstance(seq, int):
                with self._by_seq_lock:
                    self._by_seq[seq] = obj
                    # 只保留最近 fusion_history 条
                    if len(self._by_seq) > 32:
                        old = sorted(self._by_seq.keys())[:-32]
                        for k in old:
                            self._by_seq.pop(k, None)
            # 也放入历史队列 (drop-oldest)
            try:
                self._fusion_q.put_nowait(obj)
            except queue.Full:
                try:
                    self._fusion_q.get_nowait()
                    self._fusion_q.put_nowait(obj)
                except queue.Empty:
                    pass
            self._new_fusion.set()
        else:
            # 未知类型, 忽略
            pass

    def wait_fusion(self, seq: int, timeout: float = 0.5) -> Optional[dict]:
        """阻塞等待指定 seq 的 fusion 帧. 超时返回 None."""
        deadline = time.monotonic() + timeout
        while True:
            with self._by_seq_lock:
                v = self._by_seq.get(seq)
                if v is not None:
                    return v
            remain = deadline - time.monotonic()
            if remain <= 0:
                return None
            self._new_fusion.clear()
            self._new_fusion.wait(timeout=min(remain, 0.05))

    def pop_latest_fusion(self, timeout: float = 0.5) -> Optional[dict]:
        try:
            return self._fusion_q.get(timeout=timeout)
        except queue.Empty:
            return None

    def stats(self) -> dict:
        return {
            "hb": self.n_heartbeats,
            "fu": self.n_fusion,
            "bad": self.n_bad,
        }
