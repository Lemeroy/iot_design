#pragma once

#include <stdbool.h>
#include <stdint.h>

#include "esp_err.h"

typedef struct {
    bool face_present;
    uint8_t center_x;
    uint8_t center_y;
    uint8_t width;
    uint8_t height;
    int64_t received_us;
} sg_camera_observation_t;

esp_err_t sg_camera_coprocessor_init(void);
esp_err_t sg_camera_coprocessor_poll(sg_camera_observation_t *out);
