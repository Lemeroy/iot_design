"""Strict, credential-aware deployment YAML contract."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse

import yaml


DEVICE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,32}$")
ENV_RE = re.compile(r"^\$\{([A-Z][A-Z0-9_]*)\}$")
RESERVED_N16R8_GPIOS = frozenset({19, 20, *range(26, 38)})
CAMERA_PINS = ("sda", "scl")
MICROPHONE_PINS = ("sck", "ws", "sd")


class DeploymentValidationError(ValueError):
    """The local deployment file cannot safely produce firmware config."""


@dataclass(frozen=True)
class WifiConfig:
    ssid: str
    password: str


@dataclass(frozen=True)
class MqttConfig:
    uri: str
    username: str
    password: str


@dataclass(frozen=True)
class CameraConfig:
    model: str
    enabled: bool
    transport: str
    address: int
    pins: Mapping[str, int]


@dataclass(frozen=True)
class MicrophoneConfig:
    model: str
    enabled: bool
    sample_rate: int
    channel: str
    pins: Mapping[str, int]


@dataclass(frozen=True)
class DeploymentConfig:
    device_id: str
    management_token: str
    wifi: WifiConfig
    mqtt: MqttConfig
    camera: CameraConfig
    microphone: MicrophoneConfig

    @property
    def secrets(self) -> tuple[str, ...]:
        values = (
            self.management_token,
            self.wifi.password,
            self.mqtt.username,
            self.mqtt.password,
        )
        return tuple(dict.fromkeys(value for value in values if value))

    @property
    def kconfig(self) -> dict[str, str]:
        result = {
            "CONFIG_STROKEGUARD_DEVICE_ID": _kconfig_string(self.device_id),
            "CONFIG_STROKEGUARD_WIFI_SSID": _kconfig_string(self.wifi.ssid),
            "CONFIG_STROKEGUARD_WIFI_PASSWORD": _kconfig_string(self.wifi.password),
            "CONFIG_STROKEGUARD_MQTT_URI": _kconfig_string(self.mqtt.uri),
            "CONFIG_STROKEGUARD_MQTT_USERNAME": _kconfig_string(self.mqtt.username),
            "CONFIG_STROKEGUARD_MQTT_PASSWORD": _kconfig_string(self.mqtt.password),
            "CONFIG_STROKEGUARD_MANAGER_TOKEN": _kconfig_string(self.management_token),
            "CONFIG_STROKEGUARD_CAMERA_COPROCESSOR_ENABLE": "y" if self.camera.enabled else "n",
            "CONFIG_STROKEGUARD_CAMERA_I2C_ADDRESS": str(self.camera.address),
            "CONFIG_STROKEGUARD_NMO432_ENABLE": "y" if self.microphone.enabled else "n",
        }
        for name in CAMERA_PINS:
            result[f"CONFIG_STROKEGUARD_CAMERA_I2C_{name.upper()}"] = str(
                self.camera.pins.get(name, -1)
            )
        microphone_keys = {"sck": "BCLK", "ws": "WS", "sd": "DIN"}
        for name, suffix in microphone_keys.items():
            result[f"CONFIG_STROKEGUARD_NMO432_{suffix}"] = str(
                self.microphone.pins.get(name, -1)
            )
        result["CONFIG_STROKEGUARD_NMO432_CHANNEL_LEFT"] = (
            "y" if self.microphone.channel == "left" else "n"
        )
        return result


def load_deployment(path: Path, environ: Mapping[str, str]) -> DeploymentConfig:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise DeploymentValidationError(f"cannot read deployment YAML: {exc}") from exc
    return validate_deployment(raw, environ)


def validate_deployment(data: object, environ: Mapping[str, str]) -> DeploymentConfig:
    root = _object(data, "root")
    _keys(root, {"schema_version", "device", "wifi", "mqtt", "hardware"}, "root")
    if root.get("schema_version") != 1:
        raise DeploymentValidationError("schema_version must be 1")

    device = _object(root.get("device"), "device")
    _keys(device, {"id", "management_token"}, "device")
    device_id = _text(device.get("id"), "device.id")
    if not DEVICE_ID_RE.fullmatch(device_id):
        raise DeploymentValidationError("device.id must match [A-Za-z0-9_-]{1,32}")
    management_token = _resolve(device.get("management_token"), "device.management_token", environ)

    wifi_data = _object(root.get("wifi"), "wifi")
    _keys(wifi_data, {"ssid", "password"}, "wifi")
    ssid = _resolve(wifi_data.get("ssid"), "wifi.ssid", environ)
    password = _resolve(wifi_data.get("password"), "wifi.password", environ)
    if len(ssid.encode("utf-8")) > 32:
        raise DeploymentValidationError("wifi.ssid exceeds 32 bytes")

    mqtt_data = _object(root.get("mqtt"), "mqtt")
    _keys(mqtt_data, {"uri", "username", "password"}, "mqtt")
    uri = _resolve(mqtt_data.get("uri"), "mqtt.uri", environ)
    parsed = urlparse(uri)
    if parsed.scheme not in {"mqtt", "mqtts"} or not parsed.hostname:
        raise DeploymentValidationError("mqtt.uri must use mqtt:// or mqtts://")
    username = _resolve(mqtt_data.get("username"), "mqtt.username", environ)
    mqtt_password = _resolve(mqtt_data.get("password"), "mqtt.password", environ)

    hardware = _object(root.get("hardware"), "hardware")
    _keys(hardware, {"camera", "microphone"}, "hardware")
    camera = _camera(hardware.get("camera"))
    microphone = _microphone(hardware.get("microphone"))
    _validate_gpios(camera, microphone)

    return DeploymentConfig(
        device_id=device_id,
        management_token=management_token,
        wifi=WifiConfig(ssid=ssid, password=password),
        mqtt=MqttConfig(uri=uri, username=username, password=mqtt_password),
        camera=camera,
        microphone=microphone,
    )


def redact_text(text: str, config: DeploymentConfig) -> str:
    result = text
    for secret in sorted(config.secrets, key=len, reverse=True):
        result = result.replace(secret, "***")
    return result


def _camera(value: Any) -> CameraConfig:
    data = _object(value, "hardware.camera")
    _keys(
        data,
        {"model", "enabled", "transport", "address", "pins"},
        "hardware.camera",
    )
    if data.get("model") != "ESP32-S3-Cam":
        raise DeploymentValidationError("camera model must be ESP32-S3-Cam")
    enabled = _boolean(data.get("enabled"), "hardware.camera.enabled")
    transport = _text(data.get("transport"), "hardware.camera.transport")
    if transport != "i2c":
        raise DeploymentValidationError("camera.transport must be i2c")
    address = data.get("address")
    if isinstance(address, bool) or not isinstance(address, int) or not 0x08 <= address <= 0x77:
        raise DeploymentValidationError("camera.address must be an I2C address from 8 to 119")
    pins = _pins(data.get("pins"), "camera.pins", CAMERA_PINS, enabled)
    return CameraConfig(
        model="ESP32-S3-Cam",
        enabled=enabled,
        transport=transport,
        address=address,
        pins=pins,
    )


def _microphone(value: Any) -> MicrophoneConfig:
    data = _object(value, "hardware.microphone")
    _keys(
        data,
        {"model", "enabled", "sample_rate", "channel", "pins"},
        "hardware.microphone",
    )
    if data.get("model") != "NMO432":
        raise DeploymentValidationError("microphone model must be NMO432")
    enabled = _boolean(data.get("enabled"), "hardware.microphone.enabled")
    if data.get("sample_rate") != 16000:
        raise DeploymentValidationError("microphone.sample_rate must be 16000")
    channel = _text(data.get("channel"), "microphone.channel")
    if channel not in {"left", "right"}:
        raise DeploymentValidationError("microphone.channel must be left or right")
    pins = _pins(data.get("pins"), "microphone.pins", MICROPHONE_PINS, enabled)
    return MicrophoneConfig(
        model="NMO432",
        enabled=enabled,
        sample_rate=16000,
        channel=channel,
        pins=pins,
    )


def _pins(value: Any, path: str, required: tuple[str, ...], enabled: bool) -> dict[str, int]:
    data = _object(value, path)
    unknown = sorted(set(data) - set(required))
    if unknown:
        raise DeploymentValidationError(f"unknown field {path}.{unknown[0]}")
    if enabled:
        missing = [name for name in required if name not in data]
        if missing:
            raise DeploymentValidationError(f"{path} missing {', '.join(missing)}")
    elif data:
        raise DeploymentValidationError(f"{path} must be empty while disabled")
    result: dict[str, int] = {}
    for name, pin in data.items():
        if isinstance(pin, bool) or not isinstance(pin, int):
            raise DeploymentValidationError(f"{path}.{name} GPIO must be an integer")
        result[name] = pin
    return result


def _validate_gpios(camera: CameraConfig, microphone: MicrophoneConfig) -> None:
    used: dict[int, str] = {}
    groups = []
    if camera.enabled:
        groups.append(("camera", camera.pins))
    if microphone.enabled:
        groups.append(("microphone", microphone.pins))
    for group, pins in groups:
        for name, pin in pins.items():
            if not 0 <= pin <= 48:
                raise DeploymentValidationError(f"{group}.{name} GPIO {pin} is out of range")
            if pin in RESERVED_N16R8_GPIOS:
                raise DeploymentValidationError(f"{group}.{name} GPIO {pin} is reserved")
            if pin in used:
                raise DeploymentValidationError(
                    f"duplicate GPIO {pin}: {used[pin]} and {group}.{name}"
                )
            used[pin] = f"{group}.{name}"


def _object(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise DeploymentValidationError(f"{path} must be an object")
    return value


def _keys(data: Mapping[str, Any], allowed: set[str], path: str) -> None:
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise DeploymentValidationError(f"unknown field {path}.{unknown[0]}")
    missing = sorted(allowed - set(data))
    if missing:
        raise DeploymentValidationError(f"missing field {path}.{missing[0]}")


def _text(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value:
        raise DeploymentValidationError(f"{path} must be a non-empty string")
    return value


def _boolean(value: Any, path: str) -> bool:
    if not isinstance(value, bool):
        raise DeploymentValidationError(f"{path} must be boolean")
    return value


def _resolve(value: Any, path: str, environ: Mapping[str, str]) -> str:
    text = _text(value, path)
    match = ENV_RE.fullmatch(text)
    if not match:
        return text
    name = match.group(1)
    resolved = environ.get(name)
    if not resolved:
        raise DeploymentValidationError(f"environment variable {name} is required")
    return resolved


def _kconfig_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'
