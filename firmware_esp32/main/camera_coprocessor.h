#pragma once

#include <stdbool.h>
#include <stdint.h>

#include "esp_err.h"

typedef struct {
    bool face_valid;
    bool tongue_valid;
    bool eye_valid;
    uint8_t sequence;
    uint8_t face;
    uint8_t tongue;
    uint8_t eye;
    uint8_t quality;
    uint8_t status;
    int16_t mouth_angle_x10;
    uint16_t latency_ms;
    int64_t received_us;
} sg_camera_observation_t;

esp_err_t sg_camera_coprocessor_init(void);
esp_err_t sg_camera_coprocessor_poll(sg_camera_observation_t *out);
