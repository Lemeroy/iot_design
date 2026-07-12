import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication

from stroke_host.config.profile_loader import parse_profile_yaml
from stroke_host.config.profile_store import save_profile_atomic
from stroke_host.io.device_config_client import DeviceConfigResponse
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


def _device_response(revision=4, age=69):
    return DeviceConfigResponse.model_validate({
        "schema_version": 1,
        "revision": revision,
        "device_id": "sg-test",
        "profile": {
            "age": age,
            "gender": "F",
            "conditions": ["hypertension"],
            "meds": [],
            "stroke_history": True,
        },
        "readonly": {
            "face_danger": 30,
            "mouth_angle_danger_deg": 20,
            "speech_danger": 35,
        },
        "capabilities": ["profile_write"],
    })


def test_device_pull_updates_profile_and_enables_revisioned_push(tmp_path):
    panel = _panel(tmp_path)
    assert panel.device_revision is None
    assert not panel.sync_button.isEnabled()

    panel.apply_device_response(_device_response(revision=4, age=71))

    assert panel.device_revision == 4
    assert panel.age.value() == 71
    assert panel.host.text() == "192.168.1.20"
    assert panel.sync_button.isEnabled()
    parsed = parse_profile_yaml(panel.yaml_editor.toPlainText())
    assert parsed.user.age == 71
    panel.close()


def test_push_signal_contains_profile_and_known_revision(tmp_path):
    panel = _panel(tmp_path)
    emitted = []
    panel.push_requested.connect(lambda profile, revision: emitted.append(
        (profile, revision)
    ))
    panel.apply_device_response(_device_response(revision=7))
    panel.age.setValue(72)
    panel.apply_form_to_yaml()
    panel._emit_push()
    assert emitted[-1][0].user.age == 72
    assert emitted[-1][1] == 7
    panel.close()


def test_conflict_bar_offers_explicit_local_or_device_choice(tmp_path):
    panel = _panel(tmp_path)
    panel.apply_device_response(_device_response(revision=4, age=70))
    panel.age.setValue(75)
    panel.apply_form_to_yaml()
    emitted = []
    panel.push_requested.connect(lambda profile, revision: emitted.append(
        (profile.user.age, revision)
    ))

    panel.show_conflict(_device_response(revision=5, age=73))
    assert panel.conflict_bar.isVisibleTo(panel)
    panel.use_local_button.click()
    assert emitted[-1] == (75, 5)

    panel.show_conflict(_device_response(revision=6, age=74))
    panel.use_device_button.click()
    assert panel.age.value() == 74
    assert panel.device_revision == 6
    panel.close()


def test_token_is_masked_saved_to_keyring_and_never_enters_yaml(
    tmp_path, monkeypatch
):
    panel = _panel(tmp_path)
    saved = []
    monkeypatch.setattr(
        "stroke_host.ui.config_panel.save_manager_token",
        lambda device_id, token: saved.append((device_id, token)),
    )
    panel.token_edit.setText("local-only-token")
    panel.save_token()
    assert panel.token_edit.echoMode() == panel.token_edit.Password
    assert panel.token_edit.text() == ""
    assert saved == [("sg-test", "local-only-token")]
    assert "local-only-token" not in panel.yaml_editor.toPlainText()
    panel.close()


def test_finishing_busy_state_preserves_sync_result_message(tmp_path):
    panel = _panel(tmp_path)
    panel.set_sync_busy(True)
    panel.sync_succeeded("push", _device_response(revision=8))
    panel.set_sync_busy(False)
    assert panel.validation_label.text() == "已同步到设备"
    panel.close()
