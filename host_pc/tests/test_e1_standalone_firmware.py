from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MAIN = ROOT / "firmware_esp32" / "main"


def read(name: str) -> str:
    return (MAIN / name).read_text(encoding="utf-8")


def test_local_score_bus_is_wired_into_fusion():
    assert (MAIN / "score_bus.h").is_file()
    assert (MAIN / "score_bus.c").is_file()
    app = read("app_main.c")
    assert '#include "score_bus.h"' in app
    assert "sg_score_bus_snapshot" in app
    assert "sg_csi_get_score" in app
    assert "sg_fusion_compute" in app


def test_production_app_does_not_accept_pc_scores():
    app = read("app_main.c")
    cmake = read("CMakeLists.txt")
    assert "on_cdc_rx" not in app
    assert "sg_scores_parse" not in app
    assert '"scores_parser.c"' not in cmake


def test_no_runtime_fabricated_healthy_scores():
    bus = read("score_bus.c")
    assert "memset(out, 0xFF" not in bus
    assert "NAN" in bus
    assert "score = -1" in bus


def test_nvs_config_has_version_crc_and_no_real_credentials():
    header = read("device_config.h")
    source = read("device_config.c")
    kconfig = read("Kconfig.projbuild")
    defaults = (ROOT / "firmware_esp32" / "sdkconfig.defaults").read_text(
        encoding="utf-8"
    )
    assert "SG_DEVICE_CONFIG_VERSION" in header
    assert "crc32" in header
    assert 'nvs_open("sg_cfg"' in source
    assert '"device"' in source
    assert "config STROKEGUARD_MQTT_URI" in kconfig
    assert "config STROKEGUARD_DEVICE_ID" in kconfig
    assert "106.75.229.61" not in defaults


def test_firmware_cloud_contract_is_numeric_only_and_bounded():
    header = read("cloud_contract.h")
    source = read("cloud_contract.c")
    for field in (
        '"scores"',
        '"face"',
        '"speech"',
        '"tongue"',
        '"eye"',
        '"csi"',
        '"final"',
        '"level"',
        '"profile"',
        '"device_id"',
    ):
        assert field in source
    assert "cJSON_CreateObject" in source
    assert "SG_ADVICE_TEXT_MAX" in header
    lowered = source.lower()
    for forbidden in ("jpeg_b64", "mfcc", "landmarks", '"roi"'):
        assert forbidden not in lowered


def test_esp_mqtt_is_direct_and_subscribes_to_device_downlink():
    source = read("sg_mqtt.c")
    cmake = read("CMakeLists.txt")
    assert "esp_mqtt_client_init" in source
    assert "esp_mqtt_client_subscribe" in source
    assert "esp_mqtt_client_enqueue" in source
    assert '"strokeguard/%s/uplink"' in source
    assert '"strokeguard/%s/downlink"' in source
    assert "sg_cloud_parse_advice" in source
    assert "total_data_len" in source and "current_data_offset" in source
    assert "mqtt" in cmake
    for line in source.splitlines():
        if "ESP_LOG" in line:
            assert "mqtt_pass" not in line


def test_sntp_time_gates_cloud_publish_only():
    time_source = read("sg_time.c")
    app = read("app_main.c")
    assert "esp_netif_sntp_init" in time_source
    assert "sg_time_sync_start" in app
