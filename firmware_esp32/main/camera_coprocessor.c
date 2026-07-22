#include "camera_coprocessor.h"

#include <math.h>
#include <string.h>

#include "camera_uart_protocol.h"
#include "driver/gpio.h"
#include "driver/uart.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/task.h"

#include "app_config.h"
#include "log_tag.h"
#include "score_bus.h"

#define SG_CAMERA_UART UART_NUM_1
#define SG_CAMERA_UART_RX GPIO_NUM_9
#define SG_CAMERA_UART_BAUD 115200
#define SG_CAMERA_UART_RX_BUFFER 512
#define SG_CAMERA_UART_READ_MS 100
#define SG_CAMERA_UART_FRESH_US 2000000LL
#define SG_CAMERA_FACE_HOLD_US 5000000LL

static bool s_ready;
static SemaphoreHandle_t s_lock;
static sg_camera_uart_stream_t s_stream;
static sg_camera_uart_payload_t s_latest;
static int64_t s_last_received_us;
static uint16_t s_last_sequence;
static bool s_have_sequence;
static unsigned s_raw_bytes_since_log;
static unsigned s_valid_packets_since_log;
static volatile sg_screening_stage_t s_stage = SG_STAGE_IDLE;

static void publish_unavailable(int64_t now_us)
{
    esp_err_t err = sg_score_bus_apply_camera(
        false, 0, 0.0f, false, 0, false, 0, now_us);
    if (err != ESP_OK) {
        ESP_LOGW(SG_TAG_MAIN, "camera score clear failed: %s",
                 esp_err_to_name(err));
    }
}

esp_err_t sg_camera_coprocessor_poll(sg_camera_observation_t *out)
{
    if (out == NULL) return ESP_ERR_INVALID_ARG;
    memset(out, 0, sizeof(*out));
    if (!s_ready || s_lock == NULL) return ESP_ERR_INVALID_STATE;

    uint8_t bytes[64];
    int received = uart_read_bytes(
        SG_CAMERA_UART, bytes, sizeof(bytes),
        pdMS_TO_TICKS(SG_CAMERA_UART_READ_MS));
    if (received < 0) return ESP_FAIL;

    xSemaphoreTake(s_lock, portMAX_DELAY);
    s_raw_bytes_since_log += (unsigned)received;
    for (int i = 0; i < received; ++i) {
        sg_camera_uart_payload_t payload;
        uint16_t sequence;
        if (!sg_camera_uart_stream_feed(
                &s_stream, bytes[i], &payload, &sequence)) {
            continue;
        }
        if (s_have_sequence
            && sequence != (uint16_t)(s_last_sequence + 1U)) {
            ESP_LOGW(SG_TAG_MAIN, "camera UART sequence gap previous=%u next=%u",
                     (unsigned)s_last_sequence, (unsigned)sequence);
        }
        s_latest = payload;
        s_last_sequence = sequence;
        s_have_sequence = true;
        ++s_valid_packets_since_log;
        s_last_received_us = esp_timer_get_time();
        s_stage = payload.screening.stage;
    }
    const int64_t now_us = esp_timer_get_time();
    if (s_last_received_us == 0
        || now_us - s_last_received_us > SG_CAMERA_UART_FRESH_US) {
        xSemaphoreGive(s_lock);
        return ESP_ERR_TIMEOUT;
    }
    const sg_camera_uart_payload_t latest = s_latest;
    const int64_t latest_us = s_last_received_us;
    xSemaphoreGive(s_lock);

    out->valid = latest.face.valid;
    out->score = latest.face.score;
    out->mouth_angle_deg = latest.face.mouth_angle_deg;
    out->quality = latest.face.quality;
    out->eye = latest.eye;
    out->tongue = latest.tongue;
    out->screening = latest.screening;
    out->received_us = latest_us;
    return ESP_OK;
}

static void camera_poll_task(void *arg)
{
    (void)arg;
    bool online = false;
    bool have_fresh_face = false;
    uint8_t last_face_score = 0;
    float last_face_angle_deg = 0.0f;
    int64_t face_seen_us = 0;
    unsigned poll_failures = 0;
    TickType_t last_wake = xTaskGetTickCount();

    while (true) {
        vTaskDelayUntil(&last_wake, pdMS_TO_TICKS(SG_CAMERA_POLL_PERIOD_MS));
        sg_camera_observation_t observation;
        esp_err_t err = sg_camera_coprocessor_poll(&observation);
        const int64_t now_us = esp_timer_get_time();
        if (err != ESP_OK) {
            publish_unavailable(now_us);
            ++poll_failures;
            if (poll_failures == 1U || poll_failures % 20U == 0U) {
                ESP_LOGW(SG_TAG_MAIN,
                         "camera UART unavailable: %s count=%u RX=%d "
                         "raw_bytes=%u valid_packets=%u",
                         esp_err_to_name(err), poll_failures,
                         gpio_get_level(SG_CAMERA_UART_RX),
                         s_raw_bytes_since_log, s_valid_packets_since_log);
                s_raw_bytes_since_log = 0;
                s_valid_packets_since_log = 0;
            }
            if (online) ESP_LOGW(SG_TAG_MAIN, "camera coprocessor offline");
            online = false;
            have_fresh_face = false;
            continue;
        }

        poll_failures = 0;
        s_raw_bytes_since_log = 0;
        s_valid_packets_since_log = 0;
        if (!online) {
            ESP_LOGI(SG_TAG_MAIN, "camera coprocessor online via UART1 RX=9");
            online = true;
        }
        if (observation.valid) {
            face_seen_us = now_us;
            have_fresh_face = true;
            last_face_score = observation.score;
            last_face_angle_deg = fabsf((float)observation.mouth_angle_deg);
        } else if (have_fresh_face
                   && now_us - face_seen_us > SG_CAMERA_FACE_HOLD_US) {
            have_fresh_face = false;
        }

        ESP_LOGI(SG_TAG_MAIN, "camera UART F=%d E=%d T=%d stage=%u progress=%u",
                 observation.valid ? observation.score : -1,
                 observation.eye.valid ? observation.eye.score : -1,
                 observation.tongue.valid ? observation.tongue.score : -1,
                 (unsigned)observation.screening.stage,
                 (unsigned)observation.screening.progress);
        err = sg_score_bus_apply_camera(
            have_fresh_face, last_face_score, last_face_angle_deg,
            observation.tongue.valid, observation.tongue.score,
            observation.eye.valid, observation.eye.score, now_us);
        if (err != ESP_OK) {
            publish_unavailable(now_us);
            ESP_LOGW(SG_TAG_MAIN, "camera observation rejected: %s",
                     esp_err_to_name(err));
        }
    }
}

esp_err_t sg_camera_coprocessor_control(sg_screening_control_t control)
{
    if (!s_ready || s_lock == NULL || control > SG_SCREENING_START) {
        return ESP_ERR_INVALID_ARG;
    }
    xSemaphoreTake(s_lock, portMAX_DELAY);
    memset(&s_stream, 0, sizeof(s_stream));
    memset(&s_latest, 0, sizeof(s_latest));
    s_last_received_us = 0;
    s_have_sequence = false;
    s_stage = SG_STAGE_IDLE;
    uart_flush_input(SG_CAMERA_UART);
    xSemaphoreGive(s_lock);
    const char *message = control == SG_SCREENING_START
        ? "camera UART session armed"
        : "camera UART session cancelled";
    ESP_LOGI(SG_TAG_MAIN, "%s", message);
    return ESP_OK;
}

sg_screening_stage_t sg_camera_coprocessor_stage(void)
{
    return s_stage;
}

esp_err_t sg_camera_coprocessor_init(void)
{
    if (s_ready) return ESP_ERR_INVALID_STATE;
    s_lock = xSemaphoreCreateMutex();
    if (s_lock == NULL) return ESP_ERR_NO_MEM;
    const uart_config_t config = {
        .baud_rate = SG_CAMERA_UART_BAUD,
        .data_bits = UART_DATA_8_BITS,
        .parity = UART_PARITY_DISABLE,
        .stop_bits = UART_STOP_BITS_1,
        .flow_ctrl = UART_HW_FLOWCTRL_DISABLE,
        .source_clk = UART_SCLK_DEFAULT,
    };
    esp_err_t err = uart_driver_install(
        SG_CAMERA_UART, SG_CAMERA_UART_RX_BUFFER, 0, 0, NULL, 0);
    if (err != ESP_OK) return err;
    err = uart_param_config(SG_CAMERA_UART, &config);
    if (err != ESP_OK) return err;
    err = uart_set_pin(SG_CAMERA_UART, UART_PIN_NO_CHANGE,
                       SG_CAMERA_UART_RX, UART_PIN_NO_CHANGE,
                       UART_PIN_NO_CHANGE);
    if (err != ESP_OK) return err;
    s_ready = true;
    BaseType_t created = xTaskCreatePinnedToCore(
        camera_poll_task, "camera_uart", SG_TASK_CAMERA_STACK, NULL,
        SG_TASK_CAMERA_PRIO, NULL, SG_TASK_CAMERA_CORE);
    if (created != pdPASS) {
        s_ready = false;
        return ESP_ERR_NO_MEM;
    }
    ESP_LOGI(SG_TAG_MAIN, "camera UART ready UART1 RX=9 baud=115200");
    return ESP_OK;
}
