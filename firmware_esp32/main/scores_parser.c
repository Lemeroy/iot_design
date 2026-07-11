/**
 * @file scores_parser.c
 */
#include "scores_parser.h"
#include "log_tag.h"

#include <math.h>
#include <string.h>
#include "cJSON.h"
#include "esp_log.h"

static int get_int_or(cJSON *root, const char *key, int deflt)
{
    cJSON *n = cJSON_GetObjectItemCaseSensitive(root, key);
    if (!n) return deflt;
    if (cJSON_IsNull(n)) return deflt;
    if (!cJSON_IsNumber(n)) return deflt;
    return (int)n->valuedouble;
}

static float get_float_or(cJSON *root, const char *key, float deflt)
{
    cJSON *n = cJSON_GetObjectItemCaseSensitive(root, key);
    if (!n || cJSON_IsNull(n) || !cJSON_IsNumber(n)) return deflt;
    return (float)n->valuedouble;
}

int sg_scores_parse(const uint8_t *json, size_t len, sg_scores_in_t *out)
{
    if (!json || !out) return -1;

    /* cJSON 需要 \0 结尾, 但 payload 不带; 复制一份到栈 */
    if (len >= 1024) return -1;
    char tmp[1024];
    memcpy(tmp, json, len);
    tmp[len] = '\0';

    cJSON *root = cJSON_ParseWithLength(tmp, len);
    if (!root) return -1;

    /* 检查 type 字段 */
    cJSON *tp = cJSON_GetObjectItemCaseSensitive(root, "type");
    if (!tp || !cJSON_IsString(tp) || strcmp(tp->valuestring, "scores") != 0) {
        cJSON_Delete(root);
        return -2;
    }

    memset(out, 0, sizeof(*out));
    out->seq             = get_int_or(root, "seq", 0);
    out->face            = (int8_t)get_int_or(root, "face",   -1);
    out->speech          = (int8_t)get_int_or(root, "speech", -1);
    out->tongue          = (int8_t)get_int_or(root, "tongue", -1);
    out->eye             = (int8_t)get_int_or(root, "eye",    -1);
    out->csi             = (int8_t)get_int_or(root, "csi",    -1);
    out->face_theta_deg  = get_float_or(root, "face_theta",     NAN);
    out->speech_p_clear  = get_float_or(root, "speech_p_clear", NAN);

    cJSON_Delete(root);
    return 0;
}
