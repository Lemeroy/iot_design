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
    defaults = (CAMERA / "sdkconfig.defaults").read_text(encoding="utf-8")

    assert "i2c_new_slave_device" in target
    assert "i2c_slave_register_event_callbacks" in target
    assert ".on_receive" in target
    assert ".on_request" in target
    assert "i2c_slave_write" in target
    assert "CONFIG_I2C_ENABLE_SLAVE_DRIVER_VERSION_2=y" in defaults
    assert "sg_camera_face_response_encode" in app
    assert "GPIO_NUM_47" in target
    assert "GPIO_NUM_48" in target
    assert "esp_camera_init" in adapter
    assert "HumanFaceDetect" in adapter
    assert "PIXFORMAT_RGB565" in adapter
    for forbidden in ("esp_mqtt", "jpeg_b64", "http_client"):
        assert forbidden not in app.lower()


def test_camera_i2c_response_is_queued_only_when_master_requests_it():
    target = read("camera_score_target.c")

    assert ".i2c_port = I2C_NUM_0" in target
    assert "SG_CAMERA_TARGET_EVENT_REQUEST" in target
    assert "xQueueSendFromISR" in target
    assert "xQueueReceive" in target
    assert "i2c_slave_transmit" not in target
    assert "I2C target ready" in target


def test_main_firmware_logs_first_camera_poll_failure_for_bringup():
    main_camera = (ROOT / "firmware_esp32" / "main" / "camera_coprocessor.c").read_text(
        encoding="utf-8"
    )

    assert "camera poll failed" in main_camera


def test_camera_address_matches_shared_protocol():
    defaults = (ROOT / "firmware_esp32" / "sdkconfig.defaults").read_text(
        encoding="utf-8"
    )
    assert "CONFIG_STROKEGUARD_CAMERA_I2C_ADDRESS=0x52" in defaults


def test_camera_orientation_matches_esp_who_s3_default():
    adapter = read("camera_capture_adapter.cpp")

    assert "set_vflip(sensor, 1)" in adapter


def test_camera_usb_preview_is_request_gated_and_crc_protected():
    adapter = read("camera_capture_adapter.cpp")
    preview = read("camera_usb_preview.c")
    cmake = read("CMakeLists.txt")

    assert "sg_camera_usb_preview_requested" in adapter
    assert "sg_camera_usb_preview_send" in adapter
    assert "frame2jpg" in preview
    assert "SG_CAMERA_PREVIEW_REQUEST" in preview
    assert "SG_CAMERA_PREVIEW_MAX_JPEG" in preview
    assert "sg_camera_preview_crc32" in preview
    assert "921600" in preview
    assert "camera_usb_preview.c" in cmake
    assert "camera_preview_protocol.c" in cmake
    assert "frame preview" not in adapter
    assert "frame diagnostic" not in adapter
    assert "set_score_thr(0.30f" not in adapter


def test_camera_project_contains_build_and_privacy_documentation():
    assert (CAMERA / "CMakeLists.txt").is_file()
    assert (CAMERA / "sdkconfig.defaults").is_file()
    readme = (CAMERA / "README.md").read_text(encoding="utf-8")
    assert "human_face_detect" in readme
    assert "raw images" in readme.lower()
    assert "GPIO47" in readme and "GPIO48" in readme
    assert "0x52" in readme and "0x01" in readme
    for token in (
        "camera_usb_preview.py",
        "COM4",
        "921600",
        "must be closed",
        "not saved",
        "not uploaded",
    ):
        assert token in readme


def test_two_board_bringup_documents_approved_wiring_and_safety():
    text = (ROOT / "docs" / "camera-nmo432-bringup.md").read_text("utf-8")
    for token in (
        "GPIO8", "GPIO9", "GPIO17", "GPIO18", "GPIO16", "0x52", "0x01",
        "3.3 V", "share GND", "ESP-WHO", "insufficient",
    ):
        assert token in text
    assert "5 V jumper disconnected" in text
    assert "not a\ndiagnosis" in text
    assert "camera_usb_preview.py" in text
    assert "I2C remains active" in text
