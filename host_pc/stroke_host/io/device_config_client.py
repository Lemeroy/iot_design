"""Authenticated, LAN-only client for the mirror profile API."""
from __future__ import annotations

import ipaddress
import json
import re
import socket
from typing import Literal
import urllib.error
import urllib.request

import keyring
from keyring.errors import KeyringError
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ..config.profile_loader import DeviceEndpoint, Thresholds, UserProfile


KEYRING_SERVICE = "StrokeGuard Manager"
MAX_RESPONSE_BYTES = 64 * 1024
DEVICE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,32}$")


class DeviceConfigError(RuntimeError):
    """Bounded UI-safe device management failure."""

    def __init__(
        self, kind: str, message: str, current: dict | None = None
    ) -> None:
        super().__init__(message[:160])
        self.kind = kind
        self.current = current


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DeviceConfigResponse(_StrictModel):
    schema_version: Literal[1]
    revision: int = Field(ge=1, le=2**32 - 1)
    device_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,32}$")
    profile: UserProfile
    readonly: Thresholds
    capabilities: list[Literal["profile_write"]] = Field(max_length=4)


def save_manager_token(device_id: str, token: str) -> None:
    if not DEVICE_ID_RE.fullmatch(device_id):
        raise ValueError("invalid device ID")
    if not token or len(token) > 64 or any(ord(char) < 33 for char in token):
        raise ValueError("management token must contain 1..64 visible characters")
    try:
        keyring.set_password(KEYRING_SERVICE, device_id, token)
    except KeyringError as exc:
        raise OSError("system credential store unavailable") from exc


class DeviceConfigClient:
    def __init__(
        self,
        device_id: str,
        endpoint: DeviceEndpoint,
        timeout: float = 2.0,
    ) -> None:
        if not DEVICE_ID_RE.fullmatch(device_id):
            raise ValueError("invalid device ID")
        if not endpoint.host:
            raise ValueError("management host is required")
        if timeout <= 0 or timeout > 30:
            raise ValueError("timeout must be in (0, 30]")
        self.device_id = device_id
        self.endpoint = endpoint
        self.timeout = timeout
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def set_token(self, token: str) -> None:
        save_manager_token(self.device_id, token)

    def _token(self) -> str:
        try:
            token = keyring.get_password(KEYRING_SERVICE, self.device_id)
        except KeyringError as exc:
            raise DeviceConfigError("keyring", "系统凭据库不可用") from exc
        if not token:
            raise DeviceConfigError("missing_token", "尚未设置镜端管理密钥")
        if len(token) > 64 or any(ord(char) < 33 for char in token):
            raise DeviceConfigError("missing_token", "镜端管理密钥无效，请重新设置")
        return token

    def _verify_private_resolution(self) -> None:
        try:
            results = socket.getaddrinfo(
                self.endpoint.host,
                self.endpoint.port,
                type=socket.SOCK_STREAM,
            )
        except OSError as exc:
            raise DeviceConfigError("network", "无法解析镜端局域网地址") from exc
        if not results:
            raise DeviceConfigError("network", "无法解析镜端局域网地址")
        for result in results:
            try:
                address = ipaddress.ip_address(result[4][0])
            except ValueError as exc:
                raise DeviceConfigError("endpoint", "镜端地址解析结果无效") from exc
            if not (
                address.is_private
                or address.is_link_local
                or address.is_loopback
            ):
                raise DeviceConfigError("endpoint", "拒绝连接公网管理地址")

    def _url(self) -> str:
        host = self.endpoint.host
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        return f"http://{host}:{self.endpoint.port}/api/v1/config"

    def _request(self, method: str, payload: dict | None = None) -> DeviceConfigResponse:
        token = self._token()
        self._verify_private_resolution()
        data = None
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
        }
        if payload is not None:
            data = json.dumps(
                payload, ensure_ascii=False, separators=(",", ":")
            ).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            self._url(), data=data, headers=headers, method=method
        )
        try:
            with self._opener.open(request, timeout=self.timeout) as response:
                raw = response.read(MAX_RESPONSE_BYTES + 1)
        except urllib.error.HTTPError as exc:
            if exc.code == 401:
                raise DeviceConfigError("auth", "镜端管理密钥不正确") from exc
            if exc.code == 409:
                raise DeviceConfigError("conflict", "镜端配置已被其他操作更新") from exc
            if exc.code in (413, 415, 422):
                raise DeviceConfigError("validation", "镜端拒绝了配置内容") from exc
            raise DeviceConfigError("server", "镜端管理服务返回错误") from exc
        except (OSError, TimeoutError, urllib.error.URLError) as exc:
            raise DeviceConfigError("network", "无法连接镜端，请检查局域网与地址") from exc
        if len(raw) > MAX_RESPONSE_BYTES:
            raise DeviceConfigError("response", "镜端响应超过大小限制")
        try:
            decoded = json.loads(raw.decode("utf-8"))
            parsed = DeviceConfigResponse.model_validate(decoded)
        except (UnicodeError, json.JSONDecodeError, ValidationError) as exc:
            raise DeviceConfigError("response", "镜端响应格式无效") from exc
        if parsed.device_id != self.device_id:
            raise DeviceConfigError("device_mismatch", "镜端设备 ID 与本地配置不一致")
        return parsed

    def get_config(self) -> DeviceConfigResponse:
        return self._request("GET")

    def put_profile(
        self, profile: UserProfile, expected_revision: int
    ) -> DeviceConfigResponse:
        if expected_revision < 1 or expected_revision > 2**32 - 1:
            raise ValueError("expected_revision is out of range")
        return self._request(
            "PUT",
            {
                "schema_version": 1,
                "expected_revision": expected_revision,
                "profile": profile.model_dump(mode="json"),
            },
        )
