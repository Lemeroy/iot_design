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


def test_camera_coprocessor_is_polled_locally_with_validity():
    app = read("app_main.c")
    source = read("camera_coprocessor.c")
    bus = read("score_bus.c")
    cmake = read("CMakeLists.txt")

    assert '#include "camera_coprocessor.h"' in app
    assert "sg_camera_coprocessor_init" in app
    assert "i2c_new_master_bus" in source
    assert "i2c_master_transmit_receive" in source
    assert "SG_CAMERA_FACE_REGISTER" in source
    assert "sg_camera_face_bbox_parse" in source
    assert "sg_score_bus_apply_camera" in source
    assert "sg_score_bus_apply_camera" in bus
    assert '"camera_coprocessor.c"' in cmake
    assert "camera_scores_protocol.c" in cmake
    assert "ESP_ERROR_CHECK(sg_camera_coprocessor_init" not in app


def test_nmo432_uses_real_16khz_i2s_capture_without_cloud_audio():
    source = read("audio_nmo432.c")
    header = read("audio_nmo432.h")
    app = read("app_main.c")
    cmake = read("CMakeLists.txt")
    cloud = read("cloud_contract.c").lower()

    assert "i2s_new_channel" in source
    assert "I2S_STD_CLK_DEFAULT_CONFIG(16000)" in source
    assert "I2S_DATA_BIT_WIDTH_32BIT" in source
    assert "i2s_channel_read" in source
    assert "SG_PIN_NMO432_BCLK" in source
    assert "SG_PIN_NMO432_WS" in source
    assert "SG_PIN_NMO432_DIN" in source
    assert "SG_NMO432_BLOCK_SAMPLES 320" in header
    assert '#include "audio_nmo432.h"' in app
    assert "sg_audio_nmo432_init" in app
    assert app.index("sg_audio_nmo432_init") > app.index("void app_main")
    assert '"audio_nmo432.c"' in cmake
    for forbidden in ("pcm", "mfcc", "audio_b64"):
        assert forbidden not in cloud


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
    assert "mqtt://" not in defaults


def test_nvs_v2_supports_locked_revisioned_profile_updates():
    header = read("device_config.h")
    source = read("device_config.c")
    app = read("app_main.c")
    kconfig = read("Kconfig.projbuild")

    assert "SG_DEVICE_CONFIG_VERSION 2U" in header
    assert "SG_MANAGER_TOKEN_MAX" in header
    assert "uint32_t revision" in header
    assert "sg_profile_patch_t" in header
    assert "sg_device_config_snapshot" in header
    assert "sg_device_config_apply_profile" in header
    assert "sg_device_config_manager_ready" in header
    assert "sg_device_config_v1_t" in source
    assert "migrate_v1" in source
    assert "xSemaphoreTake" in source
    assert "expected_revision" in source
    assert "sg_device_config_snapshot" in app
    assert "config STROKEGUARD_MANAGER_PORT" in kconfig
    assert "config STROKEGUARD_MANAGER_TOKEN" in kconfig


def test_firmware_exposes_bounded_authenticated_manager_api():
    header = read("sg_manager_api.h")
    source = read("sg_manager_api.c")
    app = read("app_main.c")
    cmake = read("CMakeLists.txt")

    assert "SG_MANAGER_BODY_MAX 1024" in header
    assert "SG_MANAGER_AUTH_MAX 80" in header
    assert "SG_MANAGER_TASK_STACK 12288" in header
    assert "sg_manager_parse_profile_patch" in header
    assert "sg_manager_token_equal" in header
    assert "sg_manager_api_start" in header
    assert '"/api/v1/config"' in source
    assert "httpd_register_uri_handler" in source
    assert "Authorization" in source
    assert "Bearer " in source
    assert "Cache-Control" in source
    assert "no-store" in source
    assert "sg_manager_api_start" in app
    assert '"sg_manager_api.c"' in cmake
    assert "esp_http_server" in cmake
    assert "IPSTR" in app
    assert "IP2STR" in app


def test_manager_api_does_not_serialize_or_log_credentials():
    source = read("sg_manager_api.c")

    assert 'cJSON_AddStringToObject(root, "manager_token"' not in source
    assert 'cJSON_AddStringToObject(root, "mqtt_pass"' not in source
    assert 'cJSON_AddStringToObject(root, "mqtt_user"' not in source
    assert 'ESP_LOGI' not in source or "request_body" not in source
    assert "Authorization: %s" not in source


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


def test_local_alarm_is_authoritative_and_usb_stream_defaults_off():
    source = read("local_alert.c")
    app = read("app_main.c")
    kconfig = read("Kconfig.projbuild")
    assert "sg_local_alert_apply_fusion" in app
    assert "sg_local_alert_apply_advice" in app
    assert "SG_ADVICE_MAX_AGE_SEC" in app
    assert "sg_alert_io_set_level" in source
    assert "sg_display_st7789_show_status" in source
    assert "advice->level" not in source
    assert "CONFIG_STROKEGUARD_LEGACY_USB_STREAM" in app
    block = kconfig.split("config STROKEGUARD_LEGACY_USB_STREAM", 1)[1].split(
        "\n\n", 1
    )[0]
    assert "default n" in block
