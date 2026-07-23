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


def test_guided_screening_stays_idle_until_explicit_start_control() -> None:
    source = ADAPTER.read_text(encoding="utf-8")
    init_start = source.index('extern "C" esp_err_t sg_camera_capture_init')
    control_start = source.index(
        'extern "C" esp_err_t sg_camera_capture_control', init_start
    )
    observe_start = source.index(
        'extern "C" esp_err_t sg_camera_capture_observe', control_start
    )
    init_function = source[init_start:control_start]
    control_function = source[control_start:observe_start]
    observe_function = source[observe_start:]

    assert "sg_screening_session_cancel(&s_screening)" in init_function
    assert "sg_screening_session_start(&s_screening" not in init_function
    assert "sg_screening_session_start(&s_screening" in control_function
    assert "automatic screening cycle" not in source
    assert "SG_CAMERA_AUTO_RESTART_US" not in source
    assert "s_auto_restart_deadline_us" not in observe_function


def test_tongue_timeout_keeps_tongue_unavailable_for_fusion() -> None:
    source = SESSION.read_text(encoding="utf-8")
    tongue_stage = source.index("case SG_STAGE_TONGUE:")
    done_stage = source.index("enter_stage(session, SG_STAGE_DONE", tongue_stage)
    tongue_completion = source[tongue_stage:done_stage]

    assert "session->sample_count" in tongue_completion
    assert "session->tongue_result.valid = true" in tongue_completion
    assert "enter_stage(session, SG_STAGE_ERROR" in source


def test_invalid_guided_eye_is_unavailable_but_does_not_abort_tongue_stage() -> None:
    source = SESSION.read_text(encoding="utf-8")
    eye_right = source.index("case SG_STAGE_EYE_RIGHT:")
    tongue_case = source.index("case SG_STAGE_TONGUE:", eye_right)
    block = source[eye_right:tongue_case]

    assert "finish_eye_sequence(session)" in block
    assert "enter_stage(session, SG_STAGE_TONGUE" in block
    assert "enter_stage(session, SG_STAGE_ERROR" not in block
