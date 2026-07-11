"""mediapipe FaceMesh 检测封装.

兼容两套 mediapipe API:
  - legacy: mp.solutions.face_mesh.FaceMesh (mediapipe <= 0.10.14 for Py<=3.12)
  - tasks:  mediapipe.tasks.python.vision.FaceLandmarker (mediapipe 0.10.14+, Py>=3.13)

Tasks 版需要下载 face_landmarker.task, 首次运行自动缓存到
LOCALAPPDATA/StrokeGuard/mediapipe_models/ (或 ~/.cache/StrokeGuard/...).
"""
from __future__ import annotations

import logging
import os
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np

log = logging.getLogger(__name__)

# 关键点索引 (mediapipe FaceMesh 468 点体系; refine_landmarks=True 时 478 点含虹膜)
IDX = {
    "mouth_left":   61,
    "mouth_right":  291,
    "lip_top":      13,
    "lip_bottom":   14,
    "eye_left_out":  33,
    "eye_right_out": 263,
    "eye_left_in":   133,
    "eye_right_in":  362,
    "eye_left_top":     159,
    "eye_left_bot":     145,
    "eye_right_top":    386,
    "eye_right_bot":    374,
    "nose_tip":      1,
    "nose_bridge":   168,
    "chin":          152,
    "cheek_left":    234,
    "cheek_right":   454,
    "lip_inner_bot": 17,
}

IRIS_IDX = {
    "iris_left_center":  468,
    "iris_left_top":     470,
    "iris_left_bot":     472,
    "iris_left_out":     471,
    "iris_left_in":      469,
    "iris_right_center": 473,
    "iris_right_top":    475,
    "iris_right_bot":    477,
    "iris_right_out":    474,
    "iris_right_in":     476,
}

# 官方 tasks 模型 URL
_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
    "face_landmarker/float16/1/face_landmarker.task"
)


def _model_cache_path() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~/.cache")
    d = Path(base) / "StrokeGuard" / "mediapipe_models"
    d.mkdir(parents=True, exist_ok=True)
    return d / "face_landmarker.task"


def _ensure_model() -> Path:
    p = _model_cache_path()
    if p.exists() and p.stat().st_size > 1_000_000:
        return p
    log.info("downloading mediapipe face_landmarker.task -> %s", p)
    tmp = p.with_suffix(".tmp")
    urllib.request.urlretrieve(_MODEL_URL, tmp)
    tmp.replace(p)
    log.info("model ready: %d bytes", p.stat().st_size)
    return p


@dataclass
class FaceLandmarks:
    landmarks: np.ndarray
    image_w: int
    image_h: int

    def pt(self, name: str) -> np.ndarray:
        if name in IRIS_IDX:
            idx = IRIS_IDX[name]
        else:
            idx = IDX[name]
        return self.landmarks[idx, :2].astype(np.float32)

    def has_iris(self) -> bool:
        return self.landmarks.shape[0] >= 478


class FaceMeshDetector:
    """mediapipe FaceMesh 单实例封装."""

    def __init__(self,
                 max_num_faces: int = 1,
                 min_detection_confidence: float = 0.5,
                 min_tracking_confidence: float = 0.5,
                 static_image_mode: bool = False,
                 refine_landmarks: bool = True) -> None:
        try:
            import mediapipe as mp
        except ImportError as e:
            raise ImportError(
                "mediapipe not installed. Run: pip install mediapipe"
            ) from e

        self._mp = mp
        self._backend = None
        self._legacy_mesh = None
        self._tasks_lm = None

        # 优先尝试 legacy API (Py<=3.12 环境)
        legacy_ok = hasattr(mp, "solutions") and hasattr(mp.solutions, "face_mesh")
        if legacy_ok:
            self._legacy_mesh = mp.solutions.face_mesh.FaceMesh(
                static_image_mode=static_image_mode,
                max_num_faces=max_num_faces,
                refine_landmarks=refine_landmarks,
                min_detection_confidence=min_detection_confidence,
                min_tracking_confidence=min_tracking_confidence,
            )
            self._backend = "legacy"
            log.info("FaceMesh backend: legacy mp.solutions.face_mesh")
        else:
            # Tasks API
            from mediapipe.tasks import python as mp_python
            from mediapipe.tasks.python import vision as mp_vision
            model_path = _ensure_model()
            running_mode = (
                mp_vision.RunningMode.IMAGE
                if static_image_mode
                else mp_vision.RunningMode.VIDEO
            )
            options = mp_vision.FaceLandmarkerOptions(
                base_options=mp_python.BaseOptions(
                    model_asset_path=str(model_path)
                ),
                running_mode=running_mode,
                num_faces=max_num_faces,
                min_face_detection_confidence=min_detection_confidence,
                min_face_presence_confidence=min_detection_confidence,
                min_tracking_confidence=min_tracking_confidence,
                output_face_blendshapes=False,
                output_facial_transformation_matrixes=False,
            )
            self._tasks_lm = mp_vision.FaceLandmarker.create_from_options(options)
            self._tasks_running_mode = running_mode
            self._mp_vision = mp_vision
            self._backend = "tasks"
            self._video_ts_ms = 0
            log.info("FaceMesh backend: tasks FaceLandmarker (model=%s)", model_path.name)

    def detect(self, bgr: np.ndarray) -> Optional[FaceLandmarks]:
        if bgr is None or bgr.size == 0:
            return None
        import cv2
        h, w = bgr.shape[:2]
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)

        if self._backend == "legacy":
            res = self._legacy_mesh.process(rgb)
            if not res.multi_face_landmarks:
                return None
            lm = res.multi_face_landmarks[0].landmark
            arr = np.array(
                [[p.x * w, p.y * h, p.z * w] for p in lm],
                dtype=np.float32,
            )
            return FaceLandmarks(landmarks=arr, image_w=w, image_h=h)

        # tasks
        mp_image = self._mp.Image(
            image_format=self._mp.ImageFormat.SRGB, data=rgb
        )
        if self._tasks_running_mode == self._mp_vision.RunningMode.VIDEO:
            self._video_ts_ms += 33  # 假设 30fps 单调时间戳
            result = self._tasks_lm.detect_for_video(mp_image, self._video_ts_ms)
        else:
            result = self._tasks_lm.detect(mp_image)

        if not result.face_landmarks:
            return None
        lm = result.face_landmarks[0]
        arr = np.array(
            [[p.x * w, p.y * h, p.z * w] for p in lm],
            dtype=np.float32,
        )
        return FaceLandmarks(landmarks=arr, image_w=w, image_h=h)

    def close(self) -> None:
        if self._legacy_mesh is not None:
            try:
                self._legacy_mesh.close()
            except Exception:
                pass
        if self._tasks_lm is not None:
            try:
                self._tasks_lm.close()
            except Exception:
                pass

    def __enter__(self) -> "FaceMeshDetector":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
