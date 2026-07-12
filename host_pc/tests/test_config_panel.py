import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication

from stroke_host.config.profile_loader import parse_profile_yaml
from stroke_host.config.profile_store import save_profile_atomic
from stroke_host.ui.config_panel import ConfigPanel


_QT_APP = None

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


def _app():
    global _QT_APP
    app = QApplication.instance()
    _QT_APP = app or QApplication([])
    return _QT_APP


def _panel(tmp_path):
    _app()
    path = tmp_path / "profile.yaml"
    save_profile_atomic(path, parse_profile_yaml(PROFILE))
    return ConfigPanel(path)


def test_panel_loads_profile_and_round_trips_form_to_yaml(tmp_path):
    panel = _panel(tmp_path)
    assert panel.device_id.text() == "sg-test"
    assert panel.age.value() == 68

    panel.age.setValue(72)
    panel.gender.setCurrentText("F")
    panel.conditions.setText("hypertension, diabetes")
    panel.apply_form_to_yaml()

    parsed = parse_profile_yaml(panel.yaml_editor.toPlainText())
    assert parsed.user.age == 72
    assert parsed.user.gender == "F"
    assert parsed.user.conditions == ["hypertension", "diabetes"]
    panel.close()


def test_yaml_changes_can_populate_form(tmp_path):
    panel = _panel(tmp_path)
    panel.yaml_editor.setPlainText(PROFILE.replace("age: 68", "age: 77"))
    assert panel.apply_yaml_to_form()
    assert panel.age.value() == 77
    panel.close()


def test_invalid_yaml_disables_save_and_sync(tmp_path):
    panel = _panel(tmp_path)
    panel.yaml_editor.setPlainText("user: [")
    assert not panel.validate_yaml()
    assert not panel.save_button.isEnabled()
    assert not panel.sync_button.isEnabled()
    assert panel.validation_label.text()
    panel.close()


def test_save_writes_validated_yaml_atomically(tmp_path):
    panel = _panel(tmp_path)
    panel.age.setValue(74)
    panel.apply_form_to_yaml()
    panel.save_local()
    assert parse_profile_yaml((tmp_path / "profile.yaml").read_text(
        encoding="utf-8"
    )).user.age == 74
    panel.close()


def test_invalid_file_opens_in_invalid_editor_state(tmp_path):
    _app()
    path = tmp_path / "profile.yaml"
    path.write_text("user: [", encoding="utf-8")
    panel = ConfigPanel(path)
    assert panel.yaml_editor.toPlainText() == "user: ["
    assert not panel.save_button.isEnabled()
    panel.close()


def test_save_failure_is_reported_without_raising(tmp_path, monkeypatch):
    panel = _panel(tmp_path)

    def fail_save(*args):
        raise OSError("disk detail")

    monkeypatch.setattr("stroke_host.ui.config_panel.save_profile_atomic", fail_save)
    panel.save_local()
    assert "保存失败" in panel.validation_label.text()
    assert "disk detail" not in panel.validation_label.text()
    panel.close()


def test_medical_threshold_controls_are_read_only_labels(tmp_path):
    panel = _panel(tmp_path)
    assert panel.face_threshold.text() == "30"
    assert not hasattr(panel.face_threshold, "setValue")
    panel.close()


def test_yaml_editor_has_high_contrast_palette(tmp_path):
    panel = _panel(tmp_path)
    style = panel.yaml_editor.styleSheet().lower()
    assert "color:" in style
    assert "selection-color:" in style
    assert "selection-background-color:" in style
    panel.close()
