#include "camera_capture_adapter.h"
#include "camera_score_target.h"
#include "camera_usb_preview.h"

#include "driver/gpio.h"
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
    ESP_ERROR_CHECK(sg_camera_usb_preview_init());
    ESP_LOGI(TAG, "I2C idle levels SDA47=%d SCL48=%d",
             gpio_get_level(GPIO_NUM_47), gpio_get_level(GPIO_NUM_48));

    while (1) {
        sg_screening_control_t control;
        if (sg_camera_score_target_take_control(&control)) {
            ESP_ERROR_CHECK_WITHOUT_ABORT(sg_camera_capture_control(control));
        }
        (void)sg_camera_capture_observe(&observation);
        sg_camera_face_response_t bbox_response;
        sg_camera_face_metrics_response_t metrics_response;
        sg_camera_modal_response_t eye_response;
        sg_camera_modal_response_t tongue_response;
        sg_camera_stage_response_t stage_response;
        sg_camera_face_response_encode(&observation.face_bbox, &bbox_response);
        sg_camera_face_metrics_encode(
            &observation.face_metrics, &metrics_response);
        sg_camera_modal_encode(&observation.eye_metrics, &eye_response);
        sg_camera_modal_encode(&observation.tongue_metrics, &tongue_response);
        sg_camera_stage_encode(&observation.screening, &stage_response);
        esp_err_t err = sg_camera_score_target_serve(
            &bbox_response, &metrics_response, &eye_response,
            &tongue_response, &stage_response);
        if (err != ESP_OK && err != ESP_ERR_TIMEOUT) {
            ESP_LOGW(TAG, "I2C score serve failed: %s", esp_err_to_name(err));
        }
        vTaskDelay(pdMS_TO_TICKS(20));
    }
}
