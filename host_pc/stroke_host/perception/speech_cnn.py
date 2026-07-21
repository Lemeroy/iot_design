"""语音清晰度评分 (S 分).

医学依据 (Dr.Chen 会签, v0):
  FAST-S "Speech": 构音障碍/含糊/断续是核心指标.
  家用无参考评价难度大, 采用两层策略:
    (a) 若已训练 CNN 权重存在 -> 用 CNN 推理 p_clear ∈ [0,1]
    (b) 否则 -> 启发式 fallback: 语音活动比 + 谐噪比 + MFCC 稳态

S 分映射 (v0):
  score = 100 * p_clear
  单项否决: score < 35 且 p_clear < 0.4 -> danger

局限 (强调, 已在报告页/UI 显示):
  - 未使用临床构音障碍数据集训练; 家用场景仅做"能听清与否"启发式判定
  - 需背景安静, SNR 建议 > 15 dB
  - M6 前需临床映射; 当前分值仅供内部演示
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Optional

import numpy as np

from . import ModalScore
from .mfcc import compute_mfcc, frame_features

log = logging.getLogger(__name__)


class SpeechScoreStabilizer:
    """平滑有效 S 分，并在短暂无新语音时保留最近一次有效值。"""

    def __init__(self, retention_seconds: float = 300.0,
                 smoothing: float = 0.35) -> None:
        self.retention_seconds = max(0.0, float(retention_seconds))
        self.smoothing = float(np.clip(smoothing, 0.0, 1.0))
        self._score: float | None = None
        self._updated_at: float | None = None

    def update(self, score: int | None, now: float | None = None) -> int | None:
        now = time.monotonic() if now is None else float(now)
        if score is not None and 0 <= int(score) <= 100:
            value = float(int(score))
            if self._score is None:
                self._score = value
            else:
                self._score = self.smoothing * value + (1.0 - self.smoothing) * self._score
            self._updated_at = now
        elif self._updated_at is None or now - self._updated_at > self.retention_seconds:
            self._score = None
        return None if self._score is None else int(round(self._score))


class _CNNStub:
    """占位: 若 M2+ 训好权重再实装 torch/onnxruntime 版本."""

    def __init__(self, weights_path: Path) -> None:
        self.weights_path = weights_path
        self.available = weights_path.exists()

    def predict(self, mfcc: np.ndarray) -> float:
        # 未实装, 抛错让上层走 fallback
        raise NotImplementedError("CNN weights not yet integrated")


def _heuristic_p_clear(samples: np.ndarray, sr: int) -> tuple[float, dict]:
    """无 CNN 时的启发式清晰度估计.

    规则 (Dr.Chen 备注, 待临床映射):
      voiced_ratio  >= 0.35 加分, 太低 (<0.15) 视为"无语音/含糊"
      hnr_db        > -5    加分, 越负越含糊
      MFCC std      MFCC(1..12) 帧间标准差, 反映口型变化
                    过低 -> 单音/呆板; 过高 -> 噪声
    最终 p ∈ [0, 1].
    """
    feats = frame_features(samples, sr)
    mfcc = compute_mfcc(samples, sr)

    # MFCC 帧间稳定度 (排除 c0 能量)
    if mfcc.shape[0] > 4 and mfcc.shape[1] > 1:
        mfcc_std = float(np.mean(np.std(mfcc[:, 1:], axis=0)))
    else:
        mfcc_std = 0.0

    # 各分量归一 [0, 1]
    p_voice = float(np.clip((feats["voiced_ratio"] - 0.15) / 0.35, 0.0, 1.0))
    p_hnr = float(np.clip((feats["hnr_db"] + 15) / 20, 0.0, 1.0))
    # mfcc_std 甜区 ~[2, 10]
    if mfcc_std < 1.0:
        p_var = mfcc_std
    elif mfcc_std > 15.0:
        p_var = max(0.0, 1.0 - (mfcc_std - 15.0) / 10.0)
    else:
        p_var = 1.0

    # 若整段几乎无声, 直接给 unavailable 语义
    if feats["voiced_ratio"] < 0.05 or feats["rms"] < 5e-4:
        return -1.0, {**feats, "mfcc_std": round(mfcc_std, 2),
                      "p_voice": round(p_voice, 2),
                      "p_hnr": round(p_hnr, 2), "p_var": round(p_var, 2)}

    raw_p = 0.5 * p_voice + 0.3 * p_hnr + 0.2 * p_var
    # Valid speech is calibrated above the raw acoustic floor. Silence and
    # failed capture returned earlier and remain unavailable.
    p = 0.20 + 0.80 * raw_p
    return float(np.clip(p, 0.0, 1.0)), {
        **feats,
        "mfcc_std": round(mfcc_std, 2),
        "p_voice": round(p_voice, 2),
        "p_hnr": round(p_hnr, 2),
        "p_var": round(p_var, 2),
    }


def score_speech(samples: np.ndarray, sr: int = 16000,
                 weights_path: Optional[Path] = None) -> ModalScore:
    """输入一段音频 (float32 mono, 建议 1-3 秒), 输出 S 分."""
    if samples is None or samples.size == 0:
        return ModalScore(score=-1, reasons=["no_audio"], raw={})

    # 尝试 CNN
    fallback_reason = None
    if weights_path is not None:
        cnn = _CNNStub(weights_path)
        if cnn.available:
            try:
                mfcc = compute_mfcc(samples, sr)
                p = cnn.predict(mfcc)
                score = int(round(100.0 * p))
                reasons = []
                if score < 35 and p < 0.4:
                    reasons.append(f"speech_score {score} (danger)")
                return ModalScore(score=score, reasons=reasons,
                                  raw={"p_clear": round(float(p), 3),
                                       "backend": "cnn"})
            except NotImplementedError:
                fallback_reason = "cnn_not_integrated"
                log.debug("CNN not implemented, fallback")
        else:
            fallback_reason = "cnn_weights_missing"

    # Fallback: 启发式
    p, raw = _heuristic_p_clear(samples, sr)
    p, raw = _heuristic_p_clear(samples, sr)
    if fallback_reason:
        raw["fallback_reason"] = fallback_reason
        raw["cnn_weights"] = str(weights_path)
    if p < 0:
        return ModalScore(score=-1, reasons=["silence_or_too_quiet"], raw=raw)

    score = int(round(100.0 * p))
    reasons = []
    if score < 35 and p < 0.4:
        reasons.append(f"speech_score {score} (danger, heuristic)")
    elif score < 55:
        reasons.append(f"speech_score {score} (warning, heuristic)")
    raw["backend"] = "heuristic"
    raw["p_clear"] = round(p, 3)
    return ModalScore(score=score, reasons=reasons, raw=raw)
