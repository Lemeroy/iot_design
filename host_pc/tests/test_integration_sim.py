"""集成测试: SimSource + 完整 pipeline."""
import time

from stroke_host.io.sim_source import SimSource
from stroke_host.io.frame_recorder import FrameRecorder


def test_sim_produces_valid_frames():
    src = SimSource(hz=50.0)  # 加速测试
    src.open()
    frames = []
    it = iter(src.frames())
    for _ in range(5):
        frames.append(next(it))
    src.close()

    assert len(frames) == 5
    for i, f in enumerate(frames):
        js = f.json
        assert js is not None
        assert js["type"] == "heartbeat"
        assert js["seq"] == i
        assert 0 <= js["csi_score"] <= 100


def test_sim_to_recorder(tmp_path):
    src = SimSource(hz=100.0)
    rec = FrameRecorder(tmp_path, device_id="sg-test")
    src.open()
    rec.open()
    try:
        it = iter(src.frames())
        for _ in range(3):
            rec.write(next(it))
    finally:
        rec.close()
        src.close()

    sessions = list(tmp_path.glob("session_*"))
    assert sessions
    enc = sessions[0] / "frames.jsonl.enc"
    assert enc.stat().st_size > 0
