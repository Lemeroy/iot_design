"""M3 pipeline integration tests for T/E/B readiness."""
from stroke_host.io.sim_source import SyntheticFrameSource
from stroke_host.main import PerceptionPipeline


def test_pipeline_reports_m3_unavailable_when_face_backend_unavailable(tmp_path):
    src = SyntheticFrameSource(hz=100.0, csi_score=76)
    src.open()
    try:
        frame = next(iter(src.frames()))
    finally:
        src.close()

    pipe = PerceptionPipeline(
        src,
        face_backend="yolo",
        yolo_weights=str(tmp_path / "missing-yolo.pt"),
    )

    result = pipe.process(frame)

    assert result["face"]["score"] == -1
    assert result["tongue"]["score"] == -1
    assert result["eye"]["score"] == -1
    for key in ("face", "tongue", "eye"):
        assert "face_backend_unavailable" in result[key]["reasons"]
        assert result[key]["raw"]["face_backend"] == "unavailable"
        assert "yolo_weights_missing" in result[key]["raw"]["backend_reasons"]

    assert result["csi"]["score"] == 76
    assert result["csi"]["raw"]["source"] == "synthetic_frame"
    assert result["csi"]["raw"]["quality"] == "simulated"
