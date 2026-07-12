#include "device_config.h"

#include <limits.h>
#include <stddef.h>
#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "esp_crc.h"
#include "esp_log.h"
#include "nvs.h"
#include "sdkconfig.h"
#include "log_tag.h"

#define SG_CONFIG_KEY       "device"

typedef struct {
    uint32_t schema_version;
    char device_id[SG_DEVICE_ID_MAX + 1];
    char mqtt_uri[SG_MQTT_URI_MAX + 1];
    char mqtt_user[SG_MQTT_USER_MAX + 1];
    char mqtt_pass[SG_MQTT_PASS_MAX + 1];
    uint8_t age;
    char gender[6];
    bool stroke_history;
    uint8_t condition_count;
    char conditions[SG_PROFILE_ITEM_MAX][SG_PROFILE_TEXT_MAX + 1];
    uint8_t med_count;
    char meds[SG_PROFILE_ITEM_MAX][SG_PROFILE_TEXT_MAX + 1];
    uint32_t crc32;
} sg_device_config_v1_t;

static SemaphoreHandle_t s_config_mutex;
static sg_device_config_t s_current;
static bool s_loaded;

static uint32_t config_crc(const sg_device_config_t *cfg)
{
    return esp_crc32_le(0, (const uint8_t *)cfg,
                        (uint32_t)offsetof(sg_device_config_t, crc32));
}

static uint32_t config_v1_crc(const sg_device_config_v1_t *cfg)
{
    return esp_crc32_le(0, (const uint8_t *)cfg,
                        (uint32_t)offsetof(sg_device_config_v1_t, crc32));
}

static bool terminated(const char *value, size_t cap)
{
    return value && memchr(value, '\0', cap) != NULL;
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

static bool gender_valid(const char *value)
{
    return value && (strcmp(value, "M") == 0
        || strcmp(value, "F") == 0
        || strcmp(value, "other") == 0);
}

static bool profile_items_valid(
    const char items[SG_PROFILE_ITEM_MAX][SG_PROFILE_TEXT_MAX + 1],
    uint8_t count)
{
    if (count > SG_PROFILE_ITEM_MAX) return false;
    for (uint8_t i = 0; i < count; ++i) {
        if (!terminated(items[i], SG_PROFILE_TEXT_MAX + 1) || !items[i][0]) {
            return false;
        }
    }
    return true;
}

static bool profile_fields_valid(
    uint8_t age, const char *gender,
    const char conditions[SG_PROFILE_ITEM_MAX][SG_PROFILE_TEXT_MAX + 1],
    uint8_t condition_count,
    const char meds[SG_PROFILE_ITEM_MAX][SG_PROFILE_TEXT_MAX + 1],
    uint8_t med_count)
{
    return age <= 130
        && terminated(gender, 6)
        && gender_valid(gender)
        && profile_items_valid(conditions, condition_count)
        && profile_items_valid(meds, med_count);
}

static bool config_valid(const sg_device_config_t *cfg)
{
    if (!cfg || cfg->schema_version != SG_DEVICE_CONFIG_VERSION
        || cfg->revision == 0 || cfg->manager_port == 0) {
        return false;
    }
    if (!terminated(cfg->device_id, sizeof(cfg->device_id))
        || !terminated(cfg->mqtt_uri, sizeof(cfg->mqtt_uri))
        || !terminated(cfg->mqtt_user, sizeof(cfg->mqtt_user))
        || !terminated(cfg->mqtt_pass, sizeof(cfg->mqtt_pass))
        || !terminated(cfg->manager_token, sizeof(cfg->manager_token))) {
        return false;
    }
    if (!device_id_valid(cfg->device_id) || !mqtt_uri_valid(cfg->mqtt_uri)) {
        return false;
    }
    if (!profile_fields_valid(
            cfg->age, cfg->gender, cfg->conditions, cfg->condition_count,
            cfg->meds, cfg->med_count)) {
        return false;
    }
    return cfg->crc32 == config_crc(cfg);
}

static bool config_v1_valid(const sg_device_config_v1_t *cfg)
{
    if (!cfg || cfg->schema_version != 1U) return false;
    if (!terminated(cfg->device_id, sizeof(cfg->device_id))
        || !terminated(cfg->mqtt_uri, sizeof(cfg->mqtt_uri))
        || !terminated(cfg->mqtt_user, sizeof(cfg->mqtt_user))
        || !terminated(cfg->mqtt_pass, sizeof(cfg->mqtt_pass))) {
        return false;
    }
    return device_id_valid(cfg->device_id)
        && mqtt_uri_valid(cfg->mqtt_uri)
        && profile_fields_valid(
            cfg->age, cfg->gender, cfg->conditions, cfg->condition_count,
            cfg->meds, cfg->med_count)
        && cfg->crc32 == config_v1_crc(cfg);
}

static bool patch_valid(const sg_profile_patch_t *patch)
{
    return patch && profile_fields_valid(
        patch->age, patch->gender,
        patch->conditions, patch->condition_count,
        patch->meds, patch->med_count);
}

static void copy_text(char *dst, size_t cap, const char *src)
{
    if (!dst || cap == 0) return;
    strlcpy(dst, src ? src : "", cap);
}

static void factory_defaults(sg_device_config_t *cfg)
{
    memset(cfg, 0, sizeof(*cfg));
    cfg->schema_version = SG_DEVICE_CONFIG_VERSION;
    cfg->revision = 1;
    copy_text(cfg->device_id, sizeof(cfg->device_id),
              CONFIG_STROKEGUARD_DEVICE_ID);
    copy_text(cfg->mqtt_uri, sizeof(cfg->mqtt_uri),
              CONFIG_STROKEGUARD_MQTT_URI);
    copy_text(cfg->mqtt_user, sizeof(cfg->mqtt_user),
              CONFIG_STROKEGUARD_MQTT_USERNAME);
    copy_text(cfg->mqtt_pass, sizeof(cfg->mqtt_pass),
              CONFIG_STROKEGUARD_MQTT_PASSWORD);
    cfg->manager_port = (uint16_t)CONFIG_STROKEGUARD_MANAGER_PORT;
    copy_text(cfg->manager_token, sizeof(cfg->manager_token),
              CONFIG_STROKEGUARD_MANAGER_TOKEN);
    cfg->age = (uint8_t)CONFIG_STROKEGUARD_PROFILE_AGE;
    copy_text(cfg->gender, sizeof(cfg->gender),
              CONFIG_STROKEGUARD_PROFILE_GENDER);
    cfg->crc32 = config_crc(cfg);
}

static void migrate_v1(const sg_device_config_v1_t *old,
                       sg_device_config_t *cfg)
{
    memset(cfg, 0, sizeof(*cfg));
    cfg->schema_version = SG_DEVICE_CONFIG_VERSION;
    cfg->revision = 1;
    copy_text(cfg->device_id, sizeof(cfg->device_id), old->device_id);
    copy_text(cfg->mqtt_uri, sizeof(cfg->mqtt_uri), old->mqtt_uri);
    copy_text(cfg->mqtt_user, sizeof(cfg->mqtt_user), old->mqtt_user);
    copy_text(cfg->mqtt_pass, sizeof(cfg->mqtt_pass), old->mqtt_pass);
    cfg->manager_port = (uint16_t)CONFIG_STROKEGUARD_MANAGER_PORT;
    copy_text(cfg->manager_token, sizeof(cfg->manager_token),
              CONFIG_STROKEGUARD_MANAGER_TOKEN);
    cfg->age = old->age;
    copy_text(cfg->gender, sizeof(cfg->gender), old->gender);
    cfg->stroke_history = old->stroke_history;
    cfg->condition_count = old->condition_count;
    memcpy(cfg->conditions, old->conditions, sizeof(cfg->conditions));
    cfg->med_count = old->med_count;
    memcpy(cfg->meds, old->meds, sizeof(cfg->meds));
    cfg->crc32 = config_crc(cfg);
}

static esp_err_t persist(nvs_handle_t handle, const sg_device_config_t *cfg)
{
    esp_err_t err = nvs_set_blob(handle, SG_CONFIG_KEY, cfg, sizeof(*cfg));
    if (err != ESP_OK) return err;
    return nvs_commit(handle);
}

static esp_err_t load_from_nvs(nvs_handle_t handle, sg_device_config_t *out)
{
    size_t size = 0;
    esp_err_t err = nvs_get_blob(handle, SG_CONFIG_KEY, NULL, &size);
    if (err == ESP_OK && size == sizeof(*out)) {
        size_t actual = sizeof(*out);
        err = nvs_get_blob(handle, SG_CONFIG_KEY, out, &actual);
        if (err == ESP_OK && actual == sizeof(*out) && config_valid(out)) {
            return ESP_OK;
        }
    } else if (err == ESP_OK && size == sizeof(sg_device_config_v1_t)) {
        sg_device_config_v1_t old;
        memset(&old, 0, sizeof(old));
        size_t actual = sizeof(old);
        err = nvs_get_blob(handle, SG_CONFIG_KEY, &old, &actual);
        if (err == ESP_OK && actual == sizeof(old) && config_v1_valid(&old)) {
            migrate_v1(&old, out);
            ESP_LOGI(SG_TAG_MAIN, "device config migrated v1->v2");
            return persist(handle, out);
        }
    }

    if (err != ESP_ERR_NVS_NOT_FOUND && err != ESP_OK) {
        ESP_LOGW(SG_TAG_MAIN, "device config unreadable err=%s; using defaults",
                 esp_err_to_name(err));
    } else if (err == ESP_OK) {
        ESP_LOGW(SG_TAG_MAIN, "device config invalid; using defaults");
    }
    factory_defaults(out);
    if (!config_valid(out)) return ESP_ERR_INVALID_ARG;
    return persist(handle, out);
}

static esp_err_t ensure_mutex(void)
{
    if (s_config_mutex) return ESP_OK;
    s_config_mutex = xSemaphoreCreateMutex();
    return s_config_mutex ? ESP_OK : ESP_ERR_NO_MEM;
}

esp_err_t sg_device_config_load(sg_device_config_t *out)
{
    if (!out) return ESP_ERR_INVALID_ARG;

    nvs_handle_t handle;
    esp_err_t err = nvs_open("sg_cfg", NVS_READWRITE, &handle);
    if (err != ESP_OK) return err;

    sg_device_config_t loaded;
    memset(&loaded, 0, sizeof(loaded));
    err = load_from_nvs(handle, &loaded);
    nvs_close(handle);
    if (err != ESP_OK) return err;

    err = ensure_mutex();
    if (err != ESP_OK) return err;
    if (xSemaphoreTake(s_config_mutex, portMAX_DELAY) != pdTRUE) {
        return ESP_ERR_TIMEOUT;
    }
    s_current = loaded;
    s_loaded = true;
    *out = loaded;
    xSemaphoreGive(s_config_mutex);
    return ESP_OK;
}

esp_err_t sg_device_config_snapshot(sg_device_config_t *out)
{
    if (!out) return ESP_ERR_INVALID_ARG;
    if (!s_config_mutex || !s_loaded) return ESP_ERR_INVALID_STATE;
    if (xSemaphoreTake(s_config_mutex, portMAX_DELAY) != pdTRUE) {
        return ESP_ERR_TIMEOUT;
    }
    *out = s_current;
    xSemaphoreGive(s_config_mutex);
    return ESP_OK;
}

esp_err_t sg_device_config_apply_profile(uint32_t expected_revision,
                                         const sg_profile_patch_t *patch,
                                         sg_device_config_t *updated)
{
    if (!patch_valid(patch)) return ESP_ERR_INVALID_ARG;
    if (!s_config_mutex || !s_loaded) return ESP_ERR_INVALID_STATE;
    if (xSemaphoreTake(s_config_mutex, portMAX_DELAY) != pdTRUE) {
        return ESP_ERR_TIMEOUT;
    }

    if (s_current.revision != expected_revision
        || s_current.revision == UINT32_MAX) {
        xSemaphoreGive(s_config_mutex);
        return ESP_ERR_INVALID_STATE;
    }

    sg_device_config_t candidate = s_current;
    candidate.revision++;
    candidate.age = patch->age;
    copy_text(candidate.gender, sizeof(candidate.gender), patch->gender);
    candidate.stroke_history = patch->stroke_history;
    candidate.condition_count = patch->condition_count;
    memset(candidate.conditions, 0, sizeof(candidate.conditions));
    memcpy(candidate.conditions, patch->conditions,
           sizeof(candidate.conditions));
    candidate.med_count = patch->med_count;
    memset(candidate.meds, 0, sizeof(candidate.meds));
    memcpy(candidate.meds, patch->meds, sizeof(candidate.meds));
    candidate.crc32 = config_crc(&candidate);
    if (!config_valid(&candidate)) {
        xSemaphoreGive(s_config_mutex);
        return ESP_ERR_INVALID_ARG;
    }

    nvs_handle_t handle;
    esp_err_t err = nvs_open("sg_cfg", NVS_READWRITE, &handle);
    if (err == ESP_OK) {
        err = persist(handle, &candidate);
        nvs_close(handle);
    }
    if (err == ESP_OK) {
        s_current = candidate;
        if (updated) *updated = candidate;
    }
    xSemaphoreGive(s_config_mutex);
    return err;
}

bool sg_device_config_mqtt_ready(const sg_device_config_t *cfg)
{
    return cfg && config_valid(cfg)
        && cfg->mqtt_uri[0]
        && cfg->mqtt_user[0]
        && cfg->mqtt_pass[0];
}

bool sg_device_config_manager_ready(const sg_device_config_t *cfg)
{
    return cfg && config_valid(cfg)
        && cfg->manager_port > 0
        && cfg->manager_token[0];
}
