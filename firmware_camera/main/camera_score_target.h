#pragma once

#include "camera_scores_protocol.h"
#include "esp_err.h"

esp_err_t sg_camera_score_target_init(void);
esp_err_t sg_camera_score_target_serve(const sg_camera_scores_v1_t *frame);
