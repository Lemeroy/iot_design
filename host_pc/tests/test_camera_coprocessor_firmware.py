from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CAMERA = ROOT / "firmware_camera"
MAIN = CAMERA / "main"


def read(name: str) -> str:
    return (MAIN / name).read_text(encoding="utf-8")


def test_camera_firmware_exposes_i2c_scores_not_network_media():
    target = read("camera_score_target.c")
    app = read("app_main.c")
    adapter = read("camera_capture_adapter.cpp")

    assert "i2c_new_slave_device" in target
    assert "i2c_slave_transmit" in target
    assert "sg_camera_face_response_encode" in app
    assert "GPIO_NUM_47" in target
    assert "GPIO_NUM_48" in target
    assert "esp_camera_init" in adapter
    assert "HumanFaceDetect" in adapter
    assert "PIXFORMAT_RGB565" in adapter
    for forbidden in ("esp_mqtt", "jpeg_b64", "http_client"):
        assert forbidden not in app.lower()


def test_camera_project_contains_build_and_privacy_documentation():
    assert (CAMERA / "CMakeLists.txt").is_file()
    assert (CAMERA / "sdkconfig.defaults").is_file()
    readme = (CAMERA / "README.md").read_text(encoding="utf-8")
    assert "human_face_detect" in readme
    assert "raw images" in readme.lower()
    assert "GPIO47" in readme and "GPIO48" in readme
    assert "0x52" in readme and "0x01" in readme


def test_two_board_bringup_documents_approved_wiring_and_safety():
    text = (ROOT / "docs" / "camera-nmo432-bringup.md").read_text("utf-8")
    for token in (
        "GPIO8", "GPIO9", "GPIO17", "GPIO18", "GPIO16", "0x52", "0x01",
        "3.3 V", "share GND", "ESP-WHO", "insufficient",
    ):
        assert token in text
    assert "5 V jumper disconnected" in text
    assert "not a\ndiagnosis" in text
