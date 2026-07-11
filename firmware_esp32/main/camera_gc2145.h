#pragma once

#include <stddef.h>
#include <stdint.h>
#include "esp_err.h"

typedef struct {
    const char *jpeg_b64;
    size_t jpeg_b64_len;
    uint16_t width;
    uint16_t height;
} sg_camera_gc2145_frame_t;

esp_err_t sg_camera_gc2145_init(void);
esp_err_t sg_camera_gc2145_capture(sg_camera_gc2145_frame_t *out);
