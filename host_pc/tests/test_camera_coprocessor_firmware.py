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

    assert '#include "driver/i2c_slave.h"' in target
    assert '#include "driver/i2c.h"' not in target
    assert ".i2c_port = I2C_NUM_0" in target
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
    assert "PIXFORMAT_YUV422" in adapter
    assert "fmt2rgb888" in adapter
    assert "bgr888_to_rgb888_in_place" in adapter
    assert "MALLOC_CAP_SPIRAM" in adapter
    assert "DL_IMAGE_PIX_TYPE_RGB888" in adapter
    assert "config.pixel_format = PIXFORMAT_JPEG" not in adapter
    assert "config.fb_count = 1" in adapter
    assert "config.grab_mode = CAMERA_GRAB_WHEN_EMPTY" in adapter
    for forbidden in ("esp_mqtt", "jpeg_b64", "http_client"):
        assert forbidden not in app.lower()


def test_camera_i2c_response_is_served_after_register_selection():
    target = read("camera_score_target.c")

    assert ".i2c_port = I2C_NUM_0" in target
    assert ".slave_addr = SG_CAMERA_I2C_ADDRESS" in target
    assert "SG_CAMERA_TARGET_EVENT_RECEIVE" in target
    assert "SG_CAMERA_TARGET_EVENT_REQUEST" in target
    assert "xQueueSendFromISR" in target
    assert "xQueueReceive" in target
    assert "i2c_slave_write" in target
    assert "i2c_slave_transmit" not in target
    assert "I2C target ready" in target


def test_main_firmware_logs_first_camera_poll_failure_for_bringup():
    main_camera = (ROOT / "firmware_esp32" / "main" / "camera_coprocessor.c").read_text(
        encoding="utf-8"
    )

    assert "camera poll failed" in main_camera
    assert "SDA=%d SCL=%d" in main_camera
    assert "gpio_get_level" in main_camera


def test_camera_address_matches_shared_protocol():
    defaults = (ROOT / "firmware_esp32" / "sdkconfig.defaults").read_text(
        encoding="utf-8"
    )
    assert "CONFIG_STROKEGUARD_CAMERA_I2C_ADDRESS=0x52" in defaults


def test_camera_protocol_exposes_numeric_face_metrics_register():
    header = (ROOT / "firmware_common" / "camera_scores_protocol.h").read_text(
        encoding="utf-8"
    )
    source = (ROOT / "firmware_common" / "camera_scores_protocol.c").read_text(
        encoding="utf-8"
    )

    assert "SG_CAMERA_FACE_METRICS_REGISTER 0x02U" in header
    assert "sg_camera_face_metrics_response_t" in header
    assert "sizeof(sg_camera_face_metrics_response_t) == 4" in header
    assert "sg_camera_face_metrics_parse" in source
    assert "sg_camera_face_metrics_encode" in source


def test_camera_protocol_exposes_guided_eye_tongue_registers():
    header = (ROOT / "firmware_common" / "camera_scores_protocol.h").read_text(
        encoding="utf-8"
    )
    source = (ROOT / "firmware_common" / "camera_scores_protocol.c").read_text(
        encoding="utf-8"
    )

    for token in (
        "SG_CAMERA_EYE_REGISTER 0x03U",
        "SG_CAMERA_TONGUE_REGISTER 0x04U",
        "SG_CAMERA_CONTROL_REGISTER 0x10U",
        "SG_CAMERA_STAGE_REGISTER 0x11U",
        "sg_camera_modal_response_t",
        "sg_camera_stage_response_t",
        "sg_camera_modal_parse",
        "sg_camera_modal_encode",
        "sg_camera_stage_parse",
        "sg_camera_stage_encode",
    ):
        assert token in header or token in source


def test_camera_has_quality_gated_five_point_geometry_module():
    header = read("face_geometry.h")
    source = read("face_geometry.cpp")

    assert "sg_face_geometry_evaluate" in header
    for token in (
        "kMinFaceWidth",
        "kMinEyeDistance",
        "kMaxEyeRollDeg",
        "kAngleHealthyDeg",
        "kAngleZeroDeg",
        "kAsymmetryHealthy",
        "kAsymmetryZero",
        "corner_asymmetry",
    ):
        assert token in source


def test_face_geometry_scores_compensated_corner_height_asymmetry():
    source = read("face_geometry.cpp")

    assert "corner_height" in source
    assert "kCornerHeightHealthy" in source
    assert "kCornerHeightZero" in source
    assert "std::min" in source


def test_camera_has_volatile_personal_face_baseline():
    header = read("face_baseline.h")
    source = read("face_baseline.c")

    for token in (
        "SG_FACE_BASELINE_MIN_QUALITY 50U",
        "SG_FACE_BASELINE_MAX_ANGLE_RANGE 5.0f",
        "SG_FACE_BASELINE_MAX_ASYMMETRY_RANGE 0.08f",
        "SG_FACE_BASELINE_CALIBRATION_SAMPLES",
        "SG_FACE_BASELINE_OUTPUT_SAMPLES",
        "SG_FACE_BASELINE_RESET_US",
        "SG_FACE_BASELINE_INVALID_TOLERANCE 3U",
        "calibration_invalid_count",
        "sg_face_baseline_update",
        "sg_face_baseline_note_invalid",
        "sg_face_baseline_ready",
    ):
        assert token in header or token in source
    for forbidden in ("nvs", "mqtt", "fopen", "malloc"):
        assert forbidden not in source.lower()


def test_camera_eye_kernel_is_local_and_fixed_storage():
    header = read("eye_tracking.h")
    source = read("eye_tracking.cpp")

    for token in (
        "sg_eye_measure",
        "sg_eye_score_sequence",
        "inter_eye_distance",
        "eye_line_angle_deg",
    ):
        assert token in header or token in source
    for forbidden in (
        "malloc", "new ", "fopen", "mqtt", "http", "socket", "jpeg_b64"
    ):
        assert forbidden not in source.lower()


def test_camera_tongue_kernel_is_auxiliary_local_and_fixed_storage():
    header = read("tongue_deviation.h")
    source = read("tongue_deviation.cpp")

    for token in (
        "sg_tongue_measure",
        "signed_offset",
        "face_roll_deg",
        "auxiliary",
    ):
        assert token in header.lower() or token in source.lower()
    for forbidden in (
        "malloc", "new ", "fopen", "mqtt", "http", "socket", "jpeg_b64"
    ):
        assert forbidden not in source.lower()
    assert "kMinTongueSaturation = 25" in source
    assert "kMinRedGreenDelta = 20" in source
    assert "mouth_y" in header
    assert "protrusion" in source


def test_camera_continuously_tracks_eye_with_guided_override():
    header = read("eye_continuous.h")
    source = read("eye_continuous.cpp")
    adapter = read("camera_capture_adapter.cpp")

    for token in (
        "SG_EYE_CONTINUOUS_CAPACITY 12U",
        "SG_EYE_CONTINUOUS_MIN_SAMPLES 6U",
        "SG_EYE_CONTINUOUS_MAX_DROPOUT 2U",
        "SG_EYE_GUIDED_OVERRIDE_US 30000000LL",
        "sg_eye_continuous_update",
        "sg_eye_select_result",
    ):
        assert token in header or token in source
    assert "sg_eye_continuous_update" in adapter
    assert "sg_eye_select_result" in adapter


def test_camera_guided_session_is_wired_to_i2c_and_capture():
    session_h = read("screening_session.h")
    session_c = read("screening_session.c")
    adapter = read("camera_capture_adapter.cpp")
    target = read("camera_score_target.c")
    app = read("app_main.c")

    for token in (
        "sg_screening_session_start",
        "sg_screening_session_cancel",
        "sg_screening_session_update",
        "SG_STAGE_EYE_CENTER",
        "SG_STAGE_TONGUE",
    ):
        assert token in session_h or token in session_c
    assert "sg_eye_measure" in adapter
    assert "sg_tongue_measure" in adapter
    assert "eye sample stage=%u left=%d right=%d quality=%u" in adapter
    assert "eye sample invalid stage=%u count=%lu" in adapter
    assert "directional_travel" in read("eye_tracking.cpp")
    assert "(uint8_t)(opposite_steps" in read("eye_tracking.cpp")
    assert "tongue sample offset=%d score=%u quality=%u" in adapter
    assert "tongue sample invalid count=%lu" in adapter
    assert "SG_CAMERA_CONTROL_REGISTER" in target
    assert "SG_CAMERA_EYE_REGISTER" in target
    assert "SG_CAMERA_TONGUE_REGISTER" in target
    assert "SG_CAMERA_STAGE_REGISTER" in target
    assert "sg_camera_score_target_take_control" in app


def test_camera_integrates_five_landmarks_and_dual_i2c_registers():
    adapter = read("camera_capture_adapter.cpp")
    capture_header = read("camera_capture_adapter.h")
    target = read("camera_score_target.c")
    app = read("app_main.c")
    cmake = read("CMakeLists.txt")

    assert "keypoint.size() == 10" in adapter
    assert ".left_eye = {(int16_t)result.keypoint[0], (int16_t)result.keypoint[1]}" in adapter
    assert ".left_mouth = {(int16_t)result.keypoint[2], (int16_t)result.keypoint[3]}" in adapter
    assert ".nose = {(int16_t)result.keypoint[4], (int16_t)result.keypoint[5]}" in adapter
    assert ".right_eye = {(int16_t)result.keypoint[6], (int16_t)result.keypoint[7]}" in adapter
    assert ".right_mouth = {(int16_t)result.keypoint[8], (int16_t)result.keypoint[9]}" in adapter
    assert "sg_face_geometry_evaluate" in adapter
    assert "sg_face_baseline_update" in adapter
    assert "sg_face_baseline_note_invalid" in adapter
    assert "sg_face_baseline_ready" in adapter
    assert "sg_face_stabilizer_push" not in adapter
    assert "sg_camera_face_metrics_t face_metrics" in capture_header
    assert "SG_CAMERA_FACE_REGISTER" in target
    assert "SG_CAMERA_FACE_METRICS_REGISTER" in target
    assert "latest_bbox" in target
    assert "latest_metrics" in target
    assert "sg_camera_face_metrics_encode" in app
    assert "&metrics_response" in app
    assert '"face_geometry.cpp"' in cmake
    assert '"face_baseline.c"' in cmake
    for forbidden in ("tongue_score", "eye_score"):
        assert forbidden not in adapter


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
