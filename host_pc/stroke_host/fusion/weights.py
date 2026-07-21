"""五模态融合权重 (可覆盖).

sum = 1.00
"""
WEIGHTS = {
    "face":   0.35,   # F
    "speech": 0.35,   # S
    "tongue": 0.08,   # T (辅助)
    "eye":    0.14,   # E
    "csi":    0.08,   # B
}


def normalized(weights: dict) -> dict:
    """归一化 (缺失模态时按剩余权重比例分配)."""
    s = sum(weights.values())
    if s <= 0:
        return {k: 0.0 for k in weights}
    return {k: v / s for k, v in weights.items()}
