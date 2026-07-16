#pragma once

#include <stdbool.h>
#include <stddef.h>
#include "esp_err.h"
#include "cloud_contract.h"
#include "device_config.h"

typedef enum {
    SG_MQTT_DOWNLINK_ADVICE = 0,
    SG_MQTT_DOWNLINK_CONTROL,
} sg_mqtt_downlink_type_t;

typedef struct {
    sg_mqtt_downlink_type_t type;
    union {
        sg_cloud_advice_t advice;
        sg_cloud_screening_control_t control;
    } payload;
} sg_mqtt_downlink_t;

typedef void (*sg_mqtt_downlink_cb_t)(const sg_mqtt_downlink_t *downlink,
                                      void *ctx);

esp_err_t sg_mqtt_start(const sg_device_config_t *cfg,
                        sg_mqtt_downlink_cb_t cb, void *ctx);
esp_err_t sg_mqtt_publish_uplink(const char *json, size_t len);
bool sg_mqtt_connected(void);
void sg_mqtt_stop(void);
