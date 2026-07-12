#include "sg_manager_api.h"

#include <limits.h>
#include <math.h>
#include <stdio.h>
#include <string.h>
#include "cJSON.h"
#include "esp_http_server.h"
#include "esp_log.h"
#include "app_config.h"
#include "log_tag.h"

#define SG_MANAGER_API_VERSION 1

static httpd_handle_t s_server;

static bool utf8_valid(const char *value, size_t len)
{
    const unsigned char *p = (const unsigned char *)value;
    if (!p) return false;
    size_t i = 0;
    while (i < len) {
        if (*p <= 0x7F) {
            p++;
            i++;
        } else if (*p >= 0xC2 && *p <= 0xDF) {
            if (i + 1 >= len || (p[1] & 0xC0) != 0x80) return false;
            p += 2;
            i += 2;
        } else if (*p == 0xE0) {
            if (i + 2 >= len || p[1] < 0xA0 || p[1] > 0xBF
                || (p[2] & 0xC0) != 0x80) return false;
            p += 3;
            i += 3;
        } else if ((*p >= 0xE1 && *p <= 0xEC) || (*p >= 0xEE && *p <= 0xEF)) {
            if (i + 2 >= len || (p[1] & 0xC0) != 0x80
                || (p[2] & 0xC0) != 0x80) return false;
            p += 3;
            i += 3;
        } else if (*p == 0xED) {
            if (i + 2 >= len || p[1] < 0x80 || p[1] > 0x9F
                || (p[2] & 0xC0) != 0x80) return false;
            p += 3;
            i += 3;
        } else if (*p == 0xF0) {
            if (i + 3 >= len || p[1] < 0x90 || p[1] > 0xBF
                || (p[2] & 0xC0) != 0x80
                || (p[3] & 0xC0) != 0x80) return false;
            p += 4;
            i += 4;
        } else if (*p >= 0xF1 && *p <= 0xF3) {
            if (i + 3 >= len || (p[1] & 0xC0) != 0x80
                || (p[2] & 0xC0) != 0x80
                || (p[3] & 0xC0) != 0x80) return false;
            p += 4;
            i += 4;
        } else if (*p == 0xF4) {
            if (i + 3 >= len || p[1] < 0x80 || p[1] > 0x8F
                || (p[2] & 0xC0) != 0x80
                || (p[3] & 0xC0) != 0x80) return false;
            p += 4;
            i += 4;
        } else {
            return false;
        }
    }
    return true;
}

static int root_key_bit(const char *key)
{
    if (strcmp(key, "schema_version") == 0) return 1 << 0;
    if (strcmp(key, "expected_revision") == 0) return 1 << 1;
    if (strcmp(key, "profile") == 0) return 1 << 2;
    return 0;
}

static int profile_key_bit(const char *key)
{
    if (strcmp(key, "age") == 0) return 1 << 0;
    if (strcmp(key, "gender") == 0) return 1 << 1;
    if (strcmp(key, "conditions") == 0) return 1 << 2;
    if (strcmp(key, "meds") == 0) return 1 << 3;
    if (strcmp(key, "stroke_history") == 0) return 1 << 4;
    return 0;
}

static bool exact_keys(const cJSON *object, int required,
                       int (*key_bit)(const char *))
{
    int seen = 0;
    const cJSON *field = NULL;
    cJSON_ArrayForEach(field, object) {
        int bit = field->string ? key_bit(field->string) : 0;
        if (bit == 0 || (seen & bit) != 0) return false;
        seen |= bit;
    }
    return seen == required;
}

static bool json_uint32(const cJSON *item, uint32_t min_value, uint32_t *out)
{
    if (!cJSON_IsNumber(item) || !isfinite(item->valuedouble)
        || floor(item->valuedouble) != item->valuedouble
        || item->valuedouble < (double)min_value
        || item->valuedouble > (double)UINT32_MAX) return false;
    *out = (uint32_t)item->valuedouble;
    return true;
}

static bool parse_items(const cJSON *array,
                        char out[SG_PROFILE_ITEM_MAX][SG_PROFILE_TEXT_MAX + 1],
                        uint8_t *count)
{
    if (!cJSON_IsArray(array)) return false;
    int size = cJSON_GetArraySize(array);
    if (size < 0 || size > SG_PROFILE_ITEM_MAX) return false;
    for (int i = 0; i < size; ++i) {
        const cJSON *item = cJSON_GetArrayItem(array, i);
        if (!cJSON_IsString(item) || !item->valuestring) return false;
        size_t len = strlen(item->valuestring);
        if (len == 0 || len > SG_PROFILE_TEXT_MAX
            || !utf8_valid(item->valuestring, len)) return false;
        memcpy(out[i], item->valuestring, len + 1);
    }
    *count = (uint8_t)size;
    return true;
}

sg_manager_parse_err_t sg_manager_parse_profile_patch(
    const char *json, size_t len, uint32_t *expected_revision,
    sg_profile_patch_t *patch)
{
    if (!json || !expected_revision || !patch || len == 0) return SG_MANAGER_INVALID_FIELD;
    if (len > SG_MANAGER_BODY_MAX) return SG_MANAGER_TOO_LARGE;
    if (memchr(json, '\0', len) != NULL) return SG_MANAGER_BAD_JSON;

    char input[SG_MANAGER_BODY_MAX + 1];
    memcpy(input, json, len);
    input[len] = '\0';
    if (strstr(input, "\\u0000") != NULL) return SG_MANAGER_INVALID_FIELD;
    const char *end = NULL;
    cJSON *root = cJSON_ParseWithLengthOpts(input, len + 1, &end, true);
    if (!root || !cJSON_IsObject(root)) {
        cJSON_Delete(root);
        return SG_MANAGER_BAD_JSON;
    }

    cJSON *profile = cJSON_GetObjectItemCaseSensitive(root, "profile");
    if (!exact_keys(root, 0x07, root_key_bit) || !cJSON_IsObject(profile)
        || !exact_keys(profile, 0x1F, profile_key_bit)) {
        cJSON_Delete(root);
        return SG_MANAGER_INVALID_FIELD;
    }

    uint32_t version_value = 0, revision_value = 0, age_value = 0;
    cJSON *version = cJSON_GetObjectItemCaseSensitive(root, "schema_version");
    cJSON *revision = cJSON_GetObjectItemCaseSensitive(root, "expected_revision");
    cJSON *age = cJSON_GetObjectItemCaseSensitive(profile, "age");
    cJSON *gender = cJSON_GetObjectItemCaseSensitive(profile, "gender");
    cJSON *conditions = cJSON_GetObjectItemCaseSensitive(profile, "conditions");
    cJSON *meds = cJSON_GetObjectItemCaseSensitive(profile, "meds");
    cJSON *history = cJSON_GetObjectItemCaseSensitive(profile, "stroke_history");
    sg_profile_patch_t parsed = { 0 };
    bool valid = json_uint32(version, 1, &version_value) && version_value == 1
        && json_uint32(revision, 1, &revision_value)
        && json_uint32(age, 0, &age_value) && age_value <= 130
        && cJSON_IsString(gender) && gender->valuestring
        && (strcmp(gender->valuestring, "M") == 0
            || strcmp(gender->valuestring, "F") == 0
            || strcmp(gender->valuestring, "other") == 0)
        && cJSON_IsBool(history);
    if (valid) {
        parsed.age = (uint8_t)age_value;
        strlcpy(parsed.gender, gender->valuestring, sizeof(parsed.gender));
        parsed.stroke_history = cJSON_IsTrue(history);
        valid = parse_items(conditions, parsed.conditions, &parsed.condition_count)
            && parse_items(meds, parsed.meds, &parsed.med_count);
    }
    cJSON_Delete(root);
    if (!valid) return SG_MANAGER_INVALID_FIELD;
    *expected_revision = revision_value;
    *patch = parsed;
    return SG_MANAGER_OK;
}

bool sg_manager_token_equal(const char *expected, const char *provided)
{
    if (!expected || !provided) return false;
    size_t a = strnlen(expected, SG_MANAGER_TOKEN_MAX + 1);
    size_t b = strnlen(provided, SG_MANAGER_TOKEN_MAX + 1);
    unsigned diff = (unsigned)(a ^ b);
    for (size_t i = 0; i < SG_MANAGER_TOKEN_MAX; ++i) {
        unsigned char x = i < a ? (unsigned char)expected[i] : 0;
        unsigned char y = i < b ? (unsigned char)provided[i] : 0;
        diff |= x ^ y;
    }
    return diff == 0 && a > 0 && a <= SG_MANAGER_TOKEN_MAX;
}

static bool add_items(cJSON *parent, const char *name,
                      const char items[SG_PROFILE_ITEM_MAX][SG_PROFILE_TEXT_MAX + 1],
                      uint8_t count)
{
    if (count > SG_PROFILE_ITEM_MAX) return false;
    cJSON *array = cJSON_AddArrayToObject(parent, name);
    if (!array) return false;
    for (uint8_t i = 0; i < count; ++i) {
        size_t len = strnlen(items[i], SG_PROFILE_TEXT_MAX + 1);
        if (len == 0 || len > SG_PROFILE_TEXT_MAX
            || !utf8_valid(items[i], len)) return false;
        cJSON *item = cJSON_CreateString(items[i]);
        if (!item || !cJSON_AddItemToArray(array, item)) {
            cJSON_Delete(item);
            return false;
        }
    }
    return true;
}

int sg_manager_build_config_json(char *buf, size_t cap, const sg_device_config_t *cfg)
{
    if (!buf || !cfg || cap == 0 || cap > INT_MAX) return -1;
    cJSON *root = cJSON_CreateObject();
    if (!root) return -1;
    bool ok = cJSON_AddNumberToObject(root, "schema_version", 1) != NULL
        && cJSON_AddNumberToObject(root, "revision", cfg->revision)
        && cJSON_AddStringToObject(root, "device_id", cfg->device_id);
    cJSON *profile = ok ? cJSON_AddObjectToObject(root, "profile") : NULL;
    ok = ok && profile && cJSON_AddNumberToObject(profile, "age", cfg->age)
        && cJSON_AddStringToObject(profile, "gender", cfg->gender)
        && add_items(profile, "conditions", cfg->conditions, cfg->condition_count)
        && add_items(profile, "meds", cfg->meds, cfg->med_count)
        && cJSON_AddBoolToObject(profile, "stroke_history", cfg->stroke_history);
    cJSON *readonly = ok ? cJSON_AddObjectToObject(root, "readonly") : NULL;
    ok = ok && readonly
        && cJSON_AddNumberToObject(readonly, "face_danger", SG_FACE_DANGER_MAX)
        && cJSON_AddNumberToObject(readonly, "mouth_angle_danger_deg", SG_FACE_MOUTH_DEG_DANGER)
        && cJSON_AddNumberToObject(readonly, "speech_danger", SG_SPEECH_DANGER_MAX);
    cJSON *capabilities = ok ? cJSON_AddArrayToObject(root, "capabilities") : NULL;
    cJSON *capability = capabilities ? cJSON_CreateString("profile_write") : NULL;
    bool capability_added = capability
        && cJSON_AddItemToArray(capabilities, capability);
    if (!capability_added) cJSON_Delete(capability);
    ok = ok && capabilities && capability_added;
    if (!ok || !cJSON_PrintPreallocated(root, buf, (int)cap, false)) {
        cJSON_Delete(root);
        return -1;
    }
    int length = (int)strlen(buf);
    cJSON_Delete(root);
    return length;
}

static esp_err_t send_json(httpd_req_t *req, const char *status,
                           const char *body, size_t len)
{
    httpd_resp_set_status(req, status);
    httpd_resp_set_type(req, "application/json");
    httpd_resp_set_hdr(req, "Cache-Control", "no-store");
    return httpd_resp_send(req, body, (ssize_t)len);
}

static esp_err_t send_error(httpd_req_t *req, const char *status, const char *code)
{
    char body[96];
    int n = snprintf(body, sizeof(body), "{\"error\":\"%s\"}", code);
    return send_json(req, status, body, n > 0 ? (size_t)n : 0);
}

static bool authorized(httpd_req_t *req, const sg_device_config_t *cfg)
{
    size_t length = httpd_req_get_hdr_value_len(req, "Authorization");
    if (length <= 7 || length >= SG_MANAGER_AUTH_MAX) return false;
    char auth[SG_MANAGER_AUTH_MAX];
    if (httpd_req_get_hdr_value_str(req, "Authorization", auth, sizeof(auth)) != ESP_OK
        || strncmp(auth, "Bearer ", 7) != 0) return false;
    return sg_manager_token_equal(cfg->manager_token, auth + 7);
}

static esp_err_t get_config(httpd_req_t *req)
{
    sg_device_config_t cfg;
    if (sg_device_config_snapshot(&cfg) != ESP_OK)
        return send_error(req, "500 Internal Server Error", "config_unavailable");
    if (!authorized(req, &cfg)) return send_error(req, "401 Unauthorized", "unauthorized");
    char response[SG_MANAGER_RESPONSE_MAX];
    int len = sg_manager_build_config_json(response, sizeof(response), &cfg);
    if (len <= 0) return send_error(req, "500 Internal Server Error", "response_failed");
    ESP_LOGI(SG_TAG_MANAGER, "GET config status=200 device=%s", cfg.device_id);
    return send_json(req, "200 OK", response, (size_t)len);
}

static bool content_type_json(httpd_req_t *req)
{
    char value[32];
    size_t len = httpd_req_get_hdr_value_len(req, "Content-Type");
    return len == strlen("application/json")
        && httpd_req_get_hdr_value_str(req, "Content-Type", value, sizeof(value)) == ESP_OK
        && strcmp(value, "application/json") == 0;
}

static esp_err_t put_config(httpd_req_t *req)
{
    sg_device_config_t cfg;
    if (sg_device_config_snapshot(&cfg) != ESP_OK)
        return send_error(req, "500 Internal Server Error", "config_unavailable");
    if (!authorized(req, &cfg)) return send_error(req, "401 Unauthorized", "unauthorized");
    if (!content_type_json(req)) return send_error(req, "415 Unsupported Media Type", "content_type");
    if (httpd_req_get_hdr_value_len(req, "Transfer-Encoding") > 0
        || req->content_len > SG_MANAGER_BODY_MAX)
        return send_error(req, "413 Content Too Large", "body_too_large");
    if (req->content_len <= 0) return send_error(req, "422 Unprocessable Content", "invalid_body");

    char body[SG_MANAGER_BODY_MAX + 1];
    size_t offset = 0;
    unsigned timeout_count = 0;
    while (offset < (size_t)req->content_len) {
        int received = httpd_req_recv(req, body + offset, (size_t)req->content_len - offset);
        if (received == HTTPD_SOCK_ERR_TIMEOUT && timeout_count++ < 2) {
            continue;
        }
        if (received <= 0) return send_error(req, "422 Unprocessable Content", "invalid_body");
        offset += (size_t)received;
    }

    uint32_t expected_revision = 0;
    sg_profile_patch_t patch;
    sg_manager_parse_err_t parsed = sg_manager_parse_profile_patch(
        body, offset, &expected_revision, &patch);
    if (parsed == SG_MANAGER_TOO_LARGE)
        return send_error(req, "413 Content Too Large", "body_too_large");
    if (parsed != SG_MANAGER_OK)
        return send_error(req, "422 Unprocessable Content", "invalid_body");

    sg_device_config_t updated;
    esp_err_t err = sg_device_config_apply_profile(expected_revision, &patch, &updated);
    if (err == ESP_ERR_INVALID_STATE)
        return send_error(req, "409 Conflict", "revision_conflict");
    if (err == ESP_ERR_INVALID_ARG)
        return send_error(req, "422 Unprocessable Content", "invalid_profile");
    if (err != ESP_OK) return send_error(req, "500 Internal Server Error", "persist_failed");

    char response[SG_MANAGER_RESPONSE_MAX];
    int len = sg_manager_build_config_json(response, sizeof(response), &updated);
    if (len <= 0) return send_error(req, "500 Internal Server Error", "response_failed");
    ESP_LOGI(SG_TAG_MANAGER, "PUT config status=200 device=%s", updated.device_id);
    return send_json(req, "200 OK", response, (size_t)len);
}

esp_err_t sg_manager_api_start(void)
{
    if (s_server) return ESP_OK;
    sg_device_config_t cfg;
    esp_err_t err = sg_device_config_snapshot(&cfg);
    if (err != ESP_OK) return err;
    if (!sg_device_config_manager_ready(&cfg)) return ESP_ERR_INVALID_STATE;
    httpd_config_t server_config = HTTPD_DEFAULT_CONFIG();
    server_config.server_port = cfg.manager_port;
    server_config.max_uri_handlers = 2;
    server_config.stack_size = SG_MANAGER_TASK_STACK;
    err = httpd_start(&s_server, &server_config);
    if (err != ESP_OK) return err;
    const httpd_uri_t get_uri = {
        .uri = "/api/v1/config", .method = HTTP_GET, .handler = get_config,
    };
    const httpd_uri_t put_uri = {
        .uri = "/api/v1/config", .method = HTTP_PUT, .handler = put_config,
    };
    err = httpd_register_uri_handler(s_server, &get_uri);
    if (err == ESP_OK) err = httpd_register_uri_handler(s_server, &put_uri);
    if (err != ESP_OK) {
        httpd_stop(s_server);
        s_server = NULL;
        return err;
    }
    ESP_LOGI(SG_TAG_MANAGER, "manager API started port=%u", cfg.manager_port);
    return ESP_OK;
}
