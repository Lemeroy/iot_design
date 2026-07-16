from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "firmware_camera" / "main" / "camera_score_target.c"


def _receive_callback() -> str:
    source = SOURCE.read_text(encoding="utf-8")
    start = source.index("static bool camera_target_on_receive")
    end = source.index("static bool camera_target_on_request", start)
    return source[start:end]


def test_control_write_is_latched_before_ordinary_event_queue() -> None:
    callback = _receive_callback()
    control_branch = callback.index("SG_CAMERA_CONTROL_REGISTER")
    queue_send = callback.index("xQueueSendFromISR")

    assert control_branch < queue_send
    before_queue = callback[control_branch:queue_send]
    assert "pending_control" in before_queue
    assert "control_pending" in before_queue
    assert "portENTER_CRITICAL_ISR" in before_queue
    assert "return" in before_queue


def test_ordinary_event_queue_overflow_is_counted() -> None:
    source = SOURCE.read_text(encoding="utf-8")

    assert "dropped_events" in source
    assert "xQueueSendFromISR" in source
    assert "pdPASS" in _receive_callback()

