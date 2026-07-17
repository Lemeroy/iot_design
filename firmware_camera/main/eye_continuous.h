#pragma once

#include <stdbool.h>
#include <stdint.h>

#include "camera_scores_protocol.h"
#include "eye_tracking.h"

#ifdef __cplusplus
extern "C" {
#endif

#define SG_EYE_CONTINUOUS_CAPACITY 12U
#define SG_EYE_CONTINUOUS_MIN_SAMPLES 6U
#define SG_EYE_CONTINUOUS_MAX_DROPOUT 2U
#define SG_EYE_GUIDED_OVERRIDE_US 30000000LL

typedef struct {
    bool valid;
    uint8_t score;
    int8_t binocular_difference;
    uint8_t quality;
} sg_eye_continuous_result_t;

typedef struct {
    sg_eye_measurement_t samples[SG_EYE_CONTINUOUS_CAPACITY];
    uint8_t count;
    uint8_t next;
    uint8_t dropout_count;
    sg_eye_continuous_result_t latest;
} sg_eye_continuous_context_t;

void sg_eye_continuous_init(sg_eye_continuous_context_t *context);

bool sg_eye_continuous_update(
    sg_eye_continuous_context_t *context,
    bool valid,
    const sg_eye_measurement_t *measurement,
    sg_eye_continuous_result_t *out);

bool sg_eye_select_result(
    const sg_eye_continuous_result_t *continuous,
    const sg_camera_modal_metrics_t *guided,
    int64_t guided_us,
    int64_t now_us,
    sg_camera_modal_metrics_t *out);

#ifdef __cplusplus
}
#endif
