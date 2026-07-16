#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "face_geometry.h"

#ifdef __cplusplus
extern "C" {
#endif

#define SG_FACE_STABILIZER_SAMPLES 5U

typedef struct {
    uint8_t scores[SG_FACE_STABILIZER_SAMPLES];
    float angles[SG_FACE_STABILIZER_SAMPLES];
    float asymmetries[SG_FACE_STABILIZER_SAMPLES];
    uint8_t qualities[SG_FACE_STABILIZER_SAMPLES];
    size_t count;
    size_t next;
} sg_face_stabilizer_t;

void sg_face_stabilizer_reset(sg_face_stabilizer_t *state);

bool sg_face_stabilizer_push(
    sg_face_stabilizer_t *state,
    const sg_face_frame_metrics_t *sample,
    sg_face_frame_metrics_t *out);

#ifdef __cplusplus
}
#endif
