"""云端数据契约 (与 host_pc uplink / downlink 完全对齐)."""
from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

LevelT = Literal["normal", "warning", "danger", "insufficient"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Scores(StrictModel):
    face: Optional[int] = None
    speech: Optional[int] = None
    tongue: Optional[int] = None
    eye: Optional[int] = None
    csi: Optional[int] = None
    final: int = 0


class Profile(StrictModel):
    age: int = Field(ge=0, le=130)
    gender: Literal["M", "F", "other"] = "other"
    conditions: List[str] = Field(default_factory=list)
    meds: List[str] = Field(default_factory=list)
    stroke_history: bool = False


class UplinkPayload(StrictModel):
    """上位机 -> 云端 (topic: strokeguard/<device>/uplink)."""
    schema_version: Literal[1] = 1
    seq: int = Field(default=0, ge=0)
    scores: Scores
    level: LevelT
    reasons: List[str] = Field(default_factory=list)
    veto_by: List[str] = Field(default_factory=list)
    profile: Profile
    device_id: str
    ts: int


class DownlinkPayload(StrictModel):
    """云端 -> 设备 (topic: strokeguard/<device>/downlink)."""
    schema_version: Literal[1] = 1
    level: LevelT
    advice_text: str
    ts: int
    source: str = "doubao-lite"


class HealthResp(StrictModel):
    status: str
    mqtt: bool
    influx: bool
    llm: bool


class LatestResp(StrictModel):
    device_id: str
    last_uplink_ts: Optional[int] = None
    last_advice: Optional[DownlinkPayload] = None
    latest_scores: Optional[Scores] = None
    latest_level: Optional[LevelT] = None


class ManualAdviceReq(StrictModel):
    """开发/演示: 手动触发一次 LLM 建议 (不经过 MQTT)."""
    scores: Scores
    level: LevelT
    profile: Profile
    reasons: List[str] = Field(default_factory=list)


class ManualAdviceResp(StrictModel):
    advice_text: str
    latency_ms: int
    model: str
