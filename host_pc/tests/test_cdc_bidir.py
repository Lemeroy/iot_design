"""集成层测试: 验证 CdcReader.send_scores 与 CdcReader._read_one_frame 对偶,
帧序列化/反序列化与固件 usb_cdc_proto.c 帧格式一致."""
from __future__ import annotations

import io
import json
import struct
from typing import List

import pytest

from stroke_host.io.cdc_reader import (
    CRC_LEN,
    HDR_LEN,
    MAGIC0,
    MAGIC1,
    MAX_PAYLOAD,
    TYPE_FUSION,
    TYPE_SCORES,
    VER,
    CdcReader,
)
from stroke_host.io.crc16 import crc16_ccitt


class FakeSerial:
    """模拟 pyserial.Serial 的最小子集."""

    def __init__(self) -> None:
        self._rx = bytearray()   # S3 -> PC (供 read)
        self._tx = bytearray()   # PC -> S3 (来自 write)
        self.is_open = True
        self.timeout = 1.0
        self.write_timeout = 1.0

    def push_rx(self, data: bytes) -> None:
        self._rx.extend(data)

    def read(self, n: int) -> bytes:
        if not self._rx:
            return b""
        n = min(n, len(self._rx))
        out = bytes(self._rx[:n])
        del self._rx[:n]
        return out

    def write(self, data: bytes) -> int:
        self._tx.extend(data)
        return len(data)

    def flush(self) -> None:
        pass

    def close(self) -> None:
        self.is_open = False

    @property
    def tx_buffer(self) -> bytes:
        return bytes(self._tx)


def _build_frame(ftype: int, payload: bytes) -> bytes:
    plen = len(payload)
    hdr = bytes([MAGIC0, MAGIC1, VER, ftype, plen & 0xFF, (plen >> 8) & 0xFF])
    crc_input = bytes([VER, ftype, plen & 0xFF, (plen >> 8) & 0xFF]) + payload
    crc = crc16_ccitt(crc_input)
    tail = bytes([crc & 0xFF, (crc >> 8) & 0xFF])
    return hdr + payload + tail


def _make_reader() -> tuple[CdcReader, FakeSerial]:
    r = CdcReader("COM_FAKE")
    fs = FakeSerial()
    r._ser = fs  # type: ignore[attr-defined]
    return r, fs


def test_send_scores_format():
    r, fs = _make_reader()
    r.send_scores({"face": 78, "speech": 92, "tongue": 88, "eye": 75, "csi": None,
                   "face_theta": 8.2, "speech_p_clear": 0.91}, seq=42)
    buf = fs.tx_buffer
    assert buf[0] == MAGIC0 and buf[1] == MAGIC1
    assert buf[2] == VER
    assert buf[3] == TYPE_SCORES
    plen = buf[4] | (buf[5] << 8)
    payload = buf[6:6 + plen]
    obj = json.loads(payload.decode("utf-8"))
    assert obj["type"] == "scores"
    assert obj["seq"] == 42
    assert obj["face"] == 78
    assert obj["csi"] == -1   # None -> -1
    assert obj["face_theta"] == pytest.approx(8.2)
    # crc 校验: 反解自己
    crc_rx = buf[6 + plen] | (buf[6 + plen + 1] << 8)
    crc_calc = crc16_ccitt(bytes([VER, TYPE_SCORES, plen & 0xFF, plen >> 8]) + payload)
    assert crc_rx == crc_calc


def test_read_fusion_frame():
    """让 FakeSerial 回一个 fusion 帧, 验证 reader 能解回来."""
    r, fs = _make_reader()
    js = {"type": "fusion", "seq": 42, "final": 81, "level": "normal",
          "veto_by": [], "reasons": ["ok"],
          "contributions": {"face": 27.3, "speech": 23.0, "tongue": 17.6,
                            "eye": 9.0, "csi": 4.1},
          "used_weights": {"face": 0.35, "speech": 0.25, "tongue": 0.20,
                           "eye": 0.12, "csi": 0.08}}
    fs.push_rx(_build_frame(TYPE_FUSION, json.dumps(js).encode("utf-8")))

    it = r.frames()
    frame = next(it)
    assert frame.type == TYPE_FUSION
    assert frame.type_name == "fusion"
    parsed = frame.json
    assert parsed["final"] == 81
    assert parsed["level"] == "normal"


def test_read_skips_leading_garbage():
    """PC 端能滑动跳过日志字节, 找到 magic 后正确读帧."""
    r, fs = _make_reader()
    garbage = b"I (1234) sg-csi: pkt=12 score=87\n"
    js = {"type": "heartbeat", "seq": 1, "csi_score": 42}
    fs.push_rx(garbage + _build_frame(0x01, json.dumps(js).encode("utf-8")))

    frame = next(r.frames())
    assert frame.type == 0x01
    assert frame.json["csi_score"] == 42


def test_max_payload_1024():
    """确认 MAX_PAYLOAD 已从 512 涨到 1024, 允许 fusion 帧的长 reasons."""
    assert MAX_PAYLOAD == 1024
