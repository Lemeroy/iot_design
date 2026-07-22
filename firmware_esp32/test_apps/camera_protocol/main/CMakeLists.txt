idf_component_register(
    SRCS
        "test_camera_protocol.c"
        "../../../../firmware_common/camera_scores_protocol.c"
        "../../../../firmware_common/camera_uart_protocol.c"
    INCLUDE_DIRS "../../../../firmware_common"
    REQUIRES unity freertos
)
