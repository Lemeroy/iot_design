from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CAMERA = ROOT / "firmware_camera"
MAIN = CAMERA / "main"


def read(name: str) -> str:
    return (MAIN / name).read_text(encoding="utf-8")


def test_camera_firmware_exposes_i2c_scores_not_network_media():
    target = read("camera_score_target.c")
    app = read("app_main.c")
    adapter = read("camera_capture_adapter.c")

    assert "i2c_new_slave_device" in target
    assert "i2c_slave_transmit" in target
    assert "sg_camera_scores_crc" in app
    assert "GPIO_NUM_47" in target
    assert "GPIO_NUM_48" in target
    assert "SG_CAMERA_STATUS_MODEL_MISSING" in adapter
    assert "valid_mask = 0" in adapter
    for forbidden in ("esp_mqtt", "jpeg_b64", "http_client"):
        assert forbidden not in app.lower()


def test_camera_project_contains_build_and_privacy_documentation():
    assert (CAMERA / "CMakeLists.txt").is_file()
    assert (CAMERA / "sdkconfig.defaults").is_file()
    readme = (CAMERA / "README.md").read_text(encoding="utf-8")
    assert "model_missing" in readme
    assert "raw images" in readme.lower()
    assert "GPIO47" in readme and "GPIO48" in readme
