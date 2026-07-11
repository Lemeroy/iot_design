"""M2 face backend selection and 68-point output tests."""
from pathlib import Path

import numpy as np

from stroke_host.perception.face_detect import FaceLandmarks


def _fake_landmarks() -> FaceLandmarks:
    lm = np.arange(478 * 3, dtype=np.float32).reshape(478, 3)
    return FaceLandmarks(landmarks=lm, image_w=640, image_h=480)


def test_auto_backend_falls_back_to_mediapipe_without_yolo_weights():
    from stroke_host.perception.face_backend import FaceBackendConfig, resolve_face_backend

    selection = resolve_face_backend(
        FaceBackendConfig(backend="auto", yolo_weights=Path("missing.pt"))
    )

    assert selection.backend == "mediapipe"
    assert "yolo_weights_missing" in selection.reasons


def test_forced_yolo_without_weights_is_unavailable_not_crash():
    from stroke_host.perception.face_backend import FaceBackendConfig, resolve_face_backend

    selection = resolve_face_backend(
        FaceBackendConfig(backend="yolo", yolo_weights=Path("missing.pt"))
    )

    assert selection.backend == "unavailable"
    assert "yolo_weights_missing" in selection.reasons


def test_face_result_exposes_68_landmarks_from_facemesh():
    from stroke_host.perception.face_backend import result_from_facemesh

    result = result_from_facemesh(_fake_landmarks(), backend="mediapipe")

    assert result.available
    assert result.backend == "mediapipe"
    assert result.landmarks68 is not None
    assert result.landmarks68.shape == (68, 3)
    assert result.raw["landmarks68_count"] == 68


def test_cli_accepts_face_backend_and_yolo_weights():
    from stroke_host.main import _build_argparser

    args = _build_argparser().parse_args([
        "--source", "synthetic-frame",
        "--perception",
        "--face-backend", "yolo",
        "--yolo-weights", "models/yolov8n-face.pt",
    ])

    assert args.face_backend == "yolo"
    assert args.yolo_weights == "models/yolov8n-face.pt"


def test_ui_entrypoints_accept_face_backend_and_yolo_weights():
    from stroke_host.gui.observer import _build_argparser as observer_parser
    from stroke_host.ui.main_window import _build_argparser as ui_parser

    for build_parser in (observer_parser, ui_parser):
        args = build_parser().parse_args([
            "--source", "real",
            "--perception",
            "--face-backend", "mediapipe",
            "--yolo-weights", "models/yolov8n-face.pt",
        ])

        assert args.face_backend == "mediapipe"
        assert args.yolo_weights == "models/yolov8n-face.pt"
