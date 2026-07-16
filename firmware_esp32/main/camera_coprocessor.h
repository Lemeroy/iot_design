#pragma once

#include <stdbool.h>
#include <stdint.h>

#include "esp_err.h"

typedef struct {
    bool valid;
    uint8_t score;
    int8_t mouth_angle_deg;
    uint8_t quality;
    int64_t received_us;
} sg_camera_observation_t;

esp_err_t sg_camera_coprocessor_init(void);
esp_err_t sg_camera_coprocessor_poll(sg_camera_observation_t *out);
