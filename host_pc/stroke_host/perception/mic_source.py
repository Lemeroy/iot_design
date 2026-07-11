"""麦克风采集 (sounddevice, 系统默认输入).

用法:
    mic = MicSource(sample_rate=16000, chunk_sec=1.5)
    with mic:
        for chunk in mic.stream():
            audio = chunk.samples  # np.ndarray float32 [-1,1] shape (N,)
"""
from __future__ import annotations

import logging
import queue
import threading
from dataclasses import dataclass
from typing import Iterator, Optional

import numpy as np

log = logging.getLogger(__name__)


@dataclass
class AudioChunk:
    samples: np.ndarray   # float32 mono [-1, 1]
    sample_rate: int
    ts: float


class MicSource:
    def __init__(self, sample_rate: int = 16000, chunk_sec: float = 1.5,
                 device: Optional[int | str] = None) -> None:
        self.sr = sample_rate
        self.chunk_sec = chunk_sec
        self.chunk_n = int(sample_rate * chunk_sec)
        self.device = device
        self._q: queue.Queue[AudioChunk] = queue.Queue(maxsize=8)
        self._buf = np.zeros(0, dtype=np.float32)
        self._stream = None
        self._lock = threading.Lock()

    def _callback(self, indata, frames, time_info, status):
        if status:
            log.debug("mic status: %s", status)
        import time as _t
        with self._lock:
            self._buf = np.concatenate([self._buf, indata[:, 0].astype(np.float32)])
            while self._buf.shape[0] >= self.chunk_n:
                seg = self._buf[:self.chunk_n]
                self._buf = self._buf[self.chunk_n:]
                try:
                    self._q.put_nowait(AudioChunk(seg.copy(), self.sr, _t.time()))
                except queue.Full:
                    pass

    def open(self) -> None:
        try:
            import sounddevice as sd
        except (ImportError, OSError) as e:
            raise RuntimeError(f"sounddevice not available: {e}") from e
        self._stream = sd.InputStream(
            samplerate=self.sr, channels=1, dtype="float32",
            blocksize=0, device=self.device, callback=self._callback,
        )
        self._stream.start()
        log.info("mic opened sr=%d chunk=%.2fs", self.sr, self.chunk_sec)

    def close(self) -> None:
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None

    def __enter__(self) -> "MicSource":
        self.open()
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def stream(self) -> Iterator[AudioChunk]:
        while True:
            yield self._q.get()
