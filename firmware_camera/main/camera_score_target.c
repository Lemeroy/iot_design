#include "camera_score_target.h"

#include <string.h>

#include "driver/i2c_slave.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/task.h"
#include "hal/gpio_types.h"

typedef enum {
    SG_CAMERA_TARGET_EVENT_RECEIVE,
    SG_CAMERA_TARGET_EVENT_REQUEST,
} sg_camera_target_event_type_t;

typedef struct {
    sg_camera_target_event_type_t type;
    uint8_t reg;
    uint8_t value;
    bool has_value;
} sg_camera_target_event_t;

typedef struct {
    i2c_slave_dev_handle_t target;
    QueueHandle_t events;
    portMUX_TYPE response_lock;
    sg_camera_face_response_t latest_bbox;
    sg_camera_face_metrics_response_t latest_metrics;
    sg_camera_modal_response_t latest_eye;
    sg_camera_modal_response_t latest_tongue;
    sg_camera_stage_response_t latest_stage;
    sg_screening_control_t pending_control;
    bool control_pending;
    volatile uint32_t dropped_events;
    uint8_t selected_reg;
} sg_camera_target_context_t;

static sg_camera_target_context_t s_context = {
    .response_lock = portMUX_INITIALIZER_UNLOCKED,
};
static const char *TAG = "sg_camera_i2c";

static bool camera_target_on_receive(
    i2c_slave_dev_handle_t target,
    const i2c_slave_rx_done_event_data_t *event_data,
    void *user_data)
{
    (void)target;
    sg_camera_target_context_t *context = user_data;
    if (event_data->length == 0) return false;

    if (event_data->length >= 2
        && event_data->buffer[0] == SG_CAMERA_CONTROL_REGISTER
        && event_data->buffer[1] <= SG_SCREENING_START) {
        portENTER_CRITICAL_ISR(&context->response_lock);
        context->pending_control =
            (sg_screening_control_t)event_data->buffer[1];
        context->control_pending = true;
        portEXIT_CRITICAL_ISR(&context->response_lock);
        return false;
    }

    sg_camera_target_event_t event = {
        .type = SG_CAMERA_TARGET_EVENT_RECEIVE,
        .reg = event_data->buffer[0],
        .value = event_data->length >= 2 ? event_data->buffer[1] : 0,
        .has_value = event_data->length >= 2,
    };
    BaseType_t task_woken = pdFALSE;
    if (xQueueSendFromISR(context->events, &event, &task_woken) != pdPASS) {
        context->dropped_events++;
    }
    return task_woken == pdTRUE;
}

static bool camera_target_on_request(
    i2c_slave_dev_handle_t target,
    const i2c_slave_request_event_data_t *event_data,
    void *user_data)
{
    (void)target;
    (void)event_data;
    sg_camera_target_context_t *context = user_data;
    const sg_camera_target_event_t event = {
        .type = SG_CAMERA_TARGET_EVENT_REQUEST,
        .reg = 0,
    };
    BaseType_t task_woken = pdFALSE;
    xQueueSendFromISR(context->events, &event, &task_woken);
    return task_woken == pdTRUE;
}

static void camera_target_task(void *arg)
{
    sg_camera_target_context_t *context = arg;
    sg_camera_target_event_t event;
    bool receive_logged = false;
    bool request_logged = false;
    uint32_t last_dropped_events = 0;

    while (true) {
        if (xQueueReceive(context->events, &event, portMAX_DELAY) != pdTRUE) {
            continue;
        }
        if (context->dropped_events != last_dropped_events) {
            last_dropped_events = context->dropped_events;
            ESP_LOGW(TAG, "I2C event queue overflow count=%lu",
                     (unsigned long)last_dropped_events);
        }
        if (event.type == SG_CAMERA_TARGET_EVENT_RECEIVE) {
            if (event.reg == SG_CAMERA_CONTROL_REGISTER && event.has_value
                && event.value <= SG_SCREENING_START) {
                portENTER_CRITICAL(&context->response_lock);
                context->pending_control = (sg_screening_control_t)event.value;
                context->control_pending = true;
                portEXIT_CRITICAL(&context->response_lock);
                continue;
            }
            context->selected_reg = event.reg;
            if (!receive_logged) {
                ESP_LOGI(TAG, "first register received: 0x%02x", event.reg);
                receive_logged = true;
            }
            continue;
        }

        uint8_t response[sizeof(sg_camera_face_response_t)] = {0};
        if (context->selected_reg == SG_CAMERA_FACE_REGISTER) {
            portENTER_CRITICAL(&context->response_lock);
            memcpy(response, &context->latest_bbox, sizeof(response));
            portEXIT_CRITICAL(&context->response_lock);
        } else if (context->selected_reg == SG_CAMERA_FACE_METRICS_REGISTER) {
            portENTER_CRITICAL(&context->response_lock);
            memcpy(response, &context->latest_metrics, sizeof(response));
            portEXIT_CRITICAL(&context->response_lock);
        } else if (context->selected_reg == SG_CAMERA_EYE_REGISTER) {
            portENTER_CRITICAL(&context->response_lock);
            memcpy(response, &context->latest_eye, sizeof(response));
            portEXIT_CRITICAL(&context->response_lock);
        } else if (context->selected_reg == SG_CAMERA_TONGUE_REGISTER) {
            portENTER_CRITICAL(&context->response_lock);
            memcpy(response, &context->latest_tongue, sizeof(response));
            portEXIT_CRITICAL(&context->response_lock);
        } else if (context->selected_reg == SG_CAMERA_STAGE_REGISTER) {
            portENTER_CRITICAL(&context->response_lock);
            memcpy(response, &context->latest_stage, sizeof(response));
            portEXIT_CRITICAL(&context->response_lock);
        }

        uint32_t written = 0;
        esp_err_t err = i2c_slave_write(
            context->target, response, sizeof(response),
            &written, 1000);
        if (!request_logged || err != ESP_OK || written != sizeof(response)) {
            ESP_LOGI(TAG, "read request reg=0x%02x err=%s bytes=%lu",
                     context->selected_reg, esp_err_to_name(err),
                     (unsigned long)written);
            request_logged = true;
        }
    }
}

esp_err_t sg_camera_score_target_init(void)
{
    if (s_context.target != NULL) return ESP_ERR_INVALID_STATE;

    s_context.events = xQueueCreate(8, sizeof(sg_camera_target_event_t));
    if (s_context.events == NULL) return ESP_ERR_NO_MEM;

    const i2c_slave_config_t config = {
        .i2c_port = I2C_NUM_0,
        .sda_io_num = GPIO_NUM_47,
        .scl_io_num = GPIO_NUM_48,
        .clk_source = I2C_CLK_SRC_DEFAULT,
        .send_buf_depth = 16,
        .receive_buf_depth = 16,
        .slave_addr = SG_CAMERA_I2C_ADDRESS,
        .addr_bit_len = I2C_ADDR_BIT_LEN_7,
        .intr_priority = 0,
        .flags.enable_internal_pullup = true,
    };
    esp_err_t err = i2c_new_slave_device(&config, &s_context.target);
    if (err != ESP_OK) return err;

    const i2c_slave_event_callbacks_t callbacks = {
        .on_receive = camera_target_on_receive,
        .on_request = camera_target_on_request,
    };
    err = i2c_slave_register_event_callbacks(
        s_context.target, &callbacks, &s_context);
    if (err != ESP_OK) return err;

    BaseType_t created = xTaskCreate(
        camera_target_task, "camera_i2c_target", 4096, &s_context, 10, NULL);
    if (created != pdPASS) return ESP_ERR_NO_MEM;
    ESP_LOGI(TAG, "I2C target ready port=0 addr=0x%02x SDA=47 SCL=48",
             SG_CAMERA_I2C_ADDRESS);
    return ESP_OK;
}

bool sg_camera_score_target_take_control(sg_screening_control_t *control)
{
    if (control == NULL || s_context.target == NULL) return false;
    bool available = false;
    portENTER_CRITICAL(&s_context.response_lock);
    if (s_context.control_pending) {
        *control = s_context.pending_control;
        s_context.control_pending = false;
        available = true;
    }
    portEXIT_CRITICAL(&s_context.response_lock);
    return available;
}

esp_err_t sg_camera_score_target_serve(
    const sg_camera_face_response_t *bbox_response,
    const sg_camera_face_metrics_response_t *metrics_response,
    const sg_camera_modal_response_t *eye_response,
    const sg_camera_modal_response_t *tongue_response,
    const sg_camera_stage_response_t *stage_response)
{
    if (bbox_response == NULL || metrics_response == NULL || eye_response == NULL
        || tongue_response == NULL || stage_response == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    if (s_context.target == NULL) return ESP_ERR_INVALID_STATE;

    portENTER_CRITICAL(&s_context.response_lock);
    s_context.latest_bbox = *bbox_response;
    s_context.latest_metrics = *metrics_response;
    s_context.latest_eye = *eye_response;
    s_context.latest_tongue = *tongue_response;
    s_context.latest_stage = *stage_response;
    portEXIT_CRITICAL(&s_context.response_lock);
    return ESP_OK;
}
