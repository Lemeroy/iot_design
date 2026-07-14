#pragma once

#include <stdbool.h>

#include "camera_scores_protocol.h"
#include "esp_camera.h"
#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

esp_err_t sg_camera_usb_preview_init(void);
bool sg_camera_usb_preview_requested(void);
esp_err_t sg_camera_usb_preview_send(
    camera_fb_t *frame, const sg_camera_face_bbox_t *bbox);

#ifdef __cplusplus
}
#endif
