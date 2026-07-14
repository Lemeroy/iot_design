idf_component_register(
    SRCS
        "app_main.c"
        "camera_score_target.c"
        "camera_capture_adapter.c"
        "../../firmware_common/camera_scores_protocol.c"
    INCLUDE_DIRS "." "../../firmware_common"
    REQUIRES esp_driver_i2c freertos log
)
