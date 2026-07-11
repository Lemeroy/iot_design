idf_component_register(
    SRCS
        "test_e1_core.c"
        "../../../main/fusion.c"
        "../../../main/local_alert.c"
    INCLUDE_DIRS "../../../main"
    REQUIRES unity freertos log
)
