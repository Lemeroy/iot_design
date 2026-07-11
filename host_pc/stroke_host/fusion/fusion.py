"""五模态融合 + 单项否决.

融合公式 (Ark 冻结, Dr.Chen 会签):
    final = 0.35 * F + 0.25 * S + 0.20 * T + 0.12 * E + 0.08 * B

单项否决 (医疗筛查"宁误报不漏报"):
    - F <= 30  或 raw.mouth_angle >= 20°  -> danger
    - S <= 35  且 raw.p_clear < 0.4        -> danger
    - E < 30                                -> warning
    - B < 30                                -> warning
    T (辅助) 不参与否决, 但纳入加权

不可用模态处理:
    - score < 0 的模态从加权公式移除, 剩余权重按比例归一
    - 若可用模态权重总和 < 0.5, level 强制为 "insufficient"

分级映射 (final 0-100):
    final >= 70          -> normal
    40 <= final < 70     -> warning
    final < 40           -> danger

reasons 汇总:
    - 各模态贡献 (可用/不可用)
    - 触发的单项否决条目
    - 最终 level 依据
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .weights import WEIGHTS, normalized

LEVEL_NORMAL = "normal"
LEVEL_WARNING = "warning"
LEVEL_DANGER = "danger"
LEVEL_INSUFFICIENT = "insufficient"

FINAL_DANGER_MAX = 40
FINAL_WARNING_MAX = 70

# 单项否决阈值 (与 Dr.Chen 会签表一致)
FACE_DANGER_MAX = 30
FACE_MOUTH_DEG_DANGER = 20.0
SPEECH_DANGER_MAX = 35
SPEECH_P_DANGER_MAX = 0.4
EYE_WARNING_MAX = 30
CSI_WARNING_MAX = 30

MIN_AVAIL_WEIGHT_SUM = 0.50


@dataclass
class FusionResult:
    final: int
    level: str
    reasons: List[str] = field(default_factory=list)
    contributions: Dict[str, float] = field(default_factory=dict)  # 模态->加权分
    used_weights: Dict[str, float] = field(default_factory=dict)   # 归一化后
    veto_by: List[str] = field(default_factory=list)               # 触发否决的模态

    def as_dict(self) -> dict:
        return {
            "final": self.final,
            "level": self.level,
            "reasons": self.reasons,
            "veto_by": self.veto_by,
            "contributions": {k: round(v, 2) for k, v in self.contributions.items()},
            "used_weights": {k: round(v, 3) for k, v in self.used_weights.items()},
        }


def _get_score(res: Optional[dict]) -> Optional[int]:
    if not isinstance(res, dict):
        return None
    s = res.get("score")
    if s is None:
        return None
    try:
        s = int(s)
    except (TypeError, ValueError):
        return None
    if s < 0 or s > 100:
        return None
    return s


def fuse(percept: dict, weights: Optional[Dict[str, float]] = None) -> FusionResult:
    """输入 PerceptionPipeline.process() 输出, 返回融合结果.

    percept 结构: {'face': {'score':.., 'raw':.., 'reasons':..}, ...}
    可能有若干 key 缺失或 score=-1 (不可用).
    """
    w = dict(weights or WEIGHTS)

    # 1. 挑出可用模态
    scores = {}
    for k in w:
        m = percept.get(k) if percept else None
        s = _get_score(m)
        if s is not None:
            scores[k] = s

    reasons: List[str] = []
    contributions: Dict[str, float] = {}
    veto_by: List[str] = []

    if not scores:
        return FusionResult(
            final=0, level=LEVEL_INSUFFICIENT,
            reasons=["no modality available"],
        )

    avail_w = {k: w[k] for k in scores}
    if sum(avail_w.values()) < MIN_AVAIL_WEIGHT_SUM:
        return FusionResult(
            final=0, level=LEVEL_INSUFFICIENT,
            reasons=[f"available weight sum {sum(avail_w.values()):.2f} < {MIN_AVAIL_WEIGHT_SUM}"],
            used_weights=avail_w,
        )

    # 2. 归一化后加权
    used = normalized(avail_w)
    final_f = 0.0
    for k, s in scores.items():
        contributions[k] = used[k] * s
        final_f += contributions[k]
    final = int(round(max(0.0, min(100.0, final_f))))

    # 3. 单项否决检查
    # F
    f_res = percept.get("face") or {}
    f_score = scores.get("face")
    if f_score is not None:
        f_raw = f_res.get("raw") or {}
        theta = f_raw.get("theta_abs_deg", 0)
        if f_score <= FACE_DANGER_MAX:
            veto_by.append("face")
            reasons.append(f"veto: F={f_score} <= {FACE_DANGER_MAX}")
        elif theta >= FACE_MOUTH_DEG_DANGER:
            veto_by.append("face")
            reasons.append(f"veto: mouth_angle={theta}deg >= {FACE_MOUTH_DEG_DANGER}deg")

    # S
    s_res = percept.get("speech") or {}
    s_score = scores.get("speech")
    if s_score is not None and s_score <= SPEECH_DANGER_MAX:
        p_clear = (s_res.get("raw") or {}).get("p_clear", 1.0)
        if p_clear < SPEECH_P_DANGER_MAX:
            veto_by.append("speech")
            reasons.append(
                f"veto: S={s_score} <= {SPEECH_DANGER_MAX} & p_clear={p_clear} < {SPEECH_P_DANGER_MAX}"
            )

    # 4. 分级
    if veto_by:
        level = LEVEL_DANGER
        reasons.append(f"level=danger by veto({','.join(veto_by)})")
    elif final < FINAL_DANGER_MAX:
        level = LEVEL_DANGER
        reasons.append(f"level=danger by final={final} < {FINAL_DANGER_MAX}")
    elif final < FINAL_WARNING_MAX:
        level = LEVEL_WARNING
        reasons.append(f"level=warning by {FINAL_DANGER_MAX} <= final={final} < {FINAL_WARNING_MAX}")
    else:
        level = LEVEL_NORMAL

    # 单项 warning (E/B) 提升总 level 至少为 warning
    e_score = scores.get("eye")
    if e_score is not None and e_score < EYE_WARNING_MAX and level == LEVEL_NORMAL:
        level = LEVEL_WARNING
        reasons.append(f"upgrade to warning: E={e_score} < {EYE_WARNING_MAX}")
    b_score = scores.get("csi")
    if b_score is not None and b_score < CSI_WARNING_MAX and level == LEVEL_NORMAL:
        level = LEVEL_WARNING
        reasons.append(f"upgrade to warning: B={b_score} < {CSI_WARNING_MAX}")

    return FusionResult(
        final=final, level=level, reasons=reasons,
        contributions=contributions, used_weights=used, veto_by=veto_by,
    )
