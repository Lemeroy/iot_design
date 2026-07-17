idf_component_register(
    SRCS
        "test_e1_core.c"
        "../../../main/fusion.c"
        "../../../main/speech_screening.c"
        "../../../main/local_alert.c"
        "../../../main/device_config.c"
        "../../../main/sg_manager_api.c"
    INCLUDE_DIRS "../../../main" "../../../../firmware_common"
    REQUIRES unity freertos log nvs_flash esp_hw_support json esp_http_server
)
