#include "camera_coprocessor.h"

#include <math.h>
#include <string.h>

#include "driver/gpio.h"
#include "driver/i2c_master.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "app_config.h"
#include "board_pins.h"
#include "camera_scores_protocol.h"
#include "log_tag.h"
#include "score_bus.h"

#define SG_CAMERA_I2C_HZ 100000U
#define SG_CAMERA_READ_TIMEOUT_MS 100
#define SG_CAMERA_REGISTER_SETTLE_MS 5
#define SG_CAMERA_STALE_US 2000000LL

static i2c_master_bus_handle_t s_bus;
static i2c_master_dev_handle_t s_device;
static volatile sg_screening_stage_t s_stage = SG_STAGE_IDLE;

static esp_err_t read_register(uint8_t reg, uint8_t raw[4])
{
    esp_err_t err = i2c_master_transmit(
        s_device, &reg, sizeof(reg), SG_CAMERA_READ_TIMEOUT_MS);
    if (err != ESP_OK) return err;
    vTaskDelay(pdMS_TO_TICKS(SG_CAMERA_REGISTER_SETTLE_MS));
    return i2c_master_receive(s_device, raw, 4, SG_CAMERA_READ_TIMEOUT_MS);
}

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
    if (out == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    memset(out, 0, sizeof(*out));
    if (s_device == NULL) {
        return ESP_ERR_INVALID_STATE;
    }

    uint8_t raw[sizeof(sg_camera_face_metrics_response_t)] = {0};
    esp_err_t err = read_register(SG_CAMERA_FACE_METRICS_REGISTER, raw);
    if (err != ESP_OK) {
        return err;
    }
    sg_camera_face_metrics_t metrics = {0};
    if (sg_camera_face_metrics_parse(raw, sizeof(raw), &metrics)
        != SG_CAMERA_PROTOCOL_OK) {
        return ESP_ERR_INVALID_RESPONSE;
    }

    out->valid = metrics.valid;
    out->score = metrics.score;
    out->mouth_angle_deg = metrics.mouth_angle_deg;
    out->quality = metrics.quality;
    err = read_register(SG_CAMERA_EYE_REGISTER, raw);
    if (err != ESP_OK || sg_camera_modal_parse(raw, sizeof(raw), &out->eye)
        != SG_CAMERA_PROTOCOL_OK) return ESP_ERR_INVALID_RESPONSE;
    err = read_register(SG_CAMERA_TONGUE_REGISTER, raw);
    if (err != ESP_OK || sg_camera_modal_parse(raw, sizeof(raw), &out->tongue)
        != SG_CAMERA_PROTOCOL_OK) return ESP_ERR_INVALID_RESPONSE;
    err = read_register(SG_CAMERA_STAGE_REGISTER, raw);
    if (err != ESP_OK || sg_camera_stage_parse(raw, sizeof(raw), &out->screening)
        != SG_CAMERA_PROTOCOL_OK) return ESP_ERR_INVALID_RESPONSE;
    s_stage = out->screening.stage;
    out->received_us = esp_timer_get_time();
    return ESP_OK;
}

static void camera_poll_task(void *arg)
{
    (void)arg;
    bool online = false;
    bool have_fresh_face = false;
    int64_t face_seen_us = 0;
    unsigned poll_failures = 0;
    esp_err_t last_poll_error = ESP_OK;
    TickType_t last_wake = xTaskGetTickCount();

    while (1) {
        vTaskDelayUntil(&last_wake, pdMS_TO_TICKS(SG_CAMERA_POLL_PERIOD_MS));
        sg_camera_observation_t observation;
        esp_err_t err = sg_camera_coprocessor_poll(&observation);
        int64_t now_us = esp_timer_get_time();
        if (err != ESP_OK) {
            publish_unavailable(now_us);
            poll_failures++;
            if (poll_failures == 1 || err != last_poll_error || poll_failures % 20 == 0) {
                ESP_LOGW(SG_TAG_MAIN,
                         "camera poll failed: %s count=%u SDA=%d SCL=%d",
                         esp_err_to_name(err), poll_failures,
                         gpio_get_level(SG_PIN_CAMERA_I2C_SDA),
                         gpio_get_level(SG_PIN_CAMERA_I2C_SCL));
            }
            last_poll_error = err;
            if (online) {
                ESP_LOGW(SG_TAG_MAIN, "camera coprocessor offline: %s",
                         esp_err_to_name(err));
            }
            online = false;
            have_fresh_face = false;
            continue;
        }

        poll_failures = 0;
        last_poll_error = ESP_OK;

        if (!online) {
            ESP_LOGI(SG_TAG_MAIN, "camera coprocessor online addr=0x%02x reg=0x%02x",
                     SG_CAMERA_I2C_ADDRESS, SG_CAMERA_FACE_METRICS_REGISTER);
            online = true;
        }
        if (observation.valid) {
            face_seen_us = now_us;
            have_fresh_face = true;
        } else if (have_fresh_face && now_us - face_seen_us > SG_CAMERA_STALE_US) {
            have_fresh_face = false;
        }

        if (observation.valid) ESP_LOGI(
            SG_TAG_MAIN, "camera F=%u E=%d T=%d stage=%u",
            observation.score,
            observation.eye.valid ? observation.eye.score : -1,
            observation.tongue.valid ? observation.tongue.score : -1,
            (unsigned)observation.screening.stage);
        err = sg_score_bus_apply_camera(
            have_fresh_face && observation.valid, observation.score,
            fabsf((float)observation.mouth_angle_deg),
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
    if (s_device == NULL || control > SG_SCREENING_START) {
        return ESP_ERR_INVALID_ARG;
    }
    const uint8_t command[2] = {SG_CAMERA_CONTROL_REGISTER, (uint8_t)control};
    return i2c_master_transmit(s_device, command, sizeof(command),
                               SG_CAMERA_READ_TIMEOUT_MS);
}

sg_screening_stage_t sg_camera_coprocessor_stage(void)
{
    return s_stage;
}

esp_err_t sg_camera_coprocessor_init(void)
{
    if (s_bus != NULL || s_device != NULL) {
        return ESP_ERR_INVALID_STATE;
    }
    i2c_master_bus_config_t bus_config = {
        .i2c_port = I2C_NUM_0,
        .sda_io_num = SG_PIN_CAMERA_I2C_SDA,
        .scl_io_num = SG_PIN_CAMERA_I2C_SCL,
        .clk_source = I2C_CLK_SRC_DEFAULT,
        .glitch_ignore_cnt = 7,
        .flags.enable_internal_pullup = true,
    };
    esp_err_t err = i2c_new_master_bus(&bus_config, &s_bus);
    if (err != ESP_OK) {
        return err;
    }

    i2c_device_config_t device_config = {
        .dev_addr_length = I2C_ADDR_BIT_LEN_7,
        .device_address = CONFIG_STROKEGUARD_CAMERA_I2C_ADDRESS,
        .scl_speed_hz = SG_CAMERA_I2C_HZ,
    };
    err = i2c_master_bus_add_device(s_bus, &device_config, &s_device);
    if (err != ESP_OK) {
        i2c_del_master_bus(s_bus);
        s_bus = NULL;
        return err;
    }

    BaseType_t created = xTaskCreatePinnedToCore(
        camera_poll_task, "camera_i2c", SG_TASK_CAMERA_STACK, NULL,
        SG_TASK_CAMERA_PRIO, NULL, SG_TASK_CAMERA_CORE);
    if (created != pdPASS) {
        i2c_master_bus_rm_device(s_device);
        i2c_del_master_bus(s_bus);
        s_device = NULL;
        s_bus = NULL;
        return ESP_ERR_NO_MEM;
    }
    return ESP_OK;
}
