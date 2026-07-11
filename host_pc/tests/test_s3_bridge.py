"""S3Bridge 双向环路测试 (用 FakeSerial)."""
from __future__ import annotations

import json
import threading
import time

import pytest

from stroke_host.io.cdc_reader import (
    MAGIC0, MAGIC1, VER, TYPE_HEARTBEAT, TYPE_FUSION, TYPE_SCORES,
)
from stroke_host.io.crc16 import crc16_ccitt
from stroke_host.io.s3_bridge import S3Bridge


def _make_frame(ftype: int, payload: bytes) -> bytes:
    plen = len(payload)
    hdr = bytes([MAGIC0, MAGIC1, VER, ftype, plen & 0xFF, (plen >> 8) & 0xFF])
    crc = crc16_ccitt(bytes([VER, ftype, plen & 0xFF, (plen >> 8) & 0xFF]) + payload)
    return hdr + payload + bytes([crc & 0xFF, (crc >> 8) & 0xFF])


class LoopSerial:
    """双向 FakeSerial. write 存到 tx_buf, read 从 rx_buf 消费."""

    def __init__(self) -> None:
        self.rx_buf = bytearray()
        self.tx_buf = bytearray()
        self._lock = threading.Lock()
        self.is_open = True
        self.timeout = 1.0
        self.write_timeout = 1.0

    def push_rx(self, data: bytes) -> None:
        with self._lock:
            self.rx_buf.extend(data)

    def read(self, n: int) -> bytes:
        # 阻塞式读 (模拟 pyserial timeout=1s)
        t_end = time.monotonic() + self.timeout
        while time.monotonic() < t_end:
            with self._lock:
                if self.rx_buf:
                    n = min(n, len(self.rx_buf))
                    out = bytes(self.rx_buf[:n])
                    del self.rx_buf[:n]
                    return out
            time.sleep(0.005)
        return b""

    def write(self, data: bytes) -> int:
        with self._lock:
            self.tx_buf.extend(data)
        return len(data)

    def flush(self) -> None: pass
    def close(self) -> None: self.is_open = False


@pytest.fixture
def bridge(monkeypatch):
    """把 S3Bridge 内部 CdcReader 的 serial 换成 LoopSerial."""
    fs = LoopSerial()
    b = S3Bridge("COM_FAKE")

    def _open() -> None:
        b._reader._ser = fs  # type: ignore
    monkeypatch.setattr(b._reader, "open", _open)
    monkeypatch.setattr(b._reader, "close", lambda: None)
    b.start()
    yield b, fs
    b.stop()


def test_heartbeat_flows_through(bridge):
    b, fs = bridge
    received: list = []
    b._on_heartbeat = received.append

    hb = {"type": "heartbeat", "seq": 7, "csi_score": 88, "fw": "m4-0.4.0"}
    fs.push_rx(_make_frame(TYPE_HEARTBEAT, json.dumps(hb).encode()))

    deadline = time.time() + 2
    while not received and time.time() < deadline:
        time.sleep(0.02)
    assert received, "heartbeat callback not called"
    assert received[0]["csi_score"] == 88
    assert b.stats()["hb"] >= 1


def test_wait_fusion_by_seq(bridge):
    b, fs = bridge
    fu = {"type": "fusion", "seq": 42, "final": 81, "level": "normal",
          "veto_by": [], "reasons": []}
    # 先让 bridge 在后台等
    def _push_later():
        time.sleep(0.1)
        fs.push_rx(_make_frame(TYPE_FUSION, json.dumps(fu).encode()))
    threading.Thread(target=_push_later, daemon=True).start()

    got = b.wait_fusion(seq=42, timeout=1.0)
    assert got is not None
    assert got["final"] == 81
    assert got["level"] == "normal"


def test_wait_fusion_timeout(bridge):
    b, _ = bridge
    got = b.wait_fusion(seq=999, timeout=0.15)
    assert got is None


def test_send_scores_hits_wire(bridge):
    b, fs = bridge
    b.send_scores({"face": 78, "speech": 92, "tongue": 88, "eye": 75, "csi": None,
                   "face_theta": 8.2, "speech_p_clear": 0.91}, seq=7)
    # 等一下, 让 write 落到 tx_buf
    time.sleep(0.05)
    with fs._lock:
        buf = bytes(fs.tx_buf)
    assert buf[:2] == bytes([MAGIC0, MAGIC1])
    assert buf[3] == TYPE_SCORES
    plen = buf[4] | (buf[5] << 8)
    obj = json.loads(buf[6:6 + plen].decode())
    assert obj["type"] == "scores"
    assert obj["seq"] == 7
    assert obj["face"] == 78
    assert obj["csi"] == -1
