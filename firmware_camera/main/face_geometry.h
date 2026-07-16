#pragma once

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    int16_t x;
    int16_t y;
} sg_face_point_t;

typedef struct {
    int16_t x0;
    int16_t y0;
    int16_t x1;
    int16_t y1;
} sg_face_box_t;

typedef struct {
    sg_face_box_t box;
    sg_face_point_t left_eye;
    sg_face_point_t right_eye;
    sg_face_point_t nose;
    sg_face_point_t left_mouth;
    sg_face_point_t right_mouth;
} sg_face_geometry_input_t;

typedef struct {
    uint8_t score;
    float mouth_angle_deg;
    float corner_asymmetry;
    uint8_t quality;
} sg_face_frame_metrics_t;

bool sg_face_geometry_evaluate(
    const sg_face_geometry_input_t *input,
    sg_face_frame_metrics_t *out);

#ifdef __cplusplus
}
#endif
