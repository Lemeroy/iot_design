#pragma once

#include <stdbool.h>
#include <stdint.h>
#include "esp_err.h"

#define SG_DEVICE_CONFIG_VERSION 2U
#define SG_DEVICE_ID_MAX         32
#define SG_MQTT_URI_MAX          127
#define SG_MQTT_USER_MAX         63
#define SG_MQTT_PASS_MAX         95
#define SG_MANAGER_TOKEN_MAX     64
#define SG_PROFILE_ITEM_MAX      4
#define SG_PROFILE_TEXT_MAX      31

typedef struct {
    uint8_t age;
    char gender[6];
    bool stroke_history;
    uint8_t condition_count;
    char conditions[SG_PROFILE_ITEM_MAX][SG_PROFILE_TEXT_MAX + 1];
    uint8_t med_count;
    char meds[SG_PROFILE_ITEM_MAX][SG_PROFILE_TEXT_MAX + 1];
} sg_profile_patch_t;

typedef struct {
    uint32_t schema_version;
    uint32_t revision;
    char device_id[SG_DEVICE_ID_MAX + 1];
    char mqtt_uri[SG_MQTT_URI_MAX + 1];
    char mqtt_user[SG_MQTT_USER_MAX + 1];
    char mqtt_pass[SG_MQTT_PASS_MAX + 1];
    uint16_t manager_port;
    char manager_token[SG_MANAGER_TOKEN_MAX + 1];
    uint8_t age;
    char gender[6];
    bool stroke_history;
    uint8_t condition_count;
    char conditions[SG_PROFILE_ITEM_MAX][SG_PROFILE_TEXT_MAX + 1];
    uint8_t med_count;
    char meds[SG_PROFILE_ITEM_MAX][SG_PROFILE_TEXT_MAX + 1];
    uint32_t crc32;
} sg_device_config_t;

esp_err_t sg_device_config_load(sg_device_config_t *out);
esp_err_t sg_device_config_snapshot(sg_device_config_t *out);
esp_err_t sg_device_config_apply_profile(uint32_t expected_revision,
                                         const sg_profile_patch_t *patch,
                                         sg_device_config_t *updated);
bool sg_device_config_mqtt_ready(const sg_device_config_t *cfg);
bool sg_device_config_manager_ready(const sg_device_config_t *cfg);
