#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "face_geometry.h"

#ifdef __cplusplus
extern "C" {
#endif

#define SG_FACE_BASELINE_CALIBRATION_SAMPLES 5U
#define SG_FACE_BASELINE_OUTPUT_SAMPLES 3U
#define SG_FACE_BASELINE_RESET_US 10000000LL

typedef enum {
    SG_FACE_BASELINE_WAITING = 0,
    SG_FACE_BASELINE_CALIBRATING,
    SG_FACE_BASELINE_READY,
} sg_face_baseline_state_t;

typedef struct {
    sg_face_baseline_state_t state;
    float calibration_angles[SG_FACE_BASELINE_CALIBRATION_SAMPLES];
    float calibration_asymmetries[SG_FACE_BASELINE_CALIBRATION_SAMPLES];
    size_t calibration_count;
    float baseline_angle_deg;
    float baseline_asymmetry;
    uint8_t output_scores[SG_FACE_BASELINE_OUTPUT_SAMPLES];
    float output_angles[SG_FACE_BASELINE_OUTPUT_SAMPLES];
    float output_asymmetries[SG_FACE_BASELINE_OUTPUT_SAMPLES];
    uint8_t output_qualities[SG_FACE_BASELINE_OUTPUT_SAMPLES];
    size_t output_count;
    size_t output_next;
    int64_t last_valid_us;
} sg_face_baseline_t;

void sg_face_baseline_reset(sg_face_baseline_t *state);
bool sg_face_baseline_ready(const sg_face_baseline_t *state);
void sg_face_baseline_note_invalid(sg_face_baseline_t *state, int64_t now_us);
bool sg_face_baseline_update(
    sg_face_baseline_t *state,
    const sg_face_frame_metrics_t *sample,
    int64_t now_us,
    sg_face_frame_metrics_t *out);

#ifdef __cplusplus
}
#endif
