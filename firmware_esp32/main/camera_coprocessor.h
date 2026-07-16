#pragma once

#include <stdbool.h>
#include <stdint.h>

#include "esp_err.h"
#include "camera_scores_protocol.h"

typedef struct {
    bool valid;
    uint8_t score;
    int8_t mouth_angle_deg;
    uint8_t quality;
    sg_camera_modal_metrics_t eye;
    sg_camera_modal_metrics_t tongue;
    sg_camera_stage_status_t screening;
    int64_t received_us;
} sg_camera_observation_t;

esp_err_t sg_camera_coprocessor_init(void);
esp_err_t sg_camera_coprocessor_poll(sg_camera_observation_t *out);
esp_err_t sg_camera_coprocessor_control(sg_screening_control_t control);
sg_screening_stage_t sg_camera_coprocessor_stage(void);
