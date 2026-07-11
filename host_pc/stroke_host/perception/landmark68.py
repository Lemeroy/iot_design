"""FaceMesh 468 -> 经典 68 点适配 (占位, M3+ 若需要 dlib 兼容再用).

M2 主链路直接吃 468 点; 本文件提供索引映射供后续复用.
"""
from __future__ import annotations

import numpy as np

# 68 点 (iBUG multi-PIE 顺序) 到 FaceMesh 468 点的近似映射
# 索引来自社区约定 (mediapipe 官方未提供官方 68 点子集)
# 用途: 若下游脚本需要 dlib 兼容格式, 用此表提取 68 点
FACEMESH_68 = [
    # 下颌线 17 点 (0-16)
    127, 234, 93, 132, 58, 172, 136, 150, 176, 148, 152, 377, 400, 378, 365, 397, 356,
    # 右眉 (17-21)
    70, 63, 105, 66, 107,
    # 左眉 (22-26)
    336, 296, 334, 293, 300,
    # 鼻梁 (27-30)
    168, 6, 197, 195,
    # 鼻底 (31-35)
    5, 4, 1, 19, 94,
    # 右眼 (36-41)
    33, 160, 158, 133, 153, 144,
    # 左眼 (42-47)
    362, 385, 387, 263, 373, 380,
    # 外唇 (48-59)
    61, 39, 37, 0, 267, 269, 291, 405, 314, 17, 84, 181,
    # 内唇 (60-67)
    78, 82, 13, 312, 308, 317, 14, 87,
]


def mesh468_to_68(landmarks_468: np.ndarray) -> np.ndarray:
    """输入 (468,3) 输出 (68,3), 供 dlib 兼容管线使用."""
    if landmarks_468.shape[0] < 468:
        raise ValueError(f"expect 468 landmarks, got {landmarks_468.shape[0]}")
    if len(FACEMESH_68) != 68:
        raise RuntimeError("FACEMESH_68 mapping length != 68")
    return landmarks_468[FACEMESH_68]
