idf_component_register(
    SRCS
        "test_eye_tongue.cpp"
        "../../../main/eye_tracking.cpp"
        "../../../main/tongue_deviation.cpp"
        "../../../main/screening_session.c"
    INCLUDE_DIRS "../../../main" "../../../../firmware_common"
    REQUIRES unity freertos
)
