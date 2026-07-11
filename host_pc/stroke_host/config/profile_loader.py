"""profile.yaml 加载与 pydantic 校验."""
from __future__ import annotations

from pathlib import Path
from typing import List, Literal, Optional

import yaml
from pydantic import BaseModel, Field, ValidationError


class UserProfile(BaseModel):
    age: int = Field(ge=0, le=130)
    gender: Literal["M", "F", "other"]
    conditions: List[str] = []
    meds: List[str] = []
    stroke_history: bool = False


class Thresholds(BaseModel):
    face_danger: int = 30
    mouth_angle_danger_deg: int = 20
    speech_danger: int = 35


class ProfileFile(BaseModel):
    device_id: str
    user: UserProfile
    thresholds: Optional[Thresholds] = None


def load_profile(path: str | Path) -> ProfileFile:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"profile not found: {p}")
    with p.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    try:
        return ProfileFile(**raw)
    except ValidationError as e:
        raise ValueError(f"profile.yaml 校验失败:\n{e}") from e
