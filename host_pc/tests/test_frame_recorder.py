"""FrameRecorder: 加密写入 + 24h 清理."""
import base64
import json
import time
from pathlib import Path

from stroke_host.io.cdc_reader import Frame, TYPE_HEARTBEAT
from stroke_host.io.frame_recorder import FrameRecorder
from stroke_host.utils.crypto import AesGcm


def _mk_frame(seq: int) -> Frame:
    payload = json.dumps({"type": "heartbeat", "seq": seq, "csi_score": 80}).encode()
    return Frame(type=TYPE_HEARTBEAT, payload=payload, ts_recv=time.time())


def test_record_and_decrypt(tmp_path):
    rec = FrameRecorder(tmp_path, device_id="sg-test")
    rec.open()
    try:
        for i in range(5):
            rec.write(_mk_frame(i))
    finally:
        rec.close()

    # 找 session 目录
    sessions = list(tmp_path.glob("session_*"))
    assert len(sessions) == 1
    enc_file = sessions[0] / "frames.jsonl.enc"
    assert enc_file.exists()

    aes = AesGcm()
    lines = enc_file.read_bytes().splitlines()
    assert len(lines) == 5
    for i, line in enumerate(lines):
        blob = base64.b64decode(line)
        plain = aes.decrypt(blob, aad=b"sg-test")
        rec_obj = json.loads(plain)
        assert rec_obj["type"] == TYPE_HEARTBEAT
        payload = base64.b64decode(rec_obj["payload_b64"])
        assert json.loads(payload)["seq"] == i


def test_sweep_removes_old_sessions(tmp_path):
    # 手动伪造一个 25h 前的 session
    old = tmp_path / "session_20200101_000000"
    old.mkdir()
    (old / "frames.jsonl.enc").write_bytes(b"stale")
    # 改 mtime
    stale = time.time() - 25 * 3600
    import os
    os.utime(old, (stale, stale))
    os.utime(old / "frames.jsonl.enc", (stale, stale))

    rec = FrameRecorder(tmp_path, device_id="sg-test")
    rec.open()
    try:
        # 手动扫一次
        removed = rec.sweep_now()
        assert removed >= 1
        assert not old.exists()
    finally:
        rec.close()


def test_current_session_not_swept(tmp_path):
    rec = FrameRecorder(tmp_path, device_id="sg-test")
    rec.open()
    try:
        cur = rec._session_dir
        # 即使 mtime 被改成 25h 前, 当前 session 也不能删
        import os
        stale = time.time() - 25 * 3600
        os.utime(cur, (stale, stale))
        rec.sweep_now()
        assert cur.exists()
    finally:
        rec.close()
