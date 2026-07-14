#include "camera_coprocessor.h"

#include <string.h>

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
#define SG_CAMERA_STALE_US 2000000LL

static i2c_master_bus_handle_t s_bus;
static i2c_master_dev_handle_t s_device;

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

    const uint8_t reg = SG_CAMERA_FACE_REGISTER;
    uint8_t raw[sizeof(sg_camera_face_response_t)] = {0};
    esp_err_t err = i2c_master_transmit_receive(
        s_device, &reg, sizeof(reg), raw, sizeof(raw),
        SG_CAMERA_READ_TIMEOUT_MS);
    if (err != ESP_OK) {
        return err;
    }
    sg_camera_face_bbox_t bbox = {0};
    if (sg_camera_face_bbox_parse(raw, sizeof(raw), &bbox)
        != SG_CAMERA_PROTOCOL_OK) {
        return ESP_ERR_INVALID_RESPONSE;
    }

    out->face_present = bbox.valid;
    out->center_x = bbox.center_x;
    out->center_y = bbox.center_y;
    out->width = bbox.width;
    out->height = bbox.height;
    out->received_us = esp_timer_get_time();
    return ESP_OK;
}

static void camera_poll_task(void *arg)
{
    (void)arg;
    bool online = false;
    bool have_fresh_face = false;
    int64_t face_seen_us = 0;
    TickType_t last_wake = xTaskGetTickCount();

    while (1) {
        vTaskDelayUntil(&last_wake, pdMS_TO_TICKS(SG_CAMERA_POLL_PERIOD_MS));
        sg_camera_observation_t observation;
        esp_err_t err = sg_camera_coprocessor_poll(&observation);
        int64_t now_us = esp_timer_get_time();
        if (err != ESP_OK) {
            publish_unavailable(now_us);
            if (online) {
                ESP_LOGW(SG_TAG_MAIN, "camera coprocessor offline: %s",
                         esp_err_to_name(err));
            }
            online = false;
            have_fresh_face = false;
            continue;
        }

        if (!online) {
            ESP_LOGI(SG_TAG_MAIN, "camera coprocessor online addr=0x%02x reg=0x%02x",
                     SG_CAMERA_I2C_ADDRESS, SG_CAMERA_FACE_REGISTER);
            online = true;
        }
        if (observation.face_present) {
            face_seen_us = now_us;
            have_fresh_face = true;
        } else if (have_fresh_face && now_us - face_seen_us > SG_CAMERA_STALE_US) {
            have_fresh_face = false;
        }

        if (!have_fresh_face) {
            publish_unavailable(now_us);
            continue;
        }

        ESP_LOGI(SG_TAG_MAIN, "camera face bbox cx=%u cy=%u w=%u h=%u",
                 observation.center_x, observation.center_y,
                 observation.width, observation.height);
        err = sg_score_bus_apply_camera(
            false, 0, 0.0f, false, 0, false, 0, now_us);
        if (err != ESP_OK) {
            publish_unavailable(now_us);
            ESP_LOGW(SG_TAG_MAIN, "camera observation rejected: %s",
                     esp_err_to_name(err));
        }
    }
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
