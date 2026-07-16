#include "cloud_contract.h"

#include <math.h>
#include <stdbool.h>
#include <string.h>
#include "cJSON.h"

static bool score_or_missing(int value)
{
    return value == -1 || (value >= 0 && value <= 100);
}

static bool add_score(cJSON *parent, const char *name, int value)
{
    cJSON *item = value < 0 ? cJSON_CreateNull() : cJSON_CreateNumber(value);
    if (!item) return false;
    if (!cJSON_AddItemToObject(parent, name, item)) {
        cJSON_Delete(item);
        return false;
    }
    return true;
}

static bool add_profile_items(cJSON *parent, const char *name,
                              char items[SG_PROFILE_ITEM_MAX][SG_PROFILE_TEXT_MAX + 1],
                              uint8_t count)
{
    if (count > SG_PROFILE_ITEM_MAX) return false;
    cJSON *array = cJSON_AddArrayToObject(parent, name);
    if (!array) return false;
    for (uint8_t i = 0; i < count; ++i) {
        size_t len = strnlen(items[i], SG_PROFILE_TEXT_MAX + 1);
        if (len == 0 || len > SG_PROFILE_TEXT_MAX) return false;
        cJSON *item = cJSON_CreateString(items[i]);
        if (!item || !cJSON_AddItemToArray(array, item)) {
            cJSON_Delete(item);
            return false;
        }
    }
    return true;
}

int sg_cloud_build_uplink(char *buf, size_t cap,
                          const sg_device_config_t *cfg,
                          const sg_scores_in_t *scores,
                          const sg_fusion_out_t *fusion,
                          sg_screening_stage_t screening_stage,
                          int64_t unix_ts, uint32_t seq)
{
    if (!buf || !cfg || !scores || !fusion || cap == 0
        || cap > INT32_MAX || !cfg->device_id[0] || unix_ts < 0
        || !score_or_missing(scores->face)
        || !score_or_missing(scores->speech)
        || !score_or_missing(scores->tongue)
        || !score_or_missing(scores->eye)
        || !score_or_missing(scores->csi)
        || fusion->final < 0 || fusion->final > 100
        || fusion->n_reasons < 0
        || fusion->n_reasons > SG_FUSION_MAX_REASONS
        || screening_stage > SG_STAGE_ERROR) {
        return -1;
    }

    cJSON *root = cJSON_CreateObject();
    cJSON *score_obj = NULL;
    cJSON *profile = NULL;
    cJSON *reasons = NULL;
    cJSON *veto = NULL;
    if (!root) return -1;

    bool ok = cJSON_AddNumberToObject(root, "schema_version", 1) != NULL;
    score_obj = ok ? cJSON_AddObjectToObject(root, "scores") : NULL;
    ok = ok && score_obj
        && add_score(score_obj, "face", scores->face)
        && add_score(score_obj, "speech", scores->speech)
        && add_score(score_obj, "tongue", scores->tongue)
        && add_score(score_obj, "eye", scores->eye)
        && add_score(score_obj, "csi", scores->csi)
        && cJSON_AddNumberToObject(score_obj, "final", fusion->final);
    ok = ok && cJSON_AddStringToObject(root, "level",
                                       sg_fusion_level_name(fusion->level));

    profile = ok ? cJSON_AddObjectToObject(root, "profile") : NULL;
    ok = ok && profile
        && cJSON_AddNumberToObject(profile, "age", cfg->age)
        && cJSON_AddStringToObject(profile, "gender", cfg->gender)
        && add_profile_items(profile, "conditions",
                             (char (*)[SG_PROFILE_TEXT_MAX + 1])cfg->conditions,
                             cfg->condition_count)
        && add_profile_items(profile, "meds",
                             (char (*)[SG_PROFILE_TEXT_MAX + 1])cfg->meds,
                             cfg->med_count)
        && cJSON_AddBoolToObject(profile, "stroke_history", cfg->stroke_history);

    reasons = ok ? cJSON_AddArrayToObject(root, "reasons") : NULL;
    ok = ok && reasons;
    for (int i = 0; ok && i < fusion->n_reasons; ++i) {
        if (strnlen(fusion->reasons[i], SG_FUSION_REASON_LEN)
            >= SG_FUSION_REASON_LEN) {
            ok = false;
            break;
        }
        cJSON *item = cJSON_CreateString(fusion->reasons[i]);
        ok = item && cJSON_AddItemToArray(reasons, item);
        if (!ok) cJSON_Delete(item);
    }

    veto = ok ? cJSON_AddArrayToObject(root, "veto_by") : NULL;
    ok = ok && veto;
    if (ok && fusion->veto_face) {
        cJSON *item = cJSON_CreateString("face");
        ok = item && cJSON_AddItemToArray(veto, item);
        if (!ok) cJSON_Delete(item);
    }
    if (ok && fusion->veto_speech) {
        cJSON *item = cJSON_CreateString("speech");
        ok = item && cJSON_AddItemToArray(veto, item);
        if (!ok) cJSON_Delete(item);
    }

    ok = ok && cJSON_AddStringToObject(root, "device_id", cfg->device_id)
        && cJSON_AddNumberToObject(root, "screening_stage", screening_stage)
        && cJSON_AddNumberToObject(root, "ts", (double)unix_ts)
        && cJSON_AddNumberToObject(root, "seq", seq);

    if (!ok || !cJSON_PrintPreallocated(root, buf, (int)cap, false)) {
        cJSON_Delete(root);
        return -1;
    }
    int length = (int)strlen(buf);
    cJSON_Delete(root);
    return length;
}

sg_contract_err_t sg_cloud_parse_screening_control(
    const char *json, size_t len, sg_cloud_screening_control_t *out)
{
    if (!json || !out || len == 0) return SG_CONTRACT_INVALID_FIELD;
    if (len > SG_DOWNLINK_MAX) return SG_CONTRACT_TOO_LARGE;
    if (memchr(json, '\0', len) != NULL) return SG_CONTRACT_INVALID_JSON;
    char input[SG_DOWNLINK_MAX + 1];
    memcpy(input, json, len);
    input[len] = '\0';
    const char *end = NULL;
    cJSON *root = cJSON_ParseWithLengthOpts(input, len + 1, &end, true);
    if (!root || !cJSON_IsObject(root) || cJSON_GetArraySize(root) != 2) {
        cJSON_Delete(root);
        return SG_CONTRACT_INVALID_JSON;
    }
    cJSON *type = cJSON_GetObjectItemCaseSensitive(root, "type");
    cJSON *action = cJSON_GetObjectItemCaseSensitive(root, "action");
    if (!cJSON_IsString(type) || !type->valuestring
        || strcmp(type->valuestring, "screening_control") != 0
        || !cJSON_IsString(action) || !action->valuestring) {
        cJSON_Delete(root);
        return SG_CONTRACT_INVALID_FIELD;
    }
    sg_cloud_screening_control_t parsed;
    if (strcmp(action->valuestring, "start") == 0) {
        parsed.action = SG_SCREENING_START;
    } else if (strcmp(action->valuestring, "cancel") == 0) {
        parsed.action = SG_SCREENING_CANCEL;
    } else {
        cJSON_Delete(root);
        return SG_CONTRACT_INVALID_FIELD;
    }
    *out = parsed;
    cJSON_Delete(root);
    return SG_CONTRACT_OK;
}

static bool utf8_valid(const char *value)
{
    const unsigned char *p = (const unsigned char *)value;
    while (*p) {
        if (*p <= 0x7F) {
            p++;
            continue;
        }
        if (*p >= 0xC2 && *p <= 0xDF) {
            if ((p[1] & 0xC0) != 0x80) return false;
            p += 2;
            continue;
        }
        if (*p == 0xE0) {
            if (p[1] < 0xA0 || p[1] > 0xBF || (p[2] & 0xC0) != 0x80) {
                return false;
            }
            p += 3;
            continue;
        }
        if ((*p >= 0xE1 && *p <= 0xEC) || (*p >= 0xEE && *p <= 0xEF)) {
            if ((p[1] & 0xC0) != 0x80 || (p[2] & 0xC0) != 0x80) return false;
            p += 3;
            continue;
        }
        if (*p == 0xED) {
            if (p[1] < 0x80 || p[1] > 0x9F || (p[2] & 0xC0) != 0x80) {
                return false;
            }
            p += 3;
            continue;
        }
        if (*p == 0xF0) {
            if (p[1] < 0x90 || p[1] > 0xBF
                || (p[2] & 0xC0) != 0x80 || (p[3] & 0xC0) != 0x80) {
                return false;
            }
            p += 4;
            continue;
        }
        if (*p >= 0xF1 && *p <= 0xF3) {
            if ((p[1] & 0xC0) != 0x80 || (p[2] & 0xC0) != 0x80
                || (p[3] & 0xC0) != 0x80) {
                return false;
            }
            p += 4;
            continue;
        }
        if (*p == 0xF4) {
            if (p[1] < 0x80 || p[1] > 0x8F
                || (p[2] & 0xC0) != 0x80 || (p[3] & 0xC0) != 0x80) {
                return false;
            }
            p += 4;
            continue;
        }
        return false;
    }
    return true;
}

static int level_from_text(const char *value, sg_level_t *out)
{
    if (strcmp(value, "normal") == 0) *out = SG_LEVEL_NORMAL;
    else if (strcmp(value, "warning") == 0) *out = SG_LEVEL_WARNING;
    else if (strcmp(value, "danger") == 0) *out = SG_LEVEL_DANGER;
    else if (strcmp(value, "insufficient") == 0) *out = SG_LEVEL_INSUFFICIENT;
    else return -1;
    return 0;
}

static int key_bit(const char *key)
{
    if (strcmp(key, "schema_version") == 0) return 1 << 0;
    if (strcmp(key, "level") == 0) return 1 << 1;
    if (strcmp(key, "advice_text") == 0) return 1 << 2;
    if (strcmp(key, "ts") == 0) return 1 << 3;
    if (strcmp(key, "source") == 0) return 1 << 4;
    return 0;
}

sg_contract_err_t sg_cloud_parse_advice(const char *json, size_t len,
                                        sg_cloud_advice_t *out)
{
    if (!json || !out || len == 0) return SG_CONTRACT_INVALID_FIELD;
    if (len > SG_DOWNLINK_MAX) return SG_CONTRACT_TOO_LARGE;
    if (memchr(json, '\0', len) != NULL) return SG_CONTRACT_INVALID_JSON;

    char input[SG_DOWNLINK_MAX + 1];
    memcpy(input, json, len);
    input[len] = '\0';
    if (strstr(input, "\\u0000") != NULL) return SG_CONTRACT_INVALID_FIELD;

    const char *end = NULL;
    cJSON *root = cJSON_ParseWithLengthOpts(input, len + 1, &end, true);
    if (!root || !cJSON_IsObject(root)) {
        cJSON_Delete(root);
        return SG_CONTRACT_INVALID_JSON;
    }

    int seen = 0;
    cJSON *field = NULL;
    cJSON_ArrayForEach(field, root) {
        int bit = field->string ? key_bit(field->string) : 0;
        if (bit == 0 || (seen & bit) != 0) {
            cJSON_Delete(root);
            return SG_CONTRACT_INVALID_FIELD;
        }
        seen |= bit;
    }
    if (seen != 0x1F) {
        cJSON_Delete(root);
        return SG_CONTRACT_INVALID_FIELD;
    }

    cJSON *version = cJSON_GetObjectItemCaseSensitive(root, "schema_version");
    cJSON *level = cJSON_GetObjectItemCaseSensitive(root, "level");
    cJSON *advice = cJSON_GetObjectItemCaseSensitive(root, "advice_text");
    cJSON *timestamp = cJSON_GetObjectItemCaseSensitive(root, "ts");
    cJSON *source = cJSON_GetObjectItemCaseSensitive(root, "source");

    sg_cloud_advice_t parsed;
    memset(&parsed, 0, sizeof(parsed));
    bool valid = cJSON_IsNumber(version) && version->valuedouble == 1.0
        && cJSON_IsString(level) && level->valuestring
        && cJSON_IsString(advice) && advice->valuestring
        && cJSON_IsNumber(timestamp) && isfinite(timestamp->valuedouble)
        && timestamp->valuedouble >= 0.0
        && floor(timestamp->valuedouble) == timestamp->valuedouble
        && cJSON_IsString(source) && source->valuestring;
    if (!valid || level_from_text(level->valuestring, &parsed.level) != 0) {
        cJSON_Delete(root);
        return SG_CONTRACT_INVALID_FIELD;
    }

    size_t advice_len = strlen(advice->valuestring);
    size_t source_len = strlen(source->valuestring);
    if (advice_len == 0 || advice_len > SG_ADVICE_TEXT_MAX
        || source_len == 0 || source_len > SG_ADVICE_SOURCE_MAX) {
        cJSON_Delete(root);
        return SG_CONTRACT_TOO_LARGE;
    }
    if (!utf8_valid(advice->valuestring) || !utf8_valid(source->valuestring)) {
        cJSON_Delete(root);
        return SG_CONTRACT_INVALID_FIELD;
    }

    parsed.ts = (int64_t)timestamp->valuedouble;
    memcpy(parsed.advice_text, advice->valuestring, advice_len + 1);
    memcpy(parsed.source, source->valuestring, source_len + 1);
    *out = parsed;
    cJSON_Delete(root);
    return SG_CONTRACT_OK;
}
