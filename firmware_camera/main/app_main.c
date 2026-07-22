#include "camera_capture_adapter.h"
#include "camera_score_uart.h"
#include "camera_usb_preview.h"

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
    ESP_ERROR_CHECK(sg_camera_score_uart_init());
    ESP_ERROR_CHECK(sg_camera_usb_preview_init());

    while (1) {
        (void)sg_camera_capture_observe(&observation);
        esp_err_t err = sg_camera_score_uart_send(&observation);
        if (err != ESP_OK) {
            ESP_LOGW(TAG, "UART score update failed: %s", esp_err_to_name(err));
        }
        vTaskDelay(pdMS_TO_TICKS(20));
    }
}
