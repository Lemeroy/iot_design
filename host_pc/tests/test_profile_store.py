from pathlib import Path

import pytest

from stroke_host.config.profile_loader import parse_profile_yaml
from stroke_host.config.profile_store import dump_profile_yaml, save_profile_atomic


PROFILE = """
schema_version: 1
device_id: sg-test
device:
  host: 192.168.1.20
  port: 80
user:
  age: 68
  gender: M
  conditions: [hypertension]
  meds: [aspirin]
  stroke_history: false
"""


def test_dump_round_trip_is_versioned_and_unicode_safe():
    profile = parse_profile_yaml(PROFILE.replace("hypertension", "高血压"))
    dumped = dump_profile_yaml(profile)
    reparsed = parse_profile_yaml(dumped)
    assert reparsed == profile
    assert "schema_version: 1" in dumped
    assert "高血压" in dumped


def test_atomic_save_replaces_target(tmp_path):
    target = tmp_path / "profile.yaml"
    target.write_text("old", encoding="utf-8")
    profile = parse_profile_yaml(PROFILE)

    save_profile_atomic(target, profile)

    assert parse_profile_yaml(target.read_text(encoding="utf-8")) == profile
    assert list(tmp_path.glob(".profile.yaml.*")) == []


def test_atomic_save_failure_preserves_old_file(tmp_path, monkeypatch):
    target = tmp_path / "profile.yaml"
    target.write_text("old", encoding="utf-8")
    profile = parse_profile_yaml(PROFILE)

    def fail_replace(source, destination):
        raise OSError("replace failed")

    monkeypatch.setattr("stroke_host.config.profile_store.os.replace", fail_replace)

    with pytest.raises(OSError, match="replace failed"):
        save_profile_atomic(target, profile)

    assert target.read_text(encoding="utf-8") == "old"
    assert list(tmp_path.glob(".profile.yaml.*")) == []


def test_save_creates_parent_directory(tmp_path):
    target = tmp_path / "nested" / "profile.yaml"
    save_profile_atomic(target, parse_profile_yaml(PROFILE))
    assert Path(target).is_file()
