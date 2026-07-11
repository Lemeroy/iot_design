"""UI worker pipeline configuration tests."""
import argparse


def test_pyqt_backend_worker_passes_face_backend_config(monkeypatch):
    from stroke_host.ui import main_window

    seen = {}

    class DummyPipeline:
        def __init__(self, source, face_backend="auto", yolo_weights=""):
            seen["source"] = source
            seen["face_backend"] = face_backend
            seen["yolo_weights"] = yolo_weights

    monkeypatch.setattr(main_window, "PerceptionPipeline", DummyPipeline)

    source = object()
    worker = main_window.BackendWorker(
        argparse.Namespace(
            face_backend="yolo",
            yolo_weights="models/yolov8n-face.pt",
        )
    )
    worker._src = source

    assert worker._build_pipeline() is not None
    assert seen == {
        "source": source,
        "face_backend": "yolo",
        "yolo_weights": "models/yolov8n-face.pt",
    }
