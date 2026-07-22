#pragma once

#include "camera_capture_adapter.h"
#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

esp_err_t sg_camera_score_uart_init(void);
esp_err_t sg_camera_score_uart_send(
    const sg_camera_source_observation_t *observation);

#ifdef __cplusplus
}
#endif
