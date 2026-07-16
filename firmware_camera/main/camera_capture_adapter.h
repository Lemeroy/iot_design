#pragma once

#include "camera_scores_protocol.h"
#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    sg_camera_face_bbox_t face_bbox;
    sg_camera_face_metrics_t face_metrics;
} sg_camera_source_observation_t;

esp_err_t sg_camera_capture_init(void);
esp_err_t sg_camera_capture_observe(sg_camera_source_observation_t *out);

#ifdef __cplusplus
}
#endif
