from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_main_window_has_no_pc_score_injection_path():
    source = (ROOT / "stroke_host" / "ui" / "main_window.py").read_text(
        encoding="utf-8"
    )
    assert "S3 Fusion" not in source
    assert "S3Bridge" not in source
    assert "chk_s3" not in source
    assert "s3_bridge=" not in source
    assert "publish_uplink(" not in source
    assert "mqtt_pub=" not in source


def test_config_workspace_is_integrated_as_a_separate_widget():
    source = (ROOT / "stroke_host" / "ui" / "main_window.py").read_text(
        encoding="utf-8"
    )
    assert "ConfigPanel" in source
    assert "workspace_tabs" in source
