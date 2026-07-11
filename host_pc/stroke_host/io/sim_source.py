"""桩数据源: 无 ESP32 时用 PC 摄像头/麦克风模拟 heartbeat / frame 帧流.

两种模式:
  - "heartbeat" (默认): 1 Hz 空帧, csi_score 随机游走, 用于 M1a 联调
  - "synthetic-frame": 无外设合成最终 M1 frame 契约, 用于协议/算法联调
  - "real":  真源模式, 打开摄像头+麦克风, 产 type=0x02 frame 帧,
             payload = {"jpeg_b64": ..., "mfcc": [[..]], "csi_score": ..}
             用于 M2 感知算法开发, 帧率约 5 fps (与真机对齐)

产出与 cdc_reader.Frame 完全相同的对象, 下游 pipeline 零改动.
"""
from __future__ import annotations

import base64
import json
import logging
import queue
import random
import threading
import time
from typing import Iterator, Optional

import numpy as np

from .cdc_reader import Frame, TYPE_DATA, TYPE_HEARTBEAT

log = logging.getLogger(__name__)

FW_VERSION = "sim-m1a-0.1"
TINY_JPEG_B64 = base64.b64encode(b"\xff\xd8\xff\xd9").decode("ascii")


class SimSource:
    """1 Hz 心跳桩. 不依赖任何硬件."""

    def __init__(self, hz: float = 1.0) -> None:
        self.period = 1.0 / hz
        self._seq = 0
        self._csi = 85.0

    def open(self) -> None:
        log.info("SimSource started, %.1f Hz", 1.0 / self.period)

    def close(self) -> None:
        pass

    def __enter__(self) -> "SimSource":
        self.open()
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def _step_csi(self) -> int:
        self._csi += random.uniform(-4.0, 4.0)
        self._csi = max(50.0, min(98.0, self._csi))
        return int(round(self._csi))

    def frames(self) -> Iterator[Frame]:
        t_start = time.time()
        next_tick = t_start
        while True:
            now = time.time()
            if now < next_tick:
                time.sleep(next_tick - now)
            next_tick += self.period

            ts = int(time.time() - t_start)
            csi = self._step_csi()
            payload_obj = {
                "type": "heartbeat",
                "ts": ts,
                "seq": self._seq,
                "csi_score": csi,
                "fw": FW_VERSION,
            }
            self._seq += 1
            payload = json.dumps(payload_obj, separators=(",", ":")).encode("utf-8")
            yield Frame(type=TYPE_HEARTBEAT, payload=payload, ts_recv=time.time())


class SyntheticFrameSource:
    """No-sensor final frame source for M1 contract bring-up.

    It emits the same USB frame type and JSON shape the ESP32-S3 firmware will
    use once GC2145/INMP441 are wired. The JPEG is a tiny SOI/EOI placeholder,
    and MFCC is deterministic 13-coefficient data so tests and UI can run.
    """

    def __init__(self, hz: float = 5.0, csi_score: int = 80) -> None:
        self.period = 1.0 / hz
        self.csi_score = int(max(0, min(100, csi_score)))
        self._seq = 0

    def open(self) -> None:
        log.info("SyntheticFrameSource started, %.1f Hz", 1.0 / self.period)

    def close(self) -> None:
        pass

    def __enter__(self) -> "SyntheticFrameSource":
        self.open()
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    @staticmethod
    def _mfcc(seq: int) -> list[list[float]]:
        base = (seq % 10) / 10.0
        return [[round(base + j * 0.01, 4) for j in range(13)] for _ in range(4)]

    def frames(self) -> Iterator[Frame]:
        t_start = time.time()
        next_tick = t_start
        while True:
            now = time.time()
            if now < next_tick:
                time.sleep(next_tick - now)
            next_tick += self.period

            payload_obj = {
                "type": "frame",
                "ts": int(time.time() - t_start),
                "seq": self._seq,
                "jpeg_b64": TINY_JPEG_B64,
                "mfcc": self._mfcc(self._seq),
                "csi_score": self.csi_score,
                "fw": FW_VERSION,
            }
            self._seq += 1
            payload = json.dumps(payload_obj, separators=(",", ":")).encode("utf-8")
            yield Frame(type=TYPE_DATA, payload=payload, ts_recv=time.time())


class RealSource:
    """真源: PC 摄像头 + 麦克风 -> data 帧 (M2 用).

    - 摄像头 (cv2.VideoCapture) 5 fps, JPEG 编码
    - 麦克风 (sounddevice) 16 kHz mono, 每帧配 1.5s 音频算 MFCC
    - csi_score: 无, 置 null

    线程模型:
      cam 线程: 独立 5 fps 抓帧, 塞 latest_jpeg
      mic 线程: 独立回调, 累积到 1.5s 计算 MFCC, 塞 latest_mfcc
      frames(): 每 200ms 组一帧, latest_jpeg + latest_mfcc 快照
    """

    def __init__(self, cam_index: int = 0, fps: float = 5.0,
                 jpeg_quality: int = 80, sample_rate: int = 16000,
                 mfcc_chunk_sec: float = 1.5) -> None:
        self.cam_index = cam_index
        self.fps = fps
        self.period = 1.0 / fps
        self.jpeg_quality = jpeg_quality
        self.sample_rate = sample_rate
        self.mfcc_chunk_sec = mfcc_chunk_sec
        self._seq = 0
        self._stop = threading.Event()
        self._cam_thread: Optional[threading.Thread] = None
        self._latest_jpeg: Optional[bytes] = None
        self._latest_mfcc: Optional[np.ndarray] = None
        self._latest_audio: Optional[np.ndarray] = None
        self._lock = threading.Lock()
        self._mic = None

    # ---- lifecycle ----
    def open(self) -> None:
        # 摄像头
        import cv2
        self._cv2 = cv2
        cap = cv2.VideoCapture(self.cam_index, cv2.CAP_DSHOW)
        if not cap.isOpened():
            raise RuntimeError(f"camera {self.cam_index} open failed")
        self._cap = cap
        self._cam_thread = threading.Thread(target=self._cam_loop, daemon=True)
        self._cam_thread.start()

        # 麦克风 (延迟导入, 允许无声卡时降级)
        try:
            from ..perception.mic_source import MicSource
            self._mic = MicSource(sample_rate=self.sample_rate,
                                  chunk_sec=self.mfcc_chunk_sec)
            self._mic.open()
            self._mic_thread = threading.Thread(target=self._mic_loop, daemon=True)
            self._mic_thread.start()
        except Exception as e:
            log.warning("mic unavailable, video-only mode: %s", e)
            self._mic = None

        log.info("RealSource started cam=%d fps=%.1f mic=%s",
                 self.cam_index, self.fps, self._mic is not None)

    def close(self) -> None:
        self._stop.set()
        try:
            if self._cap:
                self._cap.release()
        except Exception:
            pass
        if self._mic is not None:
            self._mic.close()

    def __enter__(self) -> "RealSource":
        self.open()
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ---- worker loops ----
    def _cam_loop(self) -> None:
        while not self._stop.is_set():
            ok, bgr = self._cap.read()
            if not ok or bgr is None:
                time.sleep(0.05)
                continue
            ok, buf = self._cv2.imencode(
                ".jpg", bgr,
                [self._cv2.IMWRITE_JPEG_QUALITY, self.jpeg_quality],
            )
            if not ok:
                continue
            with self._lock:
                self._latest_jpeg = buf.tobytes()
            time.sleep(self.period)

    def _mic_loop(self) -> None:
        from ..perception.mfcc import compute_mfcc
        assert self._mic is not None
        for chunk in self._mic.stream():
            if self._stop.is_set():
                break
            try:
                mfcc = compute_mfcc(chunk.samples, chunk.sample_rate)
            except Exception as e:
                log.debug("mfcc err: %s", e)
                continue
            with self._lock:
                self._latest_mfcc = mfcc
                self._latest_audio = chunk.samples

    def latest_audio(self) -> Optional[np.ndarray]:
        with self._lock:
            return self._latest_audio.copy() if self._latest_audio is not None else None

    # ---- output ----
    def frames(self) -> Iterator[Frame]:
        t_start = time.time()
        next_tick = t_start
        while not self._stop.is_set():
            now = time.time()
            if now < next_tick:
                time.sleep(next_tick - now)
            next_tick += self.period

            with self._lock:
                jpeg = self._latest_jpeg
                mfcc = self._latest_mfcc

            if jpeg is None:
                continue

            payload_obj = {
                "type": "frame",
                "ts": int(time.time() - t_start),
                "seq": self._seq,
                "jpeg_b64": base64.b64encode(jpeg).decode("ascii"),
                "mfcc": (mfcc.tolist() if mfcc is not None else None),
                "csi_score": None,
                "fw": FW_VERSION,
            }
            self._seq += 1
            payload = json.dumps(payload_obj, separators=(",", ":")).encode("utf-8")
            yield Frame(type=TYPE_DATA, payload=payload, ts_recv=time.time())
