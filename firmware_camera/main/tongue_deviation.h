#pragma once

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define SG_TONGUE_AUXILIARY_ONLY 1

typedef struct {
    int16_t x;
    int16_t y;
} sg_tongue_point_t;

typedef struct {
    uint16_t x;
    uint16_t y;
    uint16_t width;
    uint16_t height;
} sg_tongue_roi_t;

typedef struct {
    const uint8_t *rgb888;
    uint16_t width;
    uint16_t height;
    uint16_t stride_bytes;
    sg_tongue_roi_t roi;
    sg_tongue_point_t axis_origin;
    uint16_t face_width;
    float face_roll_deg;
} sg_tongue_input_t;

typedef struct {
    int8_t signed_offset;
    uint8_t score;
    uint8_t quality;
} sg_tongue_measurement_t;

bool sg_tongue_measure(
    const sg_tongue_input_t *input, sg_tongue_measurement_t *out);

#ifdef __cplusplus
}
#endif
