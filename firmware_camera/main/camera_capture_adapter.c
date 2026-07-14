#include "camera_capture_adapter.h"

#include <string.h>

#include "camera_scores_protocol.h"

esp_err_t sg_camera_capture_init(void)
{
    return ESP_ERR_NOT_SUPPORTED;
}

esp_err_t sg_camera_capture_observe(sg_camera_source_observation_t *out)
{
    if (out == NULL) return ESP_ERR_INVALID_ARG;
    memset(out, 0, sizeof(*out));
    out->status = SG_CAMERA_STATUS_MODEL_MISSING;
    out->valid_mask = 0;
    return ESP_ERR_NOT_SUPPORTED;
}
