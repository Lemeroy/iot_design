from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_demo_entry_uses_package_import_and_main_guard():
    source = (ROOT / "host_pc" / "stroke_host" / "demo_entry.py").read_text(
        encoding="utf-8"
    )
    assert "from stroke_host.ui.main_window import main" in source
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
    assert "sdkconfig" in source
    assert "\\.docx$" in source


def test_handoff_documents_current_limits_and_rebuild_commands():
    text = (ROOT / "docs" / "developer-handoff.md").read_text(
        encoding="utf-8"
    )
    assert "GC2145" in text
    assert "INMP441" in text
    assert "训练权重" in text
    assert "VPS" in text
    assert "build_release.ps1" in text
    assert "197 passed" in text
