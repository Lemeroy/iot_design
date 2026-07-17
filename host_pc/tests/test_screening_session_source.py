from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SESSION = ROOT / "firmware_camera" / "main" / "screening_session.c"
ADAPTER = ROOT / "firmware_camera" / "main" / "camera_capture_adapter.cpp"


def test_face_stage_accepts_two_valid_samples_in_a_five_frame_window() -> None:
    source = SESSION.read_text(encoding="utf-8")

    assert "SG_FACE_SAMPLE_WINDOW" in source
    assert "SG_SCREENING_FACE_REQUIRED_SAMPLES 2U" in source
    assert "SG_FACE_DEADLINE_US 20000000LL" in source
    assert "face_sample_window" in source
    assert "face_window_count" in source
    assert "count_face_samples" in source
    assert "face_ready_to_advance" in source
    assert "elapsed >= SG_STAGE_SETTLE_US" in source


def test_face_stage_keeps_a_bounded_overall_deadline() -> None:
    source = SESSION.read_text(encoding="utf-8")

    assert "SG_FACE_DEADLINE_US" in source
    assert "enter_stage(session, SG_STAGE_ERROR" in source


def test_eye_stages_keep_recent_samples_long_enough_for_user_response() -> None:
    source = SESSION.read_text(encoding="utf-8")
    header = (SESSION.parent / "screening_session.h").read_text(encoding="utf-8")

    assert "SG_EYE_DURATION_US 4000000LL" in source
    assert "sample_next" in header
    assert "session->sample_next" in source
    assert "% SG_SCREENING_STABLE_SAMPLES" in source


def test_face_adapter_reports_bounded_local_rejection_reasons() -> None:
    source = ADAPTER.read_text(encoding="utf-8")

    assert "face sample rejected reason=" in source
    assert "no_face" in source
    assert "landmarks" in source
    assert "geometry" in source
    assert "baseline" in source
    assert "SG_FACE_REJECT_LOG_INTERVAL" in source


def test_detector_uses_balanced_thresholds_and_preview_bbox_hysteresis() -> None:
    source = ADAPTER.read_text(encoding="utf-8")

    assert "SG_FACE_PROPOSAL_SCORE_THRESHOLD = 0.40f" in source
    assert "SG_FACE_LANDMARK_SCORE_THRESHOLD = 0.45f" in source
    assert "set_score_thr(SG_FACE_PROPOSAL_SCORE_THRESHOLD, 0)" in source
    assert "set_score_thr(SG_FACE_LANDMARK_SCORE_THRESHOLD, 1)" in source
    assert "SG_FACE_BBOX_HOLD_FRAMES = 2" in source
    assert "s_bbox_miss_count" in source
