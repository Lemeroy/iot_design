"""眼动评分 (E 分, 融合权重 0.12).

医学依据 (Dr.Chen 会签, v0):
  BE-FAST 的 "Eyes": 复视 / 眼球运动障碍 / 凝视偏斜 是脑卒中重要预警.
  家用相机可近似检测: **双眼虹膜相对眼裂中心的水平偏移是否共轭** (同向且同幅度).

依赖:
  face_detect.FaceMeshDetector(refine_landmarks=True) -> 478 点含虹膜.
  未启用 iris 时本模块返回 unavailable.

计算 (v0):
  对左右眼分别算 gaze_ratio = (iris_center_x - eye_out_x) / (eye_in_x - eye_out_x)
    - 值 ~ 0.5 表示居中
    - <0.3 视线偏一侧, >0.7 视线偏另一侧
  正常: |gaze_L - gaze_R| < 0.15  → 高分
  失共轭: |gaze_L - gaze_R| >= 0.30 → 低分
  眼裂对称性: 左右眼裂高度比 < 0.6 或 > 1.66 → warning (单眼下垂/闭合)

映射:
  E = 100 - 200 * dg  (dg = |gaze_L - gaze_R|)
  clip 到 [0, 100]
  单侧 warning: E < 30

局限 (强调):
  - 头部大幅偏转导致 iris 二维投影失真, 需正视镜头 ±20°
  - 未检测扫视/追随 (需视频序列, M4+)
  - 光照极差/戴墨镜时 iris 检测失败 -> unavailable
"""
from __future__ import annotations

from typing import Optional

import numpy as np

from . import ModalScore
from .face_detect import FaceLandmarks


DG_WARN = 0.15
DG_DANGER = 0.30
LID_ASYM_LOW = 0.6
LID_ASYM_HIGH = 1.66


def _gaze_ratio(iris_c: np.ndarray, eye_out: np.ndarray,
                eye_in: np.ndarray) -> float:
    """iris 中心相对眼裂 (外眦->内眦) 的水平位置比例."""
    denom = eye_in[0] - eye_out[0]
    if abs(denom) < 1e-6:
        return 0.5
    return float((iris_c[0] - eye_out[0]) / denom)


def score_eye_gaze(fl: Optional[FaceLandmarks]) -> ModalScore:
    if fl is None:
        return ModalScore(score=-1, reasons=["no_face"], raw={})
    if not fl.has_iris():
        return ModalScore(
            score=-1, reasons=["iris_not_enabled"],
            raw={
                "backend": "facemesh_no_iris",
                "screening": "BE-FAST_E",
                "diagnosis": False,
                "hint": "use refine_landmarks=True",
            },
        )

    # 左眼 (人物左眼 = 图像右侧, mediapipe 命名遵循镜像视角)
    # 我们已在 IDX 中用 eye_left_out=33, eye_left_in=133 (mediapipe 左脸)
    el_out = fl.pt("eye_left_out")
    el_in = fl.pt("eye_left_in")
    er_out = fl.pt("eye_right_out")
    er_in = fl.pt("eye_right_in")
    il_c = fl.pt("iris_left_center")
    ir_c = fl.pt("iris_right_center")

    gaze_l = _gaze_ratio(il_c, el_out, el_in)
    gaze_r = _gaze_ratio(ir_c, er_out, er_in)
    dg = abs(gaze_l - gaze_r)

    # 眼裂高度对称性
    el_top = fl.pt("eye_left_top")
    el_bot = fl.pt("eye_left_bot")
    er_top = fl.pt("eye_right_top")
    er_bot = fl.pt("eye_right_bot")
    lid_l = float(np.linalg.norm(el_bot - el_top))
    lid_r = float(np.linalg.norm(er_bot - er_top))
    lid_ratio = lid_l / (lid_r + 1e-6)

    score = int(round(max(0.0, min(100.0, 100.0 - 200.0 * dg))))

    reasons = []
    if dg >= DG_DANGER:
        reasons.append(f"gaze_diff {dg:.2f} >= {DG_DANGER} (warning)")
    elif dg >= DG_WARN:
        reasons.append(f"gaze_diff {dg:.2f} (info)")
    if lid_ratio < LID_ASYM_LOW or lid_ratio > LID_ASYM_HIGH:
        reasons.append(f"lid_asym {lid_ratio:.2f} (unilateral ptosis?)")
        # 眼裂严重不对称直接压低分
        score = min(score, 40)

    return ModalScore(
        score=score,
        reasons=reasons,
        raw={
            "backend": "facemesh_iris",
            "screening": "BE-FAST_E",
            "diagnosis": False,
            "gaze_l": round(gaze_l, 3),
            "gaze_r": round(gaze_r, 3),
            "dg": round(dg, 3),
            "lid_l_px": round(lid_l, 1),
            "lid_r_px": round(lid_r, 1),
            "lid_ratio": round(lid_ratio, 2),
        },
    )
