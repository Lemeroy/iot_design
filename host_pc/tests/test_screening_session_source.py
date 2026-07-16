from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SESSION = ROOT / "firmware_camera" / "main" / "screening_session.c"
ADAPTER = ROOT / "firmware_camera" / "main" / "camera_capture_adapter.cpp"


def test_face_stage_requires_consecutive_ready_samples() -> None:
    source = SESSION.read_text(encoding="utf-8")

    assert "reset_face_samples_on_invalid" in source
    assert "session->stage == SG_STAGE_FACE" in source
    assert "!sample->face_ready" in source
    assert "session->sample_count = 0" in source


def test_face_stage_keeps_a_bounded_overall_deadline() -> None:
    source = SESSION.read_text(encoding="utf-8")

    assert "SG_FACE_DEADLINE_US" in source
    assert "enter_stage(session, SG_STAGE_ERROR" in source


def test_face_adapter_reports_bounded_local_rejection_reasons() -> None:
    source = ADAPTER.read_text(encoding="utf-8")

    assert "face sample rejected reason=" in source
    assert "no_face" in source
    assert "landmarks" in source
    assert "geometry" in source
    assert "baseline" in source
    assert "SG_FACE_REJECT_LOG_INTERVAL" in source

