idf_component_register(
    SRCS
        "test_eye_tongue.cpp"
        "../../../main/eye_tracking.cpp"
    INCLUDE_DIRS "../../../main"
    REQUIRES unity freertos
)
