"""Face symmetry 评分测试, 不依赖 mediapipe.

构造合成 468 点数组, 只填我们用到的 6-8 个关键点, 其余置 0.
"""
import numpy as np

from stroke_host.perception.face_detect import IDX, FaceLandmarks
from stroke_host.perception.face_symmetry import score_face_symmetry


def _mk_landmarks(points: dict[str, tuple[float, float]],
                  w: int = 640, h: int = 480) -> FaceLandmarks:
    arr = np.zeros((468, 3), dtype=np.float32)
    for name, (x, y) in points.items():
        arr[IDX[name], 0] = x
        arr[IDX[name], 1] = y
    return FaceLandmarks(landmarks=arr, image_w=w, image_h=h)


def test_perfectly_symmetric_face_scores_100():
    # 双眼水平, 嘴角水平, 唇中点 = 双颊中点
    fl = _mk_landmarks({
        "eye_left_out":  (200, 200),
        "eye_right_out": (440, 200),
        "eye_left_in":   (280, 200),
        "eye_right_in":  (360, 200),
        "mouth_left":    (260, 350),
        "mouth_right":   (380, 350),
        "lip_top":       (320, 340),
        "lip_bottom":    (320, 360),
        "cheek_left":    (150, 300),
        "cheek_right":   (490, 300),
        "nose_tip":      (320, 280),
    })
    r = score_face_symmetry(fl)
    assert r.available
    assert r.score >= 95
    assert r.raw["theta_abs_deg"] < 2.0
    assert not any("danger" in x for x in r.reasons)


def test_no_face_returns_unavailable():
    r = score_face_symmetry(None)
    assert not r.available
    assert "no_face" in r.reasons


def test_mouth_tilt_20deg_triggers_danger():
    # 嘴角连线 tan(20°) ~ 0.364
    import math
    dy = 120 * math.tan(math.radians(20))  # 双嘴角 x 距 120
    fl = _mk_landmarks({
        "eye_left_out":  (200, 200),
        "eye_right_out": (440, 200),
        "eye_left_in":   (280, 200),
        "eye_right_in":  (360, 200),
        "mouth_left":    (260, 350),
        "mouth_right":   (380, 350 + dy),  # 右嘴角下垂
        "lip_top":       (320, 340),
        "lip_bottom":    (320, 360),
        "cheek_left":    (150, 300),
        "cheek_right":   (490, 300),
    })
    r = score_face_symmetry(fl)
    assert r.available
    # 20 deg -> F = 100 - 4*20 = 20
    assert r.score <= 25
    assert any("danger" in x for x in r.reasons)


def test_moderate_tilt_10deg_warning_not_danger():
    import math
    dy = 120 * math.tan(math.radians(10))
    fl = _mk_landmarks({
        "eye_left_out":  (200, 200),
        "eye_right_out": (440, 200),
        "eye_left_in":   (280, 200),
        "eye_right_in":  (360, 200),
        "mouth_left":    (260, 350),
        "mouth_right":   (380, 350 + dy),
        "lip_top":       (320, 340),
        "lip_bottom":    (320, 360),
        "cheek_left":    (150, 300),
        "cheek_right":   (490, 300),
    })
    r = score_face_symmetry(fl)
    # F ~ 60
    assert 55 <= r.score <= 65
    assert not any("danger" in x for x in r.reasons)
    assert any("warning" in x for x in r.reasons)


def test_head_roll_compensated():
    # 整脸旋转 15° (头歪), 嘴角相对眼睛仍平行 -> 应仍是高分
    import math
    ang = math.radians(15)
    cs, sn = math.cos(ang), math.sin(ang)

    def rot(p):
        x, y = p[0] - 320, p[1] - 240
        return (cs * x - sn * y + 320, sn * x + cs * y + 240)

    fl = _mk_landmarks({
        "eye_left_out":  rot((200, 200)),
        "eye_right_out": rot((440, 200)),
        "eye_left_in":   rot((280, 200)),
        "eye_right_in":  rot((360, 200)),
        "mouth_left":    rot((260, 350)),
        "mouth_right":   rot((380, 350)),
        "lip_top":       rot((320, 340)),
        "lip_bottom":    rot((320, 360)),
        "cheek_left":    rot((150, 300)),
        "cheek_right":   rot((490, 300)),
    })
    r = score_face_symmetry(fl)
    # 头部整体旋转不该被判为口角下垂
    assert r.score >= 90, f"expected high score, got {r.score}, raw={r.raw}"
