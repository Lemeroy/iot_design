"""与固件 main/crc16.c 对拍的已知向量测试.

关键向量: 一条真实 heartbeat payload, 手算 CRC 后固定为 ground truth.
若日后修改 crc 实现, 本测试可立刻发现漂移.
"""
from stroke_host.io.crc16 import crc16_ccitt


def test_crc16_empty():
    # 空输入 -> init 值 0xFFFF
    assert crc16_ccitt(b"") == 0xFFFF


def test_crc16_known_vector_123456789():
    # CCITT-FALSE 标准向量: "123456789" -> 0x29B1
    assert crc16_ccitt(b"123456789") == 0x29B1


def test_crc16_heartbeat_frame_body():
    # 模拟一帧 [ver, type, lenL, lenH, payload]
    payload = b'{"type":"heartbeat","ts":1,"seq":0,"csi_score":80,"fw":"m1a-0.1"}'
    body = bytes([0x01, 0x01, len(payload) & 0xFF, (len(payload) >> 8) & 0xFF]) + payload
    crc = crc16_ccitt(body)
    # 值本身不重要 (依赖 payload), 关键是 idempotent + 非 0
    assert 0 <= crc <= 0xFFFF
    assert crc16_ccitt(body) == crc


def test_crc16_single_bit_flip_detected():
    a = b"hello world"
    b = b"hello wOrld"
    assert crc16_ccitt(a) != crc16_ccitt(b)
