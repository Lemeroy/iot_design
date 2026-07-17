#pragma once

#include <stdbool.h>
#include <stdint.h>

#include "camera_scores_protocol.h"
#include "eye_tracking.h"
#include "tongue_deviation.h"

#ifdef __cplusplus
extern "C" {
#endif

#define SG_SCREENING_STABLE_SAMPLES 3U

typedef struct {
    bool face_ready;
    bool eye_valid;
    sg_eye_measurement_t eye;
    bool tongue_valid;
    sg_tongue_measurement_t tongue;
} sg_screening_sample_t;

typedef struct {
    sg_screening_stage_t stage;
    int64_t stage_started_us;
    uint8_t sample_count;
    uint8_t sample_next;
    uint8_t face_sample_window;
    uint8_t face_window_count;
    sg_eye_measurement_t eye_samples[SG_SCREENING_STABLE_SAMPLES];
    sg_tongue_measurement_t tongue_samples[SG_SCREENING_STABLE_SAMPLES];
    sg_eye_measurement_t center_eye;
    sg_eye_measurement_t left_eye;
    sg_eye_measurement_t right_eye;
    sg_camera_modal_metrics_t eye_result;
    sg_camera_modal_metrics_t tongue_result;
} sg_screening_session_t;

void sg_screening_session_start(sg_screening_session_t *session, int64_t now_us);
void sg_screening_session_cancel(sg_screening_session_t *session);
void sg_screening_session_update(
    sg_screening_session_t *session,
    const sg_screening_sample_t *sample,
    int64_t now_us);
sg_screening_stage_t sg_screening_session_stage(
    const sg_screening_session_t *session);
uint8_t sg_screening_session_progress(
    const sg_screening_session_t *session, int64_t now_us);
bool sg_screening_session_eye_result(
    const sg_screening_session_t *session, sg_camera_modal_metrics_t *out);
bool sg_screening_session_tongue_result(
    const sg_screening_session_t *session, sg_camera_modal_metrics_t *out);

#ifdef __cplusplus
}
#endif
