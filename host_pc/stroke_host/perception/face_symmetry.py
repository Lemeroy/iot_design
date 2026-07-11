"""面部对称评分 (F 分).

医学依据 (Dr.Chen 会签, v0):
  FAST-F "Face": 单侧口角下垂/静态歪斜是核心指标.
  工程近似: 双嘴角连线与水平线夹角 θ 越大越异常.

计算:
  1. 输入 468 点 landmarks (mediapipe)
  2. 用双眼外眦连线定义 "水平面参考", 排除头部平面内旋转
  3. 计算嘴角连线在参考面内的夹角 θ (deg)
  4. 辅助: 上下唇中点与双颊中线偏移量 dx_ratio
  5. F = clip(100 - 4.0 * θ, 0, 100)
     - θ=0    → 100
     - θ=5    → 80
     - θ=10   → 60
     - θ=15   → 40
     - θ=20   → 20  (触发 danger, 单项否决)
  6. reasons: θ 与 dx 阈值超出时给出人类可读原因

局限 (明示):
  - mediapipe 二维投影, 头部大角度侧转会误报
  - θ 只反映静态歪斜, 动态"露齿测试"需 M3+ 视频序列
"""
from __future__ import annotations

import math
from typing import Optional

import numpy as np

from . import ModalScore
from .face_detect import FaceLandmarks

# Dr.Chen 阈值表
K_THETA = 4.0            # F = 100 - K * θ
THETA_DANGER_DEG = 20.0  # 单项否决阈值 (与 profile.thresholds.mouth_angle_danger_deg 一致)
DX_WARN_RATIO = 0.05     # 唇中点相对面宽偏移 >5% 视为异常


def _angle_deg(v: np.ndarray) -> float:
    """向量 (dx, dy) 与 x 轴夹角 (deg), 范围 [-90, 90]."""
    if np.linalg.norm(v) < 1e-6:
        return 0.0
    ang = math.degrees(math.atan2(v[1], v[0]))
    # 归到 (-90, 90]: 处理左右嘴角谁在前
    if ang > 90:
        ang -= 180
    elif ang < -90:
        ang += 180
    return ang


def score_face_symmetry(fl: Optional[FaceLandmarks]) -> ModalScore:
    if fl is None:
        return ModalScore(score=-1, reasons=["no_face"], raw={})

    ml = fl.pt("mouth_left")
    mr = fl.pt("mouth_right")
    el = fl.pt("eye_left_out")
    er = fl.pt("eye_right_out")
    lip_top = fl.pt("lip_top")
    lip_bot = fl.pt("lip_bottom")
    cheek_l = fl.pt("cheek_left")
    cheek_r = fl.pt("cheek_right")

    # 参考坐标系: 双眼外眦连线为 x 轴 → 消除面内旋转
    eye_vec = er - el
    face_yaw_rot = _angle_deg(eye_vec)   # 面内旋转角
    # 把嘴角向量投影到旋转补偿后的坐标系
    mouth_vec = mr - ml
    theta_raw = _angle_deg(mouth_vec)
    theta = theta_raw - face_yaw_rot
    theta_abs = abs(theta)

    # 唇中点相对双颊中线水平偏移
    lip_mid_x = 0.5 * (lip_top[0] + lip_bot[0])
    cheek_mid_x = 0.5 * (cheek_l[0] + cheek_r[0])
    face_w = float(np.linalg.norm(cheek_r - cheek_l)) + 1e-6
    dx_ratio = (lip_mid_x - cheek_mid_x) / face_w

    # 主打分
    s = 100.0 - K_THETA * theta_abs
    s = max(0.0, min(100.0, s))

    reasons = []
    # 用 -1e-3 容差, 消除 float32 精度导致的边界抖动
    if theta_abs >= THETA_DANGER_DEG - 1e-3:
        reasons.append(f"mouth_angle {theta_abs:.1f}deg >= {THETA_DANGER_DEG:.0f}deg (danger)")
    elif theta_abs > 10.0:
        reasons.append(f"mouth_angle {theta_abs:.1f}deg (warning)")
    if abs(dx_ratio) > DX_WARN_RATIO:
        reasons.append(f"lip_offset {dx_ratio*100:.1f}% (warning)")

    return ModalScore(
        score=int(round(s)),
        reasons=reasons,
        raw={
            "theta_deg": round(theta, 2),
            "theta_abs_deg": round(theta_abs, 2),
            "face_yaw_rot_deg": round(face_yaw_rot, 2),
            "dx_ratio": round(float(dx_ratio), 4),
            "face_w_px": round(face_w, 1),
        },
    )
