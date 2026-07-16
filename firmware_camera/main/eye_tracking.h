#pragma once

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    int16_t x;
    int16_t y;
} sg_eye_point_t;

typedef struct {
    const uint8_t *rgb888;
    uint16_t width;
    uint16_t height;
    uint16_t stride_bytes;
    sg_eye_point_t left_eye;
    sg_eye_point_t right_eye;
    uint16_t inter_eye_distance;
    float eye_line_angle_deg;
} sg_eye_input_t;

typedef struct {
    int8_t left_x;
    int8_t right_x;
    uint8_t quality;
} sg_eye_measurement_t;

typedef struct {
    uint8_t score;
    int8_t binocular_difference;
    uint8_t quality;
} sg_eye_sequence_result_t;

bool sg_eye_measure(const sg_eye_input_t *input, sg_eye_measurement_t *out);

bool sg_eye_score_sequence(
    const sg_eye_measurement_t *center,
    const sg_eye_measurement_t *left,
    const sg_eye_measurement_t *right,
    sg_eye_sequence_result_t *out);

#ifdef __cplusplus
}
#endif
