"""M3 舌偏 (辅助) 测试."""
import numpy as np

from stroke_host.perception.face_detect import IDX, FaceLandmarks
from stroke_host.perception.tongue_deviation import (
    score_tongue_deviation,
    _score_from_r,
)


def _mk(points):
    arr = np.zeros((468, 3), dtype=np.float32)
    for k, (x, y) in points.items():
        arr[IDX[k], 0] = x
        arr[IDX[k], 1] = y
    return FaceLandmarks(arr, 640, 480)


def test_no_face():
    r = score_tongue_deviation(None)
    assert not r.available


def test_centered_tongue_high_score():
    fl = _mk({
        "nose_bridge":   (320, 200),
        "chin":          (320, 400),
        "lip_inner_bot": (322, 355),
        "cheek_left":    (150, 300),
        "cheek_right":   (490, 300),
    })
    r = score_tongue_deviation(fl)
    assert r.score >= 95
    assert r.available


def test_moderate_deviation_lower_score():
    fl = _mk({
        "nose_bridge":   (320, 200),
        "chin":          (320, 400),
        "lip_inner_bot": (350, 355),  # 30 px 偏移, face_w=340, r ~0.088
        "cheek_left":    (150, 300),
        "cheek_right":   (490, 300),
    })
    r = score_tongue_deviation(fl)
    assert 70 <= r.score <= 90


def test_severe_deviation_score30():
    fl = _mk({
        "nose_bridge":   (320, 200),
        "chin":          (320, 400),
        "lip_inner_bot": (400, 355),  # 80 px 偏移, r ~0.235
        "cheek_left":    (150, 300),
        "cheek_right":   (490, 300),
    })
    r = score_tongue_deviation(fl)
    assert r.score == 30
    assert any("aux" in x for x in r.reasons)


def test_score_from_r_monotonic():
    scores = [_score_from_r(x) for x in (0.0, 0.03, 0.05, 0.08, 0.10, 0.12, 0.15, 0.30)]
    for a, b in zip(scores, scores[1:]):
        assert a >= b, scores


def test_tongue_raw_marks_auxiliary_low_confidence():
    fl = _mk({
        "nose_bridge":   (320, 200),
        "chin":          (320, 400),
        "lip_inner_bot": (400, 355),
        "cheek_left":    (150, 300),
        "cheek_right":   (490, 300),
    })

    r = score_tongue_deviation(fl)

    assert r.raw["auxiliary"] is True
    assert r.raw["confidence"] == "low"
    assert r.raw["method"] == "lower_lip_inner_proxy"


def test_tongue_result_is_not_a_zero_score_when_unavailable():
    r = score_tongue_deviation(None)
    assert r.score == -1
    assert "no_face" in r.reasons
