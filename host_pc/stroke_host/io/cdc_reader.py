"""ESP32 -> PC USB-CDC 帧读取器.

帧协议 v1 (与固件 usb_cdc_proto.c 对齐):
  0..1  magic  A5 5A
  2     ver    0x01
  3     type   0x01=heartbeat, 0x02=frame,
               0x03=scores(PC->S3), 0x04=fusion(S3->PC), 0xF0=log
  4..5  len    LE, payload 长度
  6..N  payload UTF-8 JSON
  N..   crc16  LE, CCITT-FALSE, 覆盖 ver..payload

用法:
    reader = CdcReader("COM3")
    reader.open()
    for frame in reader.frames():
        print(frame.type_name, frame.json)
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Iterator, Optional

import serial

from .crc16 import crc16_ccitt

log = logging.getLogger(__name__)

MAGIC0 = 0xA5
MAGIC1 = 0x5A
VER = 0x01
HDR_LEN = 6
CRC_LEN = 2
MAX_PAYLOAD = 1024

TYPE_HEARTBEAT = 0x01
TYPE_DATA = 0x02
TYPE_SCORES = 0x03  # PC -> S3
TYPE_FUSION = 0x04  # S3 -> PC
TYPE_LOG = 0xF0
TYPE_NAMES = {
    TYPE_HEARTBEAT: "heartbeat",
    TYPE_DATA: "frame",
    TYPE_SCORES: "scores",
    TYPE_FUSION: "fusion",
    TYPE_LOG: "log",
}


@dataclass
class Frame:
    type: int
    payload: bytes
    ts_recv: float

    @property
    def type_name(self) -> str:
        return TYPE_NAMES.get(self.type, f"unknown_0x{self.type:02X}")

    @property
    def json(self) -> Optional[dict]:
        try:
            return json.loads(self.payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None


class CdcReader:
    """状态机解析器. 单线程阻塞读, 上层可放入线程/协程."""

    def __init__(self, port: str, baudrate: int = 115200, timeout: float = 1.0):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self._ser: Optional[serial.Serial] = None
        # 统计
        self.n_ok = 0
        self.n_crc_err = 0
        self.n_resync = 0

    def open(self) -> None:
        self._ser = serial.Serial(
            port=self.port, baudrate=self.baudrate,
            timeout=self.timeout, write_timeout=self.timeout,
        )
        log.info("CDC opened: %s @ %d", self.port, self.baudrate)

    def close(self) -> None:
        if self._ser and self._ser.is_open:
            self._ser.close()
        self._ser = None

    def __enter__(self) -> "CdcReader":
        self.open()
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def _read_exact(self, n: int) -> Optional[bytes]:
        """读取正好 n 字节, 超时返回 None."""
        assert self._ser is not None
        buf = bytearray()
        deadline = time.monotonic() + self.timeout * 5
        while len(buf) < n:
            chunk = self._ser.read(n - len(buf))
            if chunk:
                buf.extend(chunk)
            elif time.monotonic() > deadline:
                return None
        return bytes(buf)

    def _sync_magic(self) -> bool:
        """在流中滑动查找 A5 5A. 找到返回 True, 断流返回 False."""
        assert self._ser is not None
        last = 0
        while True:
            b = self._ser.read(1)
            if not b:
                return False
            v = b[0]
            if last == MAGIC0 and v == MAGIC1:
                return True
            last = v

    def _read_one_frame(self) -> Optional[Frame]:
        """读取并校验一帧. 校验失败返回 None (调用方重新同步)."""
        assert self._ser is not None

        # 1. 同步 magic
        if not self._sync_magic():
            return None

        # 2. 读 ver/type/len (4B)
        head = self._read_exact(4)
        if head is None:
            self.n_resync += 1
            return None
        ver, ftype, l0, l1 = head[0], head[1], head[2], head[3]
        if ver != VER:
            self.n_resync += 1
            log.debug("bad ver=0x%02X, resync", ver)
            return None
        plen = l0 | (l1 << 8)
        if plen > MAX_PAYLOAD:
            self.n_resync += 1
            log.debug("bad plen=%d, resync", plen)
            return None

        # 3. 读 payload + crc
        rest = self._read_exact(plen + CRC_LEN)
        if rest is None or len(rest) < plen + CRC_LEN:
            self.n_resync += 1
            return None
        payload = rest[:plen]
        crc_lo, crc_hi = rest[plen], rest[plen + 1]
        crc_rx = crc_lo | (crc_hi << 8)

        # 4. 校验 CRC: ver + type + lenL + lenH + payload
        crc_calc = crc16_ccitt(bytes([ver, ftype, l0, l1]) + payload)
        if crc_calc != crc_rx:
            self.n_crc_err += 1
            log.debug("CRC mismatch: got 0x%04X, want 0x%04X", crc_rx, crc_calc)
            return None

        self.n_ok += 1
        return Frame(type=ftype, payload=payload, ts_recv=time.time())

    def frames(self) -> Iterator[Frame]:
        """无限迭代器, 断流/坏帧自动重试."""
        while True:
            if self._ser is None:
                raise RuntimeError("reader not opened")
            f = self._read_one_frame()
            if f is not None:
                yield f

    def send_frame(self, ftype: int, payload: bytes) -> None:
        """写一帧到 S3. 帧格式: A5 5A ver type lenL lenH payload crcL crcH."""
        if self._ser is None:
            raise RuntimeError("reader not opened")
        if len(payload) > MAX_PAYLOAD:
            raise ValueError(f"payload too long: {len(payload)} > {MAX_PAYLOAD}")
        plen = len(payload)
        header = bytes([
            MAGIC0, MAGIC1, VER, ftype,
            plen & 0xFF, (plen >> 8) & 0xFF,
        ])
        crc_buf = bytes([VER, ftype, plen & 0xFF, (plen >> 8) & 0xFF]) + payload
        crc = crc16_ccitt(crc_buf)
        tail = bytes([crc & 0xFF, (crc >> 8) & 0xFF])
        self._ser.write(header + payload + tail)
        try:
            self._ser.flush()
        except Exception:
            pass

    def send_scores(self, scores: dict, seq: int = 0) -> None:
        """发送 SCORES 帧. scores 字典按契约结构 (face/speech/tongue/eye/csi/...).

        None/-1/缺失字段都会传 -1 或 null 给 S3.
        """
        payload_obj = {"type": "scores", "seq": int(seq)}
        for k in ("face", "speech", "tongue", "eye", "csi"):
            v = scores.get(k)
            if v is None:
                payload_obj[k] = -1
            else:
                try:
                    payload_obj[k] = int(v)
                except (TypeError, ValueError):
                    payload_obj[k] = -1
        # 可选浮点字段
        theta = scores.get("face_theta")
        if theta is not None:
            try:
                payload_obj["face_theta"] = float(theta)
            except (TypeError, ValueError):
                pass
        p_clear = scores.get("speech_p_clear")
        if p_clear is not None:
            try:
                payload_obj["speech_p_clear"] = float(p_clear)
            except (TypeError, ValueError):
                pass
        raw = json.dumps(payload_obj, ensure_ascii=False, separators=(",", ":"))
        self.send_frame(TYPE_SCORES, raw.encode("utf-8"))
