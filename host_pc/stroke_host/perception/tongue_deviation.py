"""舌偏检测 (Tongue, 辅助模态, 融合权重 0.20).

医学依据 (Dr.Chen 会签, v0):
  中医望诊: 中风患者可见"舌偏歪一侧". 现代医学中舌偏也见于舌下神经受损.
  但家用镜头难以稳定分割舌体, 本模块采用 **两层策略**:
    (a) 若舌尖可分割 (张嘴大, 舌头可见) -> 计算舌尖 x 相对面部中线的偏移比 r
    (b) 否则 -> 退化为下唇内侧中点相对面部对称轴偏移 (低置信度)

评分 (Dr.Chen 阈值):
  r < 0.05  -> 100
  r < 0.10  -> 70
  r < 0.15  -> 50
  r >= 0.15 -> 30
  不做单项否决, 仅参考.

局限 (强调):
  - mediapipe 无舌头点位; (a) 需外接舌头分割模型, 目前未实装
  - 本 M3 版本默认走 (b), 属"下唇偏移"近似, 灵敏度低
  - 建议 M6 前接入 SAM/YOLOv8-seg 舌体分割模型
"""
from __future__ import annotations

from typing import Optional

import numpy as np

from . import ModalScore
from .face_detect import FaceLandmarks


TONGUE_R_100 = 0.05
TONGUE_R_70 = 0.10
TONGUE_R_50 = 0.15


def _score_from_r(r: float) -> int:
    r = abs(r)
    if r < TONGUE_R_100:
        return 100
    if r < TONGUE_R_70:
        # 线性 100 -> 70
        t = (r - TONGUE_R_100) / (TONGUE_R_70 - TONGUE_R_100)
        return int(round(100 - 30 * t))
    if r < TONGUE_R_50:
        t = (r - TONGUE_R_70) / (TONGUE_R_50 - TONGUE_R_70)
        return int(round(70 - 20 * t))
    return 30


def score_tongue_deviation(fl: Optional[FaceLandmarks]) -> ModalScore:
    if fl is None:
        return ModalScore(score=-1, reasons=["no_face"], raw={})

    # 面部对称轴: 鼻梁 (168) -> 下巴 (152) 连线在 x 方向的中值
    nose = fl.pt("nose_bridge")
    chin = fl.pt("chin")
    axis_x = 0.5 * (nose[0] + chin[0])

    # 下唇内侧近似点
    lip_ib = fl.pt("lip_inner_bot")
    tongue_x = lip_ib[0]

    # 面宽归一
    cheek_l = fl.pt("cheek_left")
    cheek_r = fl.pt("cheek_right")
    face_w = float(np.linalg.norm(cheek_r - cheek_l)) + 1e-6

    r = (tongue_x - axis_x) / face_w
    r_abs = abs(r)
    score = _score_from_r(r_abs)

    reasons = []
    if r_abs >= TONGUE_R_50:
        reasons.append(
            f"tongue_offset {r_abs*100:.1f}% (aux, low confidence)"
        )
    elif r_abs >= TONGUE_R_70:
        reasons.append(f"tongue_offset {r_abs*100:.1f}% (aux)")

    return ModalScore(
        score=score,
        reasons=reasons,
        raw={
            "r": round(float(r), 4),
            "backend": "lip_inner_approx",
            "method": "lower_lip_inner_proxy",
            "auxiliary": True,
            "confidence": "low",
            "note": "aux_only_not_veto",
        },
    )
