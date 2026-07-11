"""CSI 平衡评分 (B 分, 融合权重 0.08).

CSI 打分在 ESP32 端已完成 (firmware_esp32/main/csi_monitor.c),
PC 侧只做:
  1. 从帧 payload 里透传 csi_score (int 0-100 或 None)
  2. 做无值/异常判定, 转为 ModalScore

sim/real 源产的帧 csi_score 分别是模拟随机游走与 None. cdc 真源才是端侧真分.
"""
from __future__ import annotations

from typing import Optional

from . import ModalScore

CSI_WARN = 60
CSI_DANGER = 30


def _quality_for_source(source: str) -> str:
    if source in {"synthetic_frame", "sim_heartbeat"}:
        return "simulated"
    if source == "esp32_csi_monitor":
        return "measured"
    return "unknown"


def _raw_context(source: str, quality: str, **extra) -> dict:
    return {
        "source": source,
        "quality": quality,
        "warn_threshold": CSI_WARN,
        "danger_threshold": CSI_DANGER,
        **extra,
    }


def score_csi(csi_score: Optional[int],
              source: str = "esp32_csi_monitor") -> ModalScore:
    if csi_score is None:
        return ModalScore(
            score=-1,
            reasons=["csi_unavailable"],
            raw=_raw_context(source, "unavailable"),
        )
    quality = _quality_for_source(source)
    try:
        v = int(csi_score)
    except (TypeError, ValueError):
        return ModalScore(
            score=-1,
            reasons=["csi_invalid"],
            raw=_raw_context(source, quality, raw=csi_score),
        )
    if v < 0 or v > 100:
        return ModalScore(
            score=-1,
            reasons=["csi_out_of_range"],
            raw=_raw_context(source, quality, raw=v),
        )

    reasons = []
    if v < CSI_DANGER:
        reasons.append(f"csi {v} < {CSI_DANGER} (warning)")
    elif v < CSI_WARN:
        reasons.append(f"csi {v} < {CSI_WARN} (info)")
    return ModalScore(
        score=v,
        reasons=reasons,
        raw=_raw_context(source, quality, value=v),
    )
