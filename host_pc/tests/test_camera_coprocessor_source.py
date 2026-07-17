from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "firmware_esp32" / "main" / "camera_coprocessor.c"


def _control_function() -> str:
    source = SOURCE.read_text(encoding="utf-8")
    start = source.index("esp_err_t sg_camera_coprocessor_control")
    end = source.index("sg_screening_stage_t sg_camera_coprocessor_stage", start)
    return source[start:end]


def test_control_waits_for_expected_camera_stage_with_bounded_retries() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    function = _control_function()

    assert "SG_CAMERA_CONTROL_CONFIRM_RETRIES" in source
    assert "SG_CAMERA_CONTROL_CONFIRM_DELAY_MS" in source
    assert "SG_CAMERA_STAGE_REGISTER" in function
    assert "sg_camera_stage_parse" in function
    assert "SG_STAGE_FACE" in function
    assert "SG_STAGE_IDLE" in function
    assert "ESP_ERR_TIMEOUT" in function


def test_control_logs_only_after_stage_confirmation() -> None:
    function = _control_function()

    confirmed = function.index("screening control confirmed")
    stage_parse = function.index("sg_camera_stage_parse")
    assert confirmed > stage_parse


def test_face_hold_is_five_seconds_but_transport_failure_clears_scores() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    poll_task = source.index("static void camera_poll_task")
    poll_error = source.index("if (err != ESP_OK)", poll_task)
    next_success = source.index("poll_failures = 0", poll_error)
    error_branch = source[poll_error:next_success]

    assert "SG_CAMERA_FACE_HOLD_US 5000000LL" in source
    assert "now_us - face_seen_us > SG_CAMERA_FACE_HOLD_US" in source
    assert "publish_unavailable(now_us)" in error_branch
