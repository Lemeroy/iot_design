#pragma once

#include <stdint.h>
#include "esp_err.h"
#include "fusion.h"

esp_err_t sg_score_bus_init(void);
esp_err_t sg_score_bus_set_face(int score, float theta_deg, int64_t now_us);
esp_err_t sg_score_bus_set_speech(int score, float p_clear, int64_t now_us);
esp_err_t sg_score_bus_set_tongue(int score, int64_t now_us);
esp_err_t sg_score_bus_set_eye(int score, int64_t now_us);
void sg_score_bus_snapshot(sg_scores_in_t *out, int64_t now_us,
                           uint32_t stale_ms);
