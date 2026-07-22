#include "camera_score_uart.h"

#include <string.h>

#include "camera_uart_protocol.h"
#include "driver/gpio.h"
#include "driver/uart.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#define SG_CAMERA_SCORE_UART UART_NUM_1
#define SG_CAMERA_SCORE_UART_TX GPIO_NUM_48
#define SG_CAMERA_SCORE_UART_BAUD 115200
#define SG_CAMERA_SCORE_UART_RX_BUFFER 256

static const char *TAG = "sg_camera_uart";
static portMUX_TYPE s_lock = portMUX_INITIALIZER_UNLOCKED;
static sg_camera_uart_payload_t s_latest;
static uint16_t s_sequence;
static bool s_ready;

static void camera_score_uart_task(void *arg)
{
    (void)arg;
    TickType_t last_wake = xTaskGetTickCount();
    bool first_packet = true;
    while (true) {
        vTaskDelayUntil(&last_wake, pdMS_TO_TICKS(200));
        sg_camera_uart_payload_t payload;
        portENTER_CRITICAL(&s_lock);
        payload = s_latest;
        portEXIT_CRITICAL(&s_lock);

        uint8_t wire[SG_CAMERA_UART_PACKET_SIZE];
        if (sg_camera_uart_encode(&payload, ++s_sequence, wire)
            != SG_CAMERA_UART_OK) {
            ESP_LOGW(TAG, "score packet rejected before transmit");
            continue;
        }
        int written = uart_write_bytes(
            SG_CAMERA_SCORE_UART, wire, sizeof(wire));
        if (written != (int)sizeof(wire)) {
            ESP_LOGW(TAG, "score packet write failed bytes=%d", written);
        } else if (first_packet) {
            ESP_LOGI(TAG, "score stream active UART1 TX=48 baud=115200");
            first_packet = false;
        }
    }
}

esp_err_t sg_camera_score_uart_init(void)
{
    if (s_ready) return ESP_ERR_INVALID_STATE;
    const uart_config_t config = {
        .baud_rate = SG_CAMERA_SCORE_UART_BAUD,
        .data_bits = UART_DATA_8_BITS,
        .parity = UART_PARITY_DISABLE,
        .stop_bits = UART_STOP_BITS_1,
        .flow_ctrl = UART_HW_FLOWCTRL_DISABLE,
        .source_clk = UART_SCLK_DEFAULT,
    };
    esp_err_t err = uart_driver_install(
        SG_CAMERA_SCORE_UART, SG_CAMERA_SCORE_UART_RX_BUFFER, 0, 0, NULL, 0);
    if (err != ESP_OK) return err;
    err = uart_param_config(SG_CAMERA_SCORE_UART, &config);
    if (err != ESP_OK) return err;
    err = uart_set_pin(SG_CAMERA_SCORE_UART, SG_CAMERA_SCORE_UART_TX,
                       UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE,
                       UART_PIN_NO_CHANGE);
    if (err != ESP_OK) return err;
    BaseType_t created = xTaskCreate(
        camera_score_uart_task, "camera_score_uart", 3072, NULL, 9, NULL);
    if (created != pdPASS) return ESP_ERR_NO_MEM;
    s_ready = true;
    return ESP_OK;
}

esp_err_t sg_camera_score_uart_send(
    const sg_camera_source_observation_t *observation)
{
    if (!s_ready || observation == NULL) return ESP_ERR_INVALID_STATE;
    const sg_camera_uart_payload_t payload = {
        .face = observation->face_metrics,
        .eye = observation->eye_metrics,
        .tongue = observation->tongue_metrics,
        .screening = observation->screening,
    };
    portENTER_CRITICAL(&s_lock);
    s_latest = payload;
    portEXIT_CRITICAL(&s_lock);
    return ESP_OK;
}
