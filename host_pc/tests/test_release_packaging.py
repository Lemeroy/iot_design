from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_demo_entry_uses_package_import_and_main_guard():
    source = (ROOT / "host_pc" / "stroke_host" / "demo_entry.py").read_text(
        encoding="utf-8"
    )
    assert "from stroke_host.demo.window import main" in source
    assert "stroke_host.ui.main_window" not in source
    assert 'if __name__ == "__main__"' in source


def test_release_script_builds_only_the_two_named_artifacts_from_git():
    source = (ROOT / "scripts" / "build_release.ps1").read_text(
        encoding="utf-8"
    )
    assert "StrokeGuard-Demo" in source
    assert "StrokeGuard-Developer-Handoff.zip" in source
    assert "git archive" in source
    assert "git diff --quiet" in source
    assert "--onefile" in source
    assert "--windowed" in source
    assert "device-deployment.example.yaml" in source
    assert "--add-data" in source
    for excluded in ("numpy", "cv2", "mediapipe", "sounddevice", "pyttsx3", "keyring"):
        assert f'--exclude-module "{excluded}"' in source
    assert "--collect-submodules" not in source
    assert "--hidden-import" not in source
    assert "sdkconfig" in source
    assert "\\.docx$" in source


def test_handoff_documents_current_limits_and_rebuild_commands():
    text = (ROOT / "docs" / "developer-handoff.md").read_text(
        encoding="utf-8"
    )
    assert "GC2145" in text
    assert "NMO432" in text
    assert "训练权重" in text
    assert "VPS" in text
    assert "build_release.ps1" in text
    assert "真实设备" in text
    assert "不生成模拟数据" in text


def test_demo_window_resolves_bundled_yaml_and_external_firmware_paths():
    source = (ROOT / "host_pc" / "stroke_host" / "demo" / "window.py").read_text(
        encoding="utf-8"
    )
    assert 'getattr(sys, "_MEIPASS"' in source
    assert "sys.executable" in source
    assert "device-deployment.example.yaml" in source
