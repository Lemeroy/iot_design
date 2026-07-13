"""Authenticated client for the read-only StrokeGuard VPS demo API."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import httpx


class DemoCloudError(RuntimeError):
    """Base class for user-visible cloud client failures."""


class CloudUnavailable(DemoCloudError):
    """The VPS cannot be reached or its monitor service is unavailable."""


class AuthenticationRequired(DemoCloudError):
    """Credentials are invalid or the current session has expired."""


class DeviceOffline(DemoCloudError):
    """The requested device is unknown or has no recent uplink."""


class InvalidCloudResponse(DemoCloudError):
    """The VPS returned a payload outside the agreed demo contract."""


@dataclass(frozen=True)
class ScoreSnapshot:
    face: int | None
    speech: int | None
    tongue: int | None
    eye: int | None
    csi: int | None
    final: int


@dataclass(frozen=True)
class AdviceSnapshot:
    advice_text: str
    source: str
    ts: int


@dataclass(frozen=True)
class DeviceSnapshot:
    device_id: str
    online: bool
    received_at: float | None
    scores: ScoreSnapshot | None
    level: str | None
    reasons: tuple[str, ...]
    veto_by: tuple[str, ...]
    advice: AdviceSnapshot | None


class CloudClient:
    """Small synchronous API used from a Qt worker thread."""

    def __init__(
        self,
        base_url: str,
        timeout_seconds: float = 5.0,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        base_url = base_url.strip().rstrip("/")
        if not base_url:
            raise ValueError("base_url is required")
        self._client = httpx.Client(
            base_url=base_url,
            timeout=timeout_seconds,
            transport=transport,
            headers={"accept": "application/json"},
        )

    def close(self) -> None:
        self._client.close()

    def login(self, username: str, password: str) -> None:
        self._request(
            "POST",
            "/demo/api/login",
            json={"username": username, "password": password},
        )

    def connect(self, device_id: str) -> None:
        response = self._request(
            "POST", "/demo/api/connect", json={"device_id": device_id}
        )
        if response.status_code in (404, 409):
            raise DeviceOffline("设备离线")
        self._raise_for_status(response)

    def fetch_device(self) -> DeviceSnapshot:
        response = self._request("GET", "/demo/api/device")
        self._raise_for_status(response)
        body = self._json_object(response)
        try:
            scores = self._parse_scores(body.get("scores"))
            advice = self._parse_advice(body.get("advice"))
            return DeviceSnapshot(
                device_id=self._required_str(body, "device_id"),
                online=self._required_bool(body, "online"),
                received_at=self._optional_number(body.get("received_at")),
                scores=scores,
                level=self._optional_str(body.get("level")),
                reasons=self._string_tuple(body.get("reasons", [])),
                veto_by=self._string_tuple(body.get("veto_by", [])),
                advice=advice,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise InvalidCloudResponse("invalid device payload") from exc

    def logout(self) -> None:
        response = self._request("POST", "/demo/api/logout")
        self._raise_for_status(response)

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        try:
            response = self._client.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise CloudUnavailable("云端不可达") from exc
        if response.status_code == 401:
            raise AuthenticationRequired("登录失效")
        if response.status_code == 503:
            raise CloudUnavailable("云端不可达")
        return response

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise InvalidCloudResponse(
                f"unexpected cloud status {response.status_code}"
            ) from exc

    @staticmethod
    def _json_object(response: httpx.Response) -> Mapping[str, Any]:
        try:
            body = response.json()
        except ValueError as exc:
            raise InvalidCloudResponse("cloud response is not JSON") from exc
        if not isinstance(body, dict):
            raise InvalidCloudResponse("cloud response is not an object")
        return body

    @classmethod
    def _parse_scores(cls, value: Any) -> ScoreSnapshot | None:
        if value is None:
            return None
        if not isinstance(value, dict):
            raise TypeError("scores must be an object")
        return ScoreSnapshot(
            face=cls._optional_score(value.get("face")),
            speech=cls._optional_score(value.get("speech")),
            tongue=cls._optional_score(value.get("tongue")),
            eye=cls._optional_score(value.get("eye")),
            csi=cls._optional_score(value.get("csi")),
            final=cls._required_score(value, "final"),
        )

    @classmethod
    def _parse_advice(cls, value: Any) -> AdviceSnapshot | None:
        if value is None:
            return None
        if not isinstance(value, dict):
            raise TypeError("advice must be an object")
        ts = value.get("ts")
        if isinstance(ts, bool) or not isinstance(ts, int):
            raise TypeError("advice ts must be an integer")
        return AdviceSnapshot(
            advice_text=cls._required_str(value, "advice_text"),
            source=cls._required_str(value, "source"),
            ts=ts,
        )

    @staticmethod
    def _required_str(value: Mapping[str, Any], key: str) -> str:
        item = value[key]
        if not isinstance(item, str):
            raise TypeError(f"{key} must be a string")
        return item

    @staticmethod
    def _optional_str(value: Any) -> str | None:
        if value is None or isinstance(value, str):
            return value
        raise TypeError("value must be a string or null")

    @staticmethod
    def _required_bool(value: Mapping[str, Any], key: str) -> bool:
        item = value[key]
        if not isinstance(item, bool):
            raise TypeError(f"{key} must be a boolean")
        return item

    @staticmethod
    def _optional_number(value: Any) -> float | None:
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError("value must be numeric or null")
        return float(value)

    @staticmethod
    def _optional_score(value: Any) -> int | None:
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 100:
            raise ValueError("score must be 0..100 or null")
        return value

    @classmethod
    def _required_score(cls, value: Mapping[str, Any], key: str) -> int:
        score = cls._optional_score(value[key])
        if score is None:
            raise ValueError(f"{key} cannot be null")
        return score

    @staticmethod
    def _string_tuple(value: Any) -> tuple[str, ...]:
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise TypeError("value must be a string list")
        return tuple(value)
