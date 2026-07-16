#pragma once

#include "camera_scores_protocol.h"
#include "esp_err.h"

esp_err_t sg_camera_score_target_init(void);
bool sg_camera_score_target_take_control(sg_screening_control_t *control);
esp_err_t sg_camera_score_target_serve(
    const sg_camera_face_response_t *bbox_response,
    const sg_camera_face_metrics_response_t *metrics_response,
    const sg_camera_modal_response_t *eye_response,
    const sg_camera_modal_response_t *tongue_response,
    const sg_camera_stage_response_t *stage_response);
