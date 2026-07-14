#pragma once

#include <stdint.h>

#include "esp_err.h"

typedef struct {
    uint8_t face;
    uint8_t tongue;
    uint8_t eye;
    uint8_t quality;
    uint8_t valid_mask;
    uint8_t status;
    int16_t mouth_angle_x10;
    uint16_t latency_ms;
} sg_camera_source_observation_t;

esp_err_t sg_camera_capture_init(void);
esp_err_t sg_camera_capture_observe(sg_camera_source_observation_t *out);
