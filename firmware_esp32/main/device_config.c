#include "device_config.h"

#include <stddef.h>
#include <string.h>
#include "esp_crc.h"
#include "esp_log.h"
#include "nvs.h"
#include "sdkconfig.h"
#include "log_tag.h"

#define SG_CONFIG_NAMESPACE "sg_cfg"
#define SG_CONFIG_KEY       "device"

static uint32_t config_crc(const sg_device_config_t *cfg)
{
    return esp_crc32_le(0, (const uint8_t *)cfg,
                        (uint32_t)offsetof(sg_device_config_t, crc32));
}

static bool terminated(const char *value, size_t cap)
{
    return memchr(value, '\0', cap) != NULL;
}

static bool device_id_valid(const char *value)
{
    if (!value || !value[0]) return false;
    for (const unsigned char *p = (const unsigned char *)value; *p; ++p) {
        bool ok = (*p >= 'a' && *p <= 'z')
               || (*p >= 'A' && *p <= 'Z')
               || (*p >= '0' && *p <= '9')
               || *p == '_' || *p == '-';
        if (!ok) return false;
    }
    return true;
}

static bool mqtt_uri_valid(const char *value)
{
    if (!value || !value[0]) return true;
    return strncmp(value, "mqtt://", 7) == 0
        || strncmp(value, "mqtts://", 8) == 0;
}

static bool profile_items_valid(
    char items[SG_PROFILE_ITEM_MAX][SG_PROFILE_TEXT_MAX + 1], uint8_t count)
{
    if (count > SG_PROFILE_ITEM_MAX) return false;
    for (uint8_t i = 0; i < count; ++i) {
        if (!terminated(items[i], SG_PROFILE_TEXT_MAX + 1) || !items[i][0]) {
            return false;
        }
    }
    return true;
}

static bool config_valid(const sg_device_config_t *cfg)
{
    if (!cfg || cfg->schema_version != SG_DEVICE_CONFIG_VERSION) return false;
    if (!terminated(cfg->device_id, sizeof(cfg->device_id))
        || !terminated(cfg->mqtt_uri, sizeof(cfg->mqtt_uri))
        || !terminated(cfg->mqtt_user, sizeof(cfg->mqtt_user))
        || !terminated(cfg->mqtt_pass, sizeof(cfg->mqtt_pass))
        || !terminated(cfg->gender, sizeof(cfg->gender))) {
        return false;
    }
    if (!device_id_valid(cfg->device_id) || !mqtt_uri_valid(cfg->mqtt_uri)) {
        return false;
    }
    if (cfg->age > 130) return false;
    if (strcmp(cfg->gender, "M") != 0
        && strcmp(cfg->gender, "F") != 0
        && strcmp(cfg->gender, "other") != 0) {
        return false;
    }
    if (!profile_items_valid((char (*)[SG_PROFILE_TEXT_MAX + 1])cfg->conditions,
                             cfg->condition_count)
        || !profile_items_valid((char (*)[SG_PROFILE_TEXT_MAX + 1])cfg->meds,
                                cfg->med_count)) {
        return false;
    }
    return cfg->crc32 == config_crc(cfg);
}

static void copy_text(char *dst, size_t cap, const char *src)
{
    if (!dst || cap == 0) return;
    if (!src) src = "";
    strlcpy(dst, src, cap);
}

static void factory_defaults(sg_device_config_t *cfg)
{
    memset(cfg, 0, sizeof(*cfg));
    cfg->schema_version = SG_DEVICE_CONFIG_VERSION;
    copy_text(cfg->device_id, sizeof(cfg->device_id),
              CONFIG_STROKEGUARD_DEVICE_ID);
    copy_text(cfg->mqtt_uri, sizeof(cfg->mqtt_uri),
              CONFIG_STROKEGUARD_MQTT_URI);
    copy_text(cfg->mqtt_user, sizeof(cfg->mqtt_user),
              CONFIG_STROKEGUARD_MQTT_USERNAME);
    copy_text(cfg->mqtt_pass, sizeof(cfg->mqtt_pass),
              CONFIG_STROKEGUARD_MQTT_PASSWORD);
    cfg->age = (uint8_t)CONFIG_STROKEGUARD_PROFILE_AGE;
    copy_text(cfg->gender, sizeof(cfg->gender),
              CONFIG_STROKEGUARD_PROFILE_GENDER);
    cfg->crc32 = config_crc(cfg);
}

static esp_err_t persist(nvs_handle_t handle, const sg_device_config_t *cfg)
{
    esp_err_t err = nvs_set_blob(handle, SG_CONFIG_KEY, cfg, sizeof(*cfg));
    if (err != ESP_OK) return err;
    return nvs_commit(handle);
}

esp_err_t sg_device_config_load(sg_device_config_t *out)
{
    if (!out) return ESP_ERR_INVALID_ARG;

    nvs_handle_t handle;
    esp_err_t err = nvs_open("sg_cfg", NVS_READWRITE, &handle);
    if (err != ESP_OK) return err;

    sg_device_config_t stored;
    memset(&stored, 0, sizeof(stored));
    size_t size = sizeof(stored);
    err = nvs_get_blob(handle, "device", &stored, &size);
    if (err == ESP_OK && size == sizeof(stored) && config_valid(&stored)) {
        *out = stored;
        nvs_close(handle);
        return ESP_OK;
    }

    if (err != ESP_ERR_NVS_NOT_FOUND && err != ESP_OK) {
        ESP_LOGW(SG_TAG_MAIN, "device config unreadable err=%s; using defaults",
                 esp_err_to_name(err));
    } else if (err == ESP_OK) {
        ESP_LOGW(SG_TAG_MAIN, "device config invalid; using defaults");
    }

    factory_defaults(out);
    if (!config_valid(out)) {
        nvs_close(handle);
        return ESP_ERR_INVALID_ARG;
    }
    err = persist(handle, out);
    nvs_close(handle);
    return err;
}

bool sg_device_config_mqtt_ready(const sg_device_config_t *cfg)
{
    return cfg && config_valid(cfg)
        && cfg->mqtt_uri[0]
        && cfg->mqtt_user[0]
        && cfg->mqtt_pass[0];
}
