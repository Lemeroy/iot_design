"""fusion 单元测试: 权重, 单项否决, 分级."""
import pytest

from stroke_host.fusion import (
    LEVEL_DANGER,
    LEVEL_INSUFFICIENT,
    LEVEL_NORMAL,
    LEVEL_WARNING,
    WEIGHTS,
    fuse,
    normalized,
)


def _m(score, raw=None, reasons=None):
    return {"score": score, "raw": raw or {}, "reasons": reasons or []}


def test_weights_sum_to_1():
    assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9


def test_normalized_partial():
    n = normalized({"face": 0.35, "speech": 0.25})
    assert abs(sum(n.values()) - 1.0) < 1e-9
    assert n["face"] > n["speech"]


def test_all_high_normal_level():
    p = {
        "face":   _m(95, {"theta_abs_deg": 1.0}),
        "speech": _m(90, {"p_clear": 0.9}),
        "tongue": _m(100),
        "eye":    _m(95),
        "csi":    _m(85),
    }
    r = fuse(p)
    assert r.level == LEVEL_NORMAL
    assert r.final >= 88
    assert not r.veto_by


def test_face_veto_by_low_score():
    p = {
        "face":   _m(25, {"theta_abs_deg": 12.0}),
        "speech": _m(85, {"p_clear": 0.85}),
        "tongue": _m(100),
        "eye":    _m(90),
        "csi":    _m(85),
    }
    r = fuse(p)
    assert r.level == LEVEL_DANGER
    assert "face" in r.veto_by


def test_face_veto_by_mouth_angle():
    # F 分本身刚过 warning, 但 mouth_angle 触发单项否决
    p = {
        "face":   _m(35, {"theta_abs_deg": 22.0}),
        "speech": _m(85, {"p_clear": 0.85}),
        "tongue": _m(100),
        "eye":    _m(90),
        "csi":    _m(85),
    }
    r = fuse(p)
    assert r.level == LEVEL_DANGER
    assert "face" in r.veto_by
    assert any("mouth_angle" in x for x in r.reasons)


def test_speech_veto_requires_both_score_and_p():
    # 只有 score 低但 p 未确认 -> 不否决
    p = {
        "face":   _m(95, {"theta_abs_deg": 1.0}),
        "speech": _m(30, {"p_clear": 0.8}),  # 高 p 表示模型自信
        "tongue": _m(100),
        "eye":    _m(95),
        "csi":    _m(85),
    }
    r = fuse(p)
    assert "speech" not in r.veto_by

    p2 = dict(p)
    p2["speech"] = _m(30, {"p_clear": 0.3})
    r2 = fuse(p2)
    assert "speech" in r2.veto_by
    assert r2.level == LEVEL_DANGER


def test_missing_modality_reweighted():
    p = {
        "face":   _m(90, {"theta_abs_deg": 1.0}),
        "speech": _m(-1),  # unavailable
        "tongue": _m(100),
        "eye":    _m(90),
        "csi":    _m(80),
    }
    r = fuse(p)
    # speech 权重被重分, 剩余 4 模态相对权重不变
    assert "speech" not in r.contributions
    assert abs(sum(r.used_weights.values()) - 1.0) < 1e-6


def test_insufficient_when_weight_sum_too_low():
    # 只有 csi (0.08) 和 eye (0.12) 可用 = 0.20 < 0.50
    p = {
        "face":   _m(-1),
        "speech": _m(-1),
        "tongue": _m(-1),
        "eye":    _m(90),
        "csi":    _m(80),
    }
    r = fuse(p)
    assert r.level == LEVEL_INSUFFICIENT


def test_no_modality_available():
    p = {"face": _m(-1), "speech": _m(-1)}
    r = fuse(p)
    assert r.level == LEVEL_INSUFFICIENT
    assert r.final == 0


def test_empty_percept():
    r = fuse({})
    assert r.level == LEVEL_INSUFFICIENT


def test_eye_low_upgrades_normal_to_warning():
    p = {
        "face":   _m(95, {"theta_abs_deg": 1.0}),
        "speech": _m(90, {"p_clear": 0.9}),
        "tongue": _m(100),
        "eye":    _m(15),  # < 30 -> upgrade
        "csi":    _m(85),
    }
    r = fuse(p)
    assert r.level == LEVEL_WARNING


def test_csi_low_upgrades_normal_to_warning():
    p = {
        "face":   _m(95, {"theta_abs_deg": 1.0}),
        "speech": _m(90, {"p_clear": 0.9}),
        "tongue": _m(100),
        "eye":    _m(95),
        "csi":    _m(20),
    }
    r = fuse(p)
    assert r.level == LEVEL_WARNING


def test_final_range():
    for s in (0, 50, 100):
        p = {
            "face":   _m(s, {"theta_abs_deg": 0}),
            "speech": _m(s, {"p_clear": 0.9}),
            "tongue": _m(s),
            "eye":    _m(s),
            "csi":    _m(s),
        }
        r = fuse(p)
        assert r.final == s


def test_weighted_arithmetic():
    # 手算: 0.35*80 + 0.25*90 + 0.20*100 + 0.12*70 + 0.08*60
    # = 28 + 22.5 + 20 + 8.4 + 4.8 = 83.7 -> 84
    p = {
        "face":   _m(80, {"theta_abs_deg": 5.0}),
        "speech": _m(90, {"p_clear": 0.9}),
        "tongue": _m(100),
        "eye":    _m(70),
        "csi":    _m(60),
    }
    r = fuse(p)
    assert r.final == 84
    assert r.level == LEVEL_NORMAL


def test_final_below_40_is_danger_even_without_veto():
    p = {
        "face":   _m(35, {"theta_abs_deg": 5.0}),  # 未触发否决(theta<20)
        "speech": _m(40, {"p_clear": 0.7}),
        "tongue": _m(50),
        "eye":    _m(30),  # 等于阈值边界, 不 upgrade
        "csi":    _m(40),
    }
    r = fuse(p)
    # 0.35*35+0.25*40+0.20*50+0.12*30+0.08*40 = 12.25+10+10+3.6+3.2 = 39.05 -> 39
    assert r.final == 39
    assert r.level == LEVEL_DANGER


def test_result_as_dict_shape():
    p = {"face": _m(80, {"theta_abs_deg": 5.0}), "speech": _m(80, {"p_clear": 0.8})}
    r = fuse(p)
    d = r.as_dict()
    assert set(d.keys()) == {
        "final", "level", "reasons", "veto_by", "contributions", "used_weights"
    }
    assert isinstance(d["contributions"], dict)
