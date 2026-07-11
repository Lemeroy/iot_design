"""云端数据契约 (与 host_pc uplink / downlink 完全对齐)."""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

LevelT = Literal["normal", "warning", "danger", "insufficient"]


class Scores(BaseModel):
    face: Optional[int] = None
    speech: Optional[int] = None
    tongue: Optional[int] = None
    eye: Optional[int] = None
    csi: Optional[int] = None
    final: int = 0


class Profile(BaseModel):
    age: int = Field(ge=0, le=130)
    gender: Literal["M", "F", "other"] = "other"
    conditions: List[str] = []
    meds: List[str] = []
    stroke_history: bool = False


class UplinkPayload(BaseModel):
    """上位机 -> 云端 (topic: strokeguard/<device>/uplink)."""
    scores: Scores
    level: LevelT
    reasons: List[str] = []
    veto_by: List[str] = []
    profile: Profile
    device_id: str
    ts: int


class DownlinkPayload(BaseModel):
    """云端 -> 设备 (topic: strokeguard/<device>/downlink)."""
    level: LevelT
    advice_text: str
    ts: int
    source: str = "doubao-lite"


class HealthResp(BaseModel):
    status: str
    mqtt: bool
    influx: bool
    llm: bool


class LatestResp(BaseModel):
    device_id: str
    last_uplink_ts: Optional[int] = None
    last_advice: Optional[DownlinkPayload] = None
    latest_scores: Optional[Scores] = None
    latest_level: Optional[LevelT] = None


class ManualAdviceReq(BaseModel):
    """开发/演示: 手动触发一次 LLM 建议 (不经过 MQTT)."""
    scores: Scores
    level: LevelT
    profile: Profile
    reasons: List[str] = []


class ManualAdviceResp(BaseModel):
    advice_text: str
    latency_ms: int
    model: str
