"""帧解析器测试: 用 loopback 假串口构造字节流, 验证:
  - 好帧正常出
  - CRC 错帧被丢弃
  - 头前有垃圾字节能自动重新同步
"""
import json

import pytest

from stroke_host.io.cdc_reader import (
    CdcReader,
    HDR_LEN,
    MAGIC0,
    MAGIC1,
    TYPE_HEARTBEAT,
    VER,
)
from stroke_host.io.crc16 import crc16_ccitt


def _build_frame(payload: bytes, ftype: int = TYPE_HEARTBEAT,
                 ver: int = VER, corrupt_crc: bool = False) -> bytes:
    lenL = len(payload) & 0xFF
    lenH = (len(payload) >> 8) & 0xFF
    body = bytes([ver, ftype, lenL, lenH]) + payload
    crc = crc16_ccitt(body)
    if corrupt_crc:
        crc ^= 0x0001
    return bytes([MAGIC0, MAGIC1]) + body + bytes([crc & 0xFF, (crc >> 8) & 0xFF])


class FakeSerial:
    """最小 pyserial 兼容: read(n) 返回 <=n 字节, 无数据时返回空."""

    def __init__(self, data: bytes):
        self._buf = bytearray(data)
        self.is_open = True

    def read(self, n: int) -> bytes:
        take = min(n, len(self._buf))
        out = bytes(self._buf[:take])
        del self._buf[:take]
        return out

    def close(self):
        self.is_open = False


@pytest.fixture
def reader_with(monkeypatch):
    def _mk(stream: bytes) -> CdcReader:
        r = CdcReader("FAKE")
        r._ser = FakeSerial(stream)  # 直接注入
        return r
    return _mk


def test_single_heartbeat_frame(reader_with):
    payload = json.dumps({"type": "heartbeat", "seq": 0, "csi_score": 80}).encode()
    stream = _build_frame(payload)
    r = reader_with(stream)
    frame = r._read_one_frame()
    assert frame is not None
    assert frame.type == TYPE_HEARTBEAT
    assert frame.payload == payload
    assert frame.json["csi_score"] == 80
    assert r.n_ok == 1


def test_crc_error_dropped(reader_with):
    payload = b'{"type":"heartbeat","seq":1}'
    stream = _build_frame(payload, corrupt_crc=True)
    r = reader_with(stream)
    frame = r._read_one_frame()
    assert frame is None
    assert r.n_crc_err == 1


def test_resync_after_garbage(reader_with):
    payload = b'{"type":"heartbeat","seq":2}'
    good = _build_frame(payload)
    stream = b"\x00\xff\xa5\xa5\xde\xad" + good  # 前缀垃圾
    r = reader_with(stream)
    frame = r._read_one_frame()
    assert frame is not None
    assert frame.payload == payload


def test_multiple_frames_back_to_back(reader_with):
    p1 = b'{"seq":1}'
    p2 = b'{"seq":2}'
    p3 = b'{"seq":3}'
    stream = _build_frame(p1) + _build_frame(p2) + _build_frame(p3)
    r = reader_with(stream)
    frames = []
    for _ in range(3):
        f = r._read_one_frame()
        assert f is not None
        frames.append(f.payload)
    assert frames == [p1, p2, p3]
    assert r.n_ok == 3


def test_bad_version_resync(reader_with):
    # 头合法但 ver=0x99 -> 丢弃, 后面接一帧正常
    fake_hdr = bytes([MAGIC0, MAGIC1, 0x99, 0x01, 0x00, 0x00, 0x00, 0x00])
    good = _build_frame(b'{"ok":1}')
    r = reader_with(fake_hdr + good)
    # 第一次尝试: 拿到 bad ver, 返回 None
    assert r._read_one_frame() is None
    # 第二次尝试: 从流后半段找到 good
    f = r._read_one_frame()
    assert f is not None and f.json == {"ok": 1}
