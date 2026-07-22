from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "firmware_esp32" / "main" / "camera_coprocessor.c"


def _control_function() -> str:
    source = SOURCE.read_text(encoding="utf-8")
    start = source.index("esp_err_t sg_camera_coprocessor_control")
    end = source.index("sg_screening_stage_t sg_camera_coprocessor_stage", start)
    return source[start:end]


def test_camera_scores_arrive_on_uart1_gpio9_with_crc_stream_parser() -> None:
    source = SOURCE.read_text(encoding="utf-8")

    for token in (
        "UART_NUM_1",
        "GPIO_NUM_9",
        "115200",
        "sg_camera_uart_stream_feed",
        "SG_CAMERA_UART_FRESH_US 2000000LL",
        "uart_read_bytes",
    ):
        assert token in source
    assert "i2c_master_transmit" not in source
    assert "i2c_master_receive" not in source


def test_screening_control_clears_uart_freshness_locally() -> None:
    function = _control_function()

    assert "uart_flush_input" in function
    assert "camera UART session armed" in function
    assert "s_last_received_us = 0" in function


def test_control_is_explicitly_local_for_one_way_transport() -> None:
    function = _control_function()

    assert "camera UART session armed" in function
    assert "screening control confirmed" not in function
    assert "i2c_master_transmit" not in function
    assert "return ESP_OK" in function


def test_control_flushes_transport_before_reporting_session_armed() -> None:
    function = _control_function()

    flushed = function.index("uart_flush_input")
    armed = function.index("camera UART session armed")
    assert armed > flushed


def test_face_hold_is_five_seconds_but_transport_failure_clears_scores() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    poll_task = source.index("static void camera_poll_task")
    poll_error = source.index("if (err != ESP_OK)", poll_task)
    next_success = source.index("poll_failures = 0", poll_error)
    error_branch = source[poll_error:next_success]

    assert "SG_CAMERA_FACE_HOLD_US 5000000LL" in source
    assert "now_us - face_seen_us > SG_CAMERA_FACE_HOLD_US" in source
    assert "publish_unavailable(now_us)" in error_branch
