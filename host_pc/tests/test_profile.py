"""Strict local profile YAML loading and migration tests."""
import textwrap

import pytest

from stroke_host.config.profile_loader import load_profile, parse_profile_yaml


def _write(tmp_path, content: str):
    path = tmp_path / "profile.yaml"
    path.write_text(textwrap.dedent(content), encoding="utf-8")
    return path


def test_load_legacy_profile_migrates_to_v1(tmp_path):
    path = _write(tmp_path, """
        device_id: "sg-test"
        user:
          age: 68
          gender: "M"
          conditions: ["hypertension"]
          meds: ["aspirin"]
          stroke_history: false
    """)
    profile = load_profile(path)
    assert profile.schema_version == 1
    assert profile.device.host == ""
    assert profile.device_id == "sg-test"
    assert profile.user.age == 68
    assert profile.user.gender == "M"
    assert profile.user.conditions == ["hypertension"]
    assert profile.thresholds.face_danger == 30


def test_release_thresholds_are_accepted(tmp_path):
    path = _write(tmp_path, """
        device_id: "sg-test"
        user:
          age: 70
          gender: "F"
        thresholds:
          face_danger: 30
          mouth_angle_danger_deg: 20
          speech_danger: 35
    """)
    profile = load_profile(path)
    assert profile.thresholds.face_danger == 30


def test_changed_medical_threshold_is_rejected():
    with pytest.raises(ValueError, match="read-only"):
        parse_profile_yaml("""
schema_version: 1
device_id: sg-test
user: {age: 68, gender: M}
thresholds:
  face_danger: 10
  mouth_angle_danger_deg: 20
  speech_danger: 35
""")


def test_unknown_field_is_rejected():
    with pytest.raises(ValueError):
        parse_profile_yaml("""
schema_version: 1
device_id: sg-test
unknown: true
user: {age: 68, gender: M}
""")


@pytest.mark.parametrize("host", ["8.8.8.8", "example.com"])
def test_public_management_host_is_rejected(host):
    with pytest.raises(ValueError, match="private"):
        parse_profile_yaml(f"""
schema_version: 1
device_id: sg-test
device: {{host: {host}, port: 80}}
user: {{age: 68, gender: M}}
""")


@pytest.mark.parametrize("host", ["192.168.1.20", "10.0.0.2", "mirror.local"])
def test_private_or_local_management_host_is_accepted(host):
    profile = parse_profile_yaml(f"""
schema_version: 1
device_id: sg-test
device: {{host: {host}, port: 8080}}
user: {{age: 68, gender: M}}
""")
    assert profile.device.host == host


def test_profile_item_bounds_are_enforced():
    with pytest.raises(ValueError):
        parse_profile_yaml("""
schema_version: 1
device_id: sg-test
user:
  age: 68
  gender: M
  conditions: [a, b, c, d, e]
""")
    with pytest.raises(ValueError):
        parse_profile_yaml(f"""
schema_version: 1
device_id: sg-test
user:
  age: 68
  gender: M
  meds: [{"x" * 32}]
""")


def test_profile_yaml_size_is_bounded():
    with pytest.raises(ValueError, match="64 KiB"):
        parse_profile_yaml("#" * (64 * 1024 + 1))


def test_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_profile(tmp_path / "missing.yaml")


def test_invalid_gender(tmp_path):
    path = _write(tmp_path, """
        device_id: "sg-test"
        user:
          age: 68
          gender: "X"
    """)
    with pytest.raises(ValueError):
        load_profile(path)


def test_age_out_of_range(tmp_path):
    path = _write(tmp_path, """
        device_id: "sg-test"
        user:
          age: 999
          gender: "M"
    """)
    with pytest.raises(ValueError):
        load_profile(path)
