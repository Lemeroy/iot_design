"""SourceWorker 非 GUI 部分测试."""
import queue
import time

from stroke_host.gui.observer import SourceWorker
from stroke_host.io.sim_source import SimSource


def test_worker_produces_frames_and_stops():
    q: queue.Queue = queue.Queue(maxsize=128)
    w = SourceWorker(lambda: SimSource(hz=100.0), q,
                     rec=None, enable_perception=False)
    w.start()
    frames = []
    deadline = time.time() + 2
    while len(frames) < 5 and time.time() < deadline:
        try:
            item = q.get(timeout=0.5)
            frames.append(item)
        except queue.Empty:
            pass
    w.stop()
    w.join(timeout=2)
    assert not w.is_alive()
    assert w.err is None
    assert len(frames) >= 5
    for frame, res in frames:
        assert frame.json["type"] == "heartbeat"
        assert res is None  # perception 未启用


def test_worker_reports_error_on_bad_factory():
    q: queue.Queue = queue.Queue()

    def bad():
        raise RuntimeError("boom")

    w = SourceWorker(bad, q, rec=None, enable_perception=False)
    w.start()
    w.join(timeout=2)
    assert w.err is not None
    assert "boom" in w.err


def test_worker_passes_face_backend_config_to_pipeline(monkeypatch):
    import stroke_host.main as main_mod

    seen = {}

    class DummyPipeline:
        def __init__(self, source, face_backend="auto", yolo_weights=""):
            seen["source"] = source
            seen["face_backend"] = face_backend
            seen["yolo_weights"] = yolo_weights

    monkeypatch.setattr(main_mod, "PerceptionPipeline", DummyPipeline)

    q: queue.Queue = queue.Queue()
    source = object()
    w = SourceWorker(
        lambda: source,
        q,
        rec=None,
        enable_perception=True,
        face_backend="yolo",
        yolo_weights="models/yolov8n-face.pt",
    )
    w.source = source

    assert w._build_pipeline() is not None
    assert seen == {
        "source": source,
        "face_backend": "yolo",
        "yolo_weights": "models/yolov8n-face.pt",
    }
