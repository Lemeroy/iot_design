"""Face backend selection for M2.

The project target is YOLOv8 face detection + 68-point landmarks. In the
current no-weights environment, this module makes that explicit:
  - auto mode falls back to MediaPipe when YOLO weights are absent
  - forced yolo mode reports unavailable instead of pretending to run
  - MediaPipe FaceMesh outputs a dlib-compatible 68-point view
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Optional

import numpy as np

from .face_detect import FaceLandmarks
from .landmark68 import mesh468_to_68

FaceBackendName = Literal["auto", "mediapipe", "yolo"]
ResolvedBackend = Literal["mediapipe", "yolo", "unavailable"]


@dataclass(frozen=True)
class FaceBackendConfig:
    backend: FaceBackendName = "auto"
    yolo_weights: Optional[Path] = None


@dataclass(frozen=True)
class FaceBackendSelection:
    backend: ResolvedBackend
    reasons: list[str] = field(default_factory=list)


@dataclass
class FaceBackendResult:
    backend: str
    landmarks: Optional[FaceLandmarks] = None
    landmarks68: Optional[np.ndarray] = None
    reasons: list[str] = field(default_factory=list)
    raw: dict = field(default_factory=dict)

    @property
    def available(self) -> bool:
        return self.landmarks is not None


def _has_yolo_weights(path: Optional[Path]) -> bool:
    return bool(path and Path(path).exists())


def resolve_face_backend(config: FaceBackendConfig) -> FaceBackendSelection:
    """Resolve requested face backend without importing heavy optional deps."""
    if config.backend == "mediapipe":
        return FaceBackendSelection(backend="mediapipe")

    if config.backend == "yolo":
        if not _has_yolo_weights(config.yolo_weights):
            return FaceBackendSelection(
                backend="unavailable",
                reasons=["yolo_weights_missing"],
            )
        return FaceBackendSelection(backend="yolo")

    # auto: prefer YOLO only when weights are explicitly available.
    if _has_yolo_weights(config.yolo_weights):
        return FaceBackendSelection(backend="yolo")
    return FaceBackendSelection(
        backend="mediapipe",
        reasons=["yolo_weights_missing"],
    )


def result_from_facemesh(fl: Optional[FaceLandmarks],
                         backend: str = "mediapipe") -> FaceBackendResult:
    if fl is None:
        return FaceBackendResult(
            backend=backend,
            landmarks=None,
            landmarks68=None,
            reasons=["no_face"],
            raw={},
        )
    lm68 = mesh468_to_68(fl.landmarks)
    return FaceBackendResult(
        backend=backend,
        landmarks=fl,
        landmarks68=lm68,
        reasons=[],
        raw={
            "landmarks_count": int(fl.landmarks.shape[0]),
            "landmarks68_count": int(lm68.shape[0]),
        },
    )
