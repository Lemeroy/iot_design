"""Strict, versioned local profile YAML loading."""
from __future__ import annotations

import ipaddress
from pathlib import Path
import re
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from pydantic import field_validator, model_validator


MAX_YAML_BYTES = 64 * 1024
DEVICE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,32}$")
RELEASE_THRESHOLDS = {
    "face_danger": 30,
    "mouth_angle_danger_deg": 20,
    "speech_danger": 35,
}


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DeviceEndpoint(StrictModel):
    host: str = ""
    port: int = Field(default=80, ge=1, le=65535)

    @field_validator("host")
    @classmethod
    def validate_host(cls, value: str) -> str:
        value = value.strip()
        if not value:
            return value
        try:
            address = ipaddress.ip_address(value)
        except ValueError:
            if value.lower().endswith(".local") and len(value) <= 253:
                return value
            raise ValueError("management host must be a private address or .local name")
        if not (address.is_private or address.is_link_local or address.is_loopback):
            raise ValueError("management host must be private or link-local")
        return value


def _validate_profile_item(value: str) -> str:
    value = value.strip()
    if not value or len(value) > 31:
        raise ValueError("profile items must contain 1..31 characters")
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValueError("profile items cannot contain control characters")
    return value


class UserProfile(StrictModel):
    age: int = Field(ge=0, le=130)
    gender: Literal["M", "F", "other"]
    conditions: list[str] = Field(default_factory=list, max_length=4)
    meds: list[str] = Field(default_factory=list, max_length=4)
    stroke_history: bool = False

    @field_validator("conditions", "meds")
    @classmethod
    def validate_items(cls, values: list[str]) -> list[str]:
        return [_validate_profile_item(value) for value in values]


class Thresholds(StrictModel):
    face_danger: int = 30
    mouth_angle_danger_deg: int = 20
    speech_danger: int = 35

    @model_validator(mode="after")
    def validate_release_values(self) -> "Thresholds":
        if self.model_dump() != RELEASE_THRESHOLDS:
            raise ValueError("medical thresholds are read-only")
        return self


class ProfileFile(StrictModel):
    schema_version: Literal[1] = 1
    device_id: str
    device: DeviceEndpoint = Field(default_factory=DeviceEndpoint)
    user: UserProfile
    thresholds: Thresholds = Field(default_factory=Thresholds)

    @field_validator("device_id")
    @classmethod
    def validate_device_id(cls, value: str) -> str:
        if not DEVICE_ID_RE.fullmatch(value):
            raise ValueError("device_id must match [A-Za-z0-9_-]{1,32}")
        return value


def _migrate(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("profile.yaml root must be a mapping")
    migrated = dict(raw)
    version = migrated.get("schema_version", 0)
    if version == 0:
        migrated["schema_version"] = 1
        migrated.setdefault("device", {})
    elif version != 1:
        raise ValueError(f"unsupported profile schema_version: {version}")
    return migrated


def parse_profile_yaml(text: str) -> ProfileFile:
    if len(text.encode("utf-8")) > MAX_YAML_BYTES:
        raise ValueError("profile YAML exceeds 64 KiB")
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ValueError(f"profile.yaml parse failed: {exc}") from exc
    try:
        return ProfileFile.model_validate(_migrate(raw))
    except ValidationError as exc:
        raise ValueError(f"profile.yaml validation failed:\n{exc}") from exc


def load_profile(path: str | Path) -> ProfileFile:
    profile_path = Path(path)
    if not profile_path.exists():
        raise FileNotFoundError(f"profile not found: {profile_path}")
    return parse_profile_yaml(profile_path.read_text(encoding="utf-8"))
