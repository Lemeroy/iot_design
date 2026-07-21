"""StrokeGuard M1a+M2 PC 端入口.

用法:
    python -m stroke_host.main --source sim
    python -m stroke_host.main --source synthetic-frame
    python -m stroke_host.main --source real          # PC 摄像头/麦克风, 出 F/S 分
    python -m stroke_host.main --source cdc --port COM3
"""
from __future__ import annotations

import argparse
import base64
import json
import logging
import signal
import sys
from pathlib import Path
from typing import Optional

import numpy as np

from .config.profile_loader import load_profile
from .io.cdc_reader import CdcReader, TYPE_DATA
from .io.frame_recorder import FrameRecorder
from .io.sim_source import RealSource, SimSource, SyntheticFrameSource

log = logging.getLogger("stroke_host.main")


def _build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="stroke-host", description="StrokeGuard M1a/M2 host")
    p.add_argument("--source", choices=["cdc", "sim", "synthetic-frame", "real"], default="sim",
                   help="frame source (default: sim)")
    p.add_argument("--port", default="COM3", help="serial port for --source cdc")
    p.add_argument("--baud", type=int, default=115200)
    p.add_argument("--cam", type=int, default=0, help="camera index for --source real")
    p.add_argument("--profile", default="config/profile.yaml",
                   help="path to profile.yaml")
    p.add_argument("--data-dir", default="data", help="recorder root")
    p.add_argument("--no-record", action="store_true",
                   help="disable AES-GCM recording (dev only)")
    p.add_argument("--max-frames", type=int, default=0,
                   help="stop after N frames (0 = infinite)")
    p.add_argument("--perception", action="store_true",
                   help="enable M2 F/S scoring on data frames")
    p.add_argument("--face-backend", choices=["auto", "mediapipe", "yolo"],
                   default="auto",
                   help="face backend: auto prefers YOLO only when weights exist")
    p.add_argument("--yolo-weights", default="",
                   help="optional YOLOv8 face weights path")
    p.add_argument("-v", "--verbose", action="store_true")
    return p


def _make_source(args):
    if args.source == "cdc":
        return CdcReader(args.port, args.baud)
    if args.source == "real":
        return RealSource(cam_index=args.cam)
    if args.source == "synthetic-frame":
        return SyntheticFrameSource()
    return SimSource()


class PerceptionPipeline:
    """M2+M3 感知流水线: frame 帧 -> F/S/Tongue/E/B 5 模态分.

    延迟导入 mediapipe: 未安装时给 warning, F/Tongue/E 均不可用.
    """

    def __init__(self, source, face_backend: str = "auto",
                 yolo_weights: str = "") -> None:
        from .perception.face_backend import (
            FaceBackendConfig,
            resolve_face_backend,
            result_from_facemesh,
        )
        self._face_result_from_facemesh = result_from_facemesh
        yolo_path = Path(yolo_weights) if yolo_weights else None
        self._face_selection = resolve_face_backend(
            FaceBackendConfig(backend=face_backend, yolo_weights=yolo_path)
        )
        self._face_backend = self._face_selection.backend
        self._face_unavailable_reasons = list(self._face_selection.reasons)
        self._fd = None
        self._face_ok = False
        if self._face_backend == "mediapipe":
            try:
                from .perception.face_detect import FaceMeshDetector
                self._fd = FaceMeshDetector(refine_landmarks=True)
                self._face_ok = True
            except ImportError as e:
                self._face_unavailable_reasons.append("mediapipe_unavailable")
                log.warning("mediapipe unavailable, F/Tongue/E disabled: %s", e)
        elif self._face_backend == "yolo":
            self._face_unavailable_reasons.append("yolo_detector_not_integrated")
            log.warning("YOLO backend selected but detector integration awaits weights/runtime")
        else:
            log.warning("face backend unavailable: %s",
                        ",".join(self._face_selection.reasons))
        self._source = source
        from .perception.csi_score import score_csi
        from .perception.eye_gaze import score_eye_gaze
        from .perception.face_symmetry import score_face_symmetry
        from .perception.speech_cnn import SpeechScoreStabilizer, score_speech
        from .perception.tongue_deviation import score_tongue_deviation
        self._score_face = score_face_symmetry
        self._score_speech = score_speech
        self._speech_stabilizer = SpeechScoreStabilizer(retention_seconds=300.0)
        self._score_tongue = score_tongue_deviation
        self._score_eye = score_eye_gaze
        self._score_csi = score_csi

    def _metric_dict(self, score) -> dict:
        return {"score": score.score, "reasons": score.reasons, "raw": score.raw}

    def _mark_face_dependency_unavailable(self, score) -> None:
        reasons = ["face_backend_unavailable", *self._face_unavailable_reasons]
        for reason in reasons:
            if reason and reason not in score.reasons:
                score.reasons.append(reason)
        score.raw.update({
            "face_backend": self._face_backend,
            "backend_reasons": list(self._face_unavailable_reasons),
            "dependency": "face_landmarks",
        })

    def _csi_source_name(self) -> str:
        name = self._source.__class__.__name__
        if name == "SyntheticFrameSource":
            return "synthetic_frame"
        if name == "SimSource":
            return "sim_heartbeat"
        if name == "RealSource":
            return "pc_real"
        return "esp32_csi_monitor"

    def process(self, frame) -> Optional[dict]:
        if frame.type != TYPE_DATA:
            return None
        js = frame.json or {}
        result: dict = {"seq": js.get("seq")}

        # ---- Face landmarks 共享给 F/Tongue/E ----
        fl = None
        jpeg_b64 = js.get("jpeg_b64")
        if self._face_ok and jpeg_b64:
            import cv2
            buf = np.frombuffer(base64.b64decode(jpeg_b64), dtype=np.uint8)
            bgr = cv2.imdecode(buf, cv2.IMREAD_COLOR)
            fl = self._fd.detect(bgr)

        if self._face_ok:
            face_meta = self._face_result_from_facemesh(fl, backend=self._face_backend)
            f = self._score_face(fl)
            f.raw.update(face_meta.raw)
            f.raw["face_backend"] = self._face_backend
            if face_meta.reasons:
                f.reasons.extend(face_meta.reasons)
            result["face"] = {"score": f.score, "reasons": f.reasons, "raw": f.raw}
            t = self._score_tongue(fl)
            result["tongue"] = {"score": t.score, "reasons": t.reasons, "raw": t.raw}
            e = self._score_eye(fl)
            result["eye"] = {"score": e.score, "reasons": e.reasons, "raw": e.raw}
        else:
            f = self._score_face(None)
            t = self._score_tongue(None)
            e = self._score_eye(None)
            for score in (f, t, e):
                self._mark_face_dependency_unavailable(score)
            result["face"] = self._metric_dict(f)
            result["tongue"] = self._metric_dict(t)
            result["eye"] = self._metric_dict(e)

        # ---- S 分 ----
        audio = None
        if hasattr(self._source, "latest_audio"):
            audio = self._source.latest_audio()
        if audio is not None:
            s = self._score_speech(audio)
            stable_score = self._speech_stabilizer.update(
                s.score if s.available else None)
            if stable_score is not None:
                s.score = stable_score
                s.raw["stabilized"] = True
            result["speech"] = {"score": s.score, "reasons": s.reasons, "raw": s.raw}
        else:
            stable_score = self._speech_stabilizer.update(None)
            if stable_score is not None:
                result["speech"] = {
                    "score": stable_score,
                    "reasons": ["speech_retained_last_valid"],
                    "raw": {"stabilized": True, "retention_seconds": 300},
                }

        # ---- B 分 (CSI 透传) ----
        b = self._score_csi(js.get("csi_score"), source=self._csi_source_name())
        result["csi"] = {"score": b.score, "reasons": b.reasons, "raw": b.raw}
        return result


def run(args) -> int:
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )

    profile_path = Path(args.profile)
    if profile_path.exists():
        try:
            profile = load_profile(profile_path)
            log.info("profile loaded: device_id=%s age=%d",
                     profile.device_id, profile.user.age)
            device_id = profile.device_id
        except Exception as e:
            log.error("profile invalid: %s", e)
            return 2
    else:
        log.warning("profile not found (%s), using defaults", profile_path)
        device_id = "sg-0001"

    src = _make_source(args)
    rec = None if args.no_record else FrameRecorder(args.data_dir, device_id)
    pipe: Optional[PerceptionPipeline] = None

    stop = False

    def _sigint(_signo, _frame):
        nonlocal stop
        stop = True
        log.info("SIGINT, stopping...")

    signal.signal(signal.SIGINT, _sigint)

    n = 0
    try:
        src.open()
        if args.perception or args.source == "real":
            pipe = PerceptionPipeline(
                src,
                face_backend=args.face_backend,
                yolo_weights=args.yolo_weights,
            )
        if rec:
            rec.open()
        for frame in src.frames():
            if stop:
                break
            js = frame.json or {}
            log_line = (
                f"[#{n}] {frame.type_name} csi={js.get('csi_score')} "
                f"ts={js.get('ts')}"
            )
            if pipe is not None:
                res = pipe.process(frame)
                if res:
                    for k in ("face", "speech", "tongue", "eye", "csi"):
                        m = res.get(k)
                        if not m:
                            continue
                        tag = {"face": "F", "speech": "S", "tongue": "T",
                               "eye": "E", "csi": "B"}[k]
                        log_line += f"  {tag}={m['score']}"
                        if m["reasons"]:
                            log_line += f"({';'.join(m['reasons'])})"
            log.info(log_line)
            if rec:
                rec.write(frame)
            n += 1
            if args.max_frames and n >= args.max_frames:
                break
    except KeyboardInterrupt:
        pass
    finally:
        if rec:
            rec.close()
        src.close()

    log.info("done, frames=%d", n)
    if args.source == "cdc":
        r: CdcReader = src  # type: ignore
        log.info("cdc stats: ok=%d crc_err=%d resync=%d",
                 r.n_ok, r.n_crc_err, r.n_resync)
    return 0


def cli() -> None:
    args = _build_argparser().parse_args()
    sys.exit(run(args))


if __name__ == "__main__":
    cli()
