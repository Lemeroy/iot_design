#include "camera_capture_adapter.h"
#include "camera_score_target.h"

#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static const char *TAG = "sg_camera";

void app_main(void)
{
    sg_camera_source_observation_t observation;
    esp_err_t capture_err = sg_camera_capture_init();
    if (capture_err != ESP_OK) {
        ESP_LOGW(TAG, "camera acquisition unavailable; serving model_missing");
    }
    ESP_ERROR_CHECK(sg_camera_score_target_init());

    while (1) {
        (void)sg_camera_capture_observe(&observation);
        sg_camera_scores_v1_t frame = {
            .version = SG_CAMERA_PROTOCOL_V1,
            .face = observation.face,
            .tongue = observation.tongue,
            .eye = observation.eye,
            .quality = observation.quality,
            .valid_mask = observation.valid_mask,
            .status = observation.status,
            .mouth_angle_x10 = observation.mouth_angle_x10,
            .latency_ms = observation.latency_ms,
        };
        frame.crc16 = sg_camera_scores_crc(&frame);
        esp_err_t err = sg_camera_score_target_serve(&frame);
        if (err != ESP_OK && err != ESP_ERR_TIMEOUT) {
            ESP_LOGW(TAG, "I2C score serve failed: %s", esp_err_to_name(err));
        }
        vTaskDelay(pdMS_TO_TICKS(20));
    }
}
