idf_component_register(
    SRCS
        "test_face_geometry.cpp"
        "../../../main/face_geometry.cpp"
        "../../../main/face_stabilizer.c"
        "../../../main/face_baseline.c"
    INCLUDE_DIRS "../../../main"
    REQUIRES unity freertos
)
