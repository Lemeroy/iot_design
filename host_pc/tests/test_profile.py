"""profile.yaml 加载 & 校验测试."""
import textwrap

import pytest

from stroke_host.config.profile_loader import load_profile


def _write(tmp_path, content: str):
    p = tmp_path / "profile.yaml"
    p.write_text(textwrap.dedent(content), encoding="utf-8")
    return p


def test_load_ok(tmp_path):
    p = _write(tmp_path, """
        device_id: "sg-test"
        user:
          age: 68
          gender: "M"
          conditions: ["hypertension"]
          meds: ["aspirin"]
          stroke_history: false
    """)
    pf = load_profile(p)
    assert pf.device_id == "sg-test"
    assert pf.user.age == 68
    assert pf.user.gender == "M"
    assert pf.user.conditions == ["hypertension"]
    assert pf.thresholds is None  # 缺省时可空


def test_load_with_thresholds(tmp_path):
    p = _write(tmp_path, """
        device_id: "sg-test"
        user:
          age: 70
          gender: "F"
        thresholds:
          face_danger: 25
          mouth_angle_danger_deg: 18
          speech_danger: 30
    """)
    pf = load_profile(p)
    assert pf.thresholds.face_danger == 25


def test_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_profile(tmp_path / "missing.yaml")


def test_invalid_gender(tmp_path):
    p = _write(tmp_path, """
        device_id: "sg-test"
        user:
          age: 68
          gender: "X"
    """)
    with pytest.raises(ValueError):
        load_profile(p)


def test_age_out_of_range(tmp_path):
    p = _write(tmp_path, """
        device_id: "sg-test"
        user:
          age: 999
          gender: "M"
    """)
    with pytest.raises(ValueError):
        load_profile(p)
