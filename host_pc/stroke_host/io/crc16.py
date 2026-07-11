"""CRC16-CCITT (FALSE): poly=0x1021, init=0xFFFF, no reflect, no xorout.

Byte-for-byte identical to firmware `main/crc16.c`.
"""
from __future__ import annotations


def crc16_ccitt(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc
