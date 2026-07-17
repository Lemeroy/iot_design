idf_component_register(
    SRCS
        "app_main.c"
        "camera_score_target.c"
        "camera_usb_preview.c"
        "camera_capture_adapter.cpp"
        "face_geometry.cpp"
        "face_baseline.c"
        "eye_tracking.cpp"
        "eye_continuous.cpp"
        "tongue_deviation.cpp"
        "screening_session.c"
        "../../firmware_common/camera_scores_protocol.c"
        "../../firmware_common/camera_preview_protocol.c"
    INCLUDE_DIRS "." "../../firmware_common"
    REQUIRES esp_driver_i2c esp_driver_uart esp_timer esp32-camera human_face_detect freertos log
)
