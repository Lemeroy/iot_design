#pragma once

#include <stdbool.h>
#include <stddef.h>
#include "esp_err.h"
#include "cloud_contract.h"
#include "device_config.h"

typedef void (*sg_mqtt_advice_cb_t)(const sg_cloud_advice_t *advice,
                                    void *ctx);

esp_err_t sg_mqtt_start(const sg_device_config_t *cfg,
                        sg_mqtt_advice_cb_t cb, void *ctx);
esp_err_t sg_mqtt_publish_uplink(const char *json, size_t len);
bool sg_mqtt_connected(void);
void sg_mqtt_stop(void);
