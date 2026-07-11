"""Final M1 frame payload contract.

USB frame type 0x02 carries this JSON shape:
  {"type":"frame","jpeg_b64":"...","mfcc":[[...]],"csi_score":0-100}

This validator is intentionally strict about raw media keys. Raw audio/video
must stay local and must never be confused with the cloud uplink payload.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Any


RAW_MEDIA_KEYS = {"pcm", "audio", "audio_pcm", "video", "image", "frame_bytes"}


@dataclass(frozen=True)
class FramePayload:
    seq: int
    ts: int
    jpeg_b64: str
    mfcc: list[list[float]]
    csi_score: int

    @property
    def mfcc_shape(self) -> tuple[int, int]:
        if not self.mfcc:
            return (0, 0)
        return (len(self.mfcc), len(self.mfcc[0]))


def _as_int(value: Any, name: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be int") from exc


def _parse_mfcc(value: Any) -> list[list[float]]:
    if not isinstance(value, list) or not value:
        raise ValueError("mfcc must be a non-empty 2D list")
    rows: list[list[float]] = []
    width: int | None = None
    for row in value:
        if not isinstance(row, list) or not row:
            raise ValueError("mfcc rows must be non-empty lists")
        parsed = [float(v) for v in row]
        if width is None:
            width = len(parsed)
        elif len(parsed) != width:
            raise ValueError("mfcc rows must have equal length")
        rows.append(parsed)
    return rows


def parse_frame_payload(obj: dict[str, Any]) -> FramePayload:
    """Validate and normalize a final M1 frame payload."""
    if not isinstance(obj, dict):
        raise ValueError("payload must be dict")
    raw_keys = RAW_MEDIA_KEYS.intersection(obj)
    if raw_keys:
        raise ValueError(f"raw media key not allowed: {sorted(raw_keys)[0]}")
    if obj.get("type") != "frame":
        raise ValueError('type must be "frame"')

    jpeg_b64 = obj.get("jpeg_b64")
    if not isinstance(jpeg_b64, str) or not jpeg_b64:
        raise ValueError("jpeg_b64 must be non-empty string")
    try:
        base64.b64decode(jpeg_b64, validate=True)
    except Exception as exc:
        raise ValueError("jpeg_b64 must be valid base64") from exc

    mfcc = _parse_mfcc(obj.get("mfcc"))
    csi = _as_int(obj.get("csi_score"), "csi_score")
    if csi < 0 or csi > 100:
        raise ValueError("csi_score must be 0..100")

    return FramePayload(
        seq=_as_int(obj.get("seq", 0), "seq"),
        ts=_as_int(obj.get("ts", 0), "ts"),
        jpeg_b64=jpeg_b64,
        mfcc=mfcc,
        csi_score=csi,
    )
