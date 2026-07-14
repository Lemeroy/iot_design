from __future__ import annotations

from pathlib import Path

import pytest


BASE_ENV = {
    "STROKEGUARD_MANAGER_TOKEN": "manager-secret",
    "STROKEGUARD_WIFI_SSID": "StrokeLab",
    "STROKEGUARD_WIFI_PASSWORD": "wifi-secret",
    "STROKEGUARD_MQTT_USERNAME": "sg-device",
    "STROKEGUARD_MQTT_PASSWORD": "mqtt-secret",
}


def deployment_data():
    return {
        "schema_version": 1,
        "device": {
            "id": "sg-0002",
            "management_token": "${STROKEGUARD_MANAGER_TOKEN}",
        },
        "wifi": {
            "ssid": "${STROKEGUARD_WIFI_SSID}",
            "password": "${STROKEGUARD_WIFI_PASSWORD}",
        },
        "mqtt": {
            "uri": "mqtt://106.75.229.61:1883",
            "username": "${STROKEGUARD_MQTT_USERNAME}",
            "password": "${STROKEGUARD_MQTT_PASSWORD}",
        },
        "hardware": {
            "camera": {
                "model": "ESP32-S3-Cam",
                "enabled": True,
                "transport": "i2c",
                "address": 0x42,
                "pins": {"sda": 8, "scl": 9},
            },
            "microphone": {
                "model": "NMO432",
                "enabled": True,
                "sample_rate": 16000,
                "channel": "left",
                "pins": {"sck": 17, "ws": 18, "sd": 16},
            },
        },
    }


def test_valid_hardware_config_resolves_environment_and_maps_kconfig():
    from stroke_host.deployment.schema import validate_deployment

    config = validate_deployment(deployment_data(), BASE_ENV)

    assert config.device_id == "sg-0002"
    assert config.wifi.ssid == "StrokeLab"
    assert config.microphone.model == "NMO432"
    assert config.kconfig["CONFIG_STROKEGUARD_DEVICE_ID"] == '"sg-0002"'
    assert config.camera.transport == "i2c"
    assert config.camera.address == 0x42
    assert config.kconfig["CONFIG_STROKEGUARD_CAMERA_COPROCESSOR_ENABLE"] == "y"
    assert config.kconfig["CONFIG_STROKEGUARD_CAMERA_I2C_SDA"] == "8"
    assert config.kconfig["CONFIG_STROKEGUARD_CAMERA_I2C_SCL"] == "9"
    assert config.kconfig["CONFIG_STROKEGUARD_CAMERA_I2C_ADDRESS"] == "66"
    assert config.kconfig["CONFIG_STROKEGUARD_NMO432_ENABLE"] == "y"
    assert "manager-secret" in config.secrets
    assert "wifi-secret" in config.secrets
    assert "mqtt-secret" in config.secrets


def test_load_deployment_uses_safe_yaml(tmp_path: Path):
    from stroke_host.deployment.schema import load_deployment

    path = tmp_path / "device.yaml"
    path.write_text(
        """schema_version: 1
device: {id: sg-0002, management_token: '${STROKEGUARD_MANAGER_TOKEN}'}
wifi: {ssid: '${STROKEGUARD_WIFI_SSID}', password: '${STROKEGUARD_WIFI_PASSWORD}'}
mqtt:
  uri: mqtt://106.75.229.61:1883
  username: '${STROKEGUARD_MQTT_USERNAME}'
  password: '${STROKEGUARD_MQTT_PASSWORD}'
hardware:
  camera: {model: ESP32-S3-Cam, enabled: true, transport: i2c, address: 66, pins: {sda: 8, scl: 9}}
  microphone: {model: NMO432, enabled: true, sample_rate: 16000, channel: left, pins: {sck: 17, ws: 18, sd: 16}}
""",
        encoding="utf-8",
    )

    config = load_deployment(path, BASE_ENV)

    assert config.device_id == "sg-0002"


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda d: d.update({"unknown": True}), "unknown field"),
        (lambda d: d["device"].update({"extra": 1}), "unknown field"),
        (lambda d: d["device"].update({"id": "bad id"}), "device.id"),
        (lambda d: d["mqtt"].update({"uri": "http://not-mqtt"}), "mqtt.uri"),
        (lambda d: d["hardware"]["camera"].update({"model": "GC2145"}), "ESP32-S3-Cam"),
        (lambda d: d["hardware"]["camera"].update({"transport": "uart"}), "transport"),
        (lambda d: d["hardware"]["camera"].update({"address": 0x78}), "address"),
        (lambda d: d["hardware"]["microphone"].update({"model": "INMP441"}), "NMO432"),
        (lambda d: d["hardware"]["microphone"].update({"channel": "center"}), "channel"),
    ],
)
def test_deployment_rejects_invalid_or_unknown_fields(mutate, message):
    from stroke_host.deployment.schema import DeploymentValidationError, validate_deployment

    data = deployment_data()
    mutate(data)

    with pytest.raises(DeploymentValidationError, match=message):
        validate_deployment(data, BASE_ENV)


def test_deployment_rejects_missing_environment_secret():
    from stroke_host.deployment.schema import DeploymentValidationError, validate_deployment

    env = dict(BASE_ENV)
    del env["STROKEGUARD_WIFI_PASSWORD"]

    with pytest.raises(DeploymentValidationError, match="STROKEGUARD_WIFI_PASSWORD"):
        validate_deployment(deployment_data(), env)


def test_enabled_nmo432_requires_complete_i2s_pins():
    from stroke_host.deployment.schema import DeploymentValidationError, validate_deployment

    data = deployment_data()
    data["hardware"]["microphone"]["pins"] = {"sck": 17, "ws": 18}

    with pytest.raises(DeploymentValidationError, match="microphone.pins.*sd"):
        validate_deployment(data, BASE_ENV)


def test_enabled_nmo432_maps_i2s_pins_and_channel():
    from stroke_host.deployment.schema import validate_deployment

    data = deployment_data()
    data["hardware"]["microphone"].update(
        {"enabled": True, "channel": "right", "pins": {"sck": 17, "ws": 18, "sd": 16}}
    )

    config = validate_deployment(data, BASE_ENV)

    assert config.kconfig["CONFIG_STROKEGUARD_NMO432_ENABLE"] == "y"
    assert config.kconfig["CONFIG_STROKEGUARD_NMO432_BCLK"] == "17"
    assert config.kconfig["CONFIG_STROKEGUARD_NMO432_WS"] == "18"
    assert config.kconfig["CONFIG_STROKEGUARD_NMO432_DIN"] == "16"
    assert config.microphone.channel == "right"


def test_camera_coprocessor_requires_fixed_i2c_pins():
    from stroke_host.deployment.schema import DeploymentValidationError, validate_deployment

    data = deployment_data()
    data["hardware"]["camera"]["pins"] = {"sda": 8}

    with pytest.raises(DeploymentValidationError, match="camera.pins"):
        validate_deployment(data, BASE_ENV)


@pytest.mark.parametrize("bad_pin", [-1, 49, 26, 19])
def test_enabled_hardware_rejects_out_of_range_or_reserved_gpio(bad_pin):
    from stroke_host.deployment.schema import DeploymentValidationError, validate_deployment

    data = deployment_data()
    data["hardware"]["microphone"].update(
        {"enabled": True, "pins": {"sck": bad_pin, "ws": 18, "sd": 16}}
    )

    with pytest.raises(DeploymentValidationError, match="GPIO"):
        validate_deployment(data, BASE_ENV)


def test_enabled_hardware_rejects_duplicate_gpio_across_modules():
    from stroke_host.deployment.schema import DeploymentValidationError, validate_deployment

    data = deployment_data()
    data["hardware"]["microphone"].update(
        {"enabled": True, "pins": {"sck": 8, "ws": 17, "sd": 18}}
    )

    with pytest.raises(DeploymentValidationError, match="duplicate GPIO 8"):
        validate_deployment(data, BASE_ENV)


def test_redact_text_masks_all_resolved_secrets():
    from stroke_host.deployment.schema import redact_text, validate_deployment

    config = validate_deployment(deployment_data(), BASE_ENV)
    text = "wifi-secret manager-secret mqtt-secret sg-device StrokeLab"

    redacted = redact_text(text, config)

    assert redacted == "*** *** *** *** StrokeLab"
