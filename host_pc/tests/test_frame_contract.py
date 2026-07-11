"""M1 final frame contract tests.

The ESP32-S3 sends TYPE_DATA (0x02) frames whose JSON payload follows the
project contract:
  {"type":"frame","jpeg_b64":"...","mfcc":[[...]],"csi_score":0-100}
"""
import base64

from stroke_host.io.cdc_reader import TYPE_DATA
from stroke_host.io.frame_contract import parse_frame_payload
from stroke_host.io.sim_source import SyntheticFrameSource
from stroke_host.main import _build_argparser, _make_source


def test_parse_final_frame_payload_accepts_required_fields():
    tiny_jpeg = base64.b64encode(b"\xff\xd8\xff\xd9").decode("ascii")
    payload = {
        "type": "frame",
        "seq": 12,
        "ts": 3,
        "jpeg_b64": tiny_jpeg,
        "mfcc": [[0.0, 1.0, -1.0], [0.5, 0.25, -0.25]],
        "csi_score": 87,
    }

    parsed = parse_frame_payload(payload)

    assert parsed.seq == 12
    assert parsed.ts == 3
    assert parsed.jpeg_b64 == tiny_jpeg
    assert parsed.mfcc_shape == (2, 3)
    assert parsed.csi_score == 87


def test_parse_final_frame_payload_rejects_raw_audio_or_video_keys():
    payload = {
        "type": "frame",
        "jpeg_b64": base64.b64encode(b"\xff\xd8\xff\xd9").decode("ascii"),
        "mfcc": [[0.0]],
        "csi_score": 80,
        "pcm": [0, 1, 2],
    }

    try:
        parse_frame_payload(payload)
    except ValueError as exc:
        assert "raw media key" in str(exc)
    else:
        raise AssertionError("raw media key should be rejected")


def test_synthetic_frame_source_emits_final_frame_contract():
    src = SyntheticFrameSource(hz=100.0, csi_score=76)
    src.open()
    try:
        frame = next(iter(src.frames()))
    finally:
        src.close()

    assert frame.type == TYPE_DATA
    assert frame.type_name == "frame"
    js = frame.json
    assert js["type"] == "frame"
    parsed = parse_frame_payload(js)
    assert parsed.seq == 0
    assert parsed.csi_score == 76
    assert parsed.mfcc_shape[1] == 13


def test_cli_accepts_synthetic_frame_source():
    args = _build_argparser().parse_args(["--source", "synthetic-frame"])

    src = _make_source(args)

    assert isinstance(src, SyntheticFrameSource)
