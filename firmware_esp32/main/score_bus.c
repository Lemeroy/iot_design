#include "score_bus.h"

#include <math.h>
#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"

typedef struct {
    int score;
    float aux;
    int64_t updated_us;
} sg_score_entry_t;

static SemaphoreHandle_t s_lock;
static sg_score_entry_t s_face;
static sg_score_entry_t s_speech;
static sg_score_entry_t s_tongue;
static sg_score_entry_t s_eye;

static void entry_reset(sg_score_entry_t *entry)
{
    entry->score = -1;
    entry->aux = NAN;
    entry->updated_us = 0;
}

static bool score_valid(int score)
{
    return score >= 0 && score <= 100;
}

static esp_err_t entry_set(sg_score_entry_t *entry, int score,
                           float aux, int64_t now_us)
{
    if (!s_lock) return ESP_ERR_INVALID_STATE;
    if (!score_valid(score) || now_us <= 0) return ESP_ERR_INVALID_ARG;
    if (xSemaphoreTake(s_lock, portMAX_DELAY) != pdTRUE) return ESP_ERR_TIMEOUT;
    entry->score = score;
    entry->aux = aux;
    entry->updated_us = now_us;
    xSemaphoreGive(s_lock);
    return ESP_OK;
}

static bool entry_fresh(const sg_score_entry_t *entry, int64_t now_us,
                        int64_t stale_us)
{
    if (!score_valid(entry->score) || entry->updated_us <= 0) return false;
    int64_t age_us = now_us - entry->updated_us;
    return age_us >= 0 && age_us <= stale_us;
}

esp_err_t sg_score_bus_init(void)
{
    if (s_lock) return ESP_OK;
    s_lock = xSemaphoreCreateMutex();
    if (!s_lock) return ESP_ERR_NO_MEM;
    entry_reset(&s_face);
    entry_reset(&s_speech);
    entry_reset(&s_tongue);
    entry_reset(&s_eye);
    return ESP_OK;
}

esp_err_t sg_score_bus_set_face(int score, float theta_deg, int64_t now_us)
{
    if (!isfinite(theta_deg) || theta_deg < 0.0f || theta_deg > 90.0f) {
        return ESP_ERR_INVALID_ARG;
    }
    return entry_set(&s_face, score, theta_deg, now_us);
}

esp_err_t sg_score_bus_set_speech(int score, float p_clear, int64_t now_us)
{
    if (!isfinite(p_clear) || p_clear < 0.0f || p_clear > 1.0f) {
        return ESP_ERR_INVALID_ARG;
    }
    return entry_set(&s_speech, score, p_clear, now_us);
}

esp_err_t sg_score_bus_set_tongue(int score, int64_t now_us)
{
    return entry_set(&s_tongue, score, NAN, now_us);
}

esp_err_t sg_score_bus_set_eye(int score, int64_t now_us)
{
    return entry_set(&s_eye, score, NAN, now_us);
}

esp_err_t sg_score_bus_apply_camera(
    bool face_valid, int face, float theta_deg,
    bool tongue_valid, int tongue,
    bool eye_valid, int eye, int64_t now_us)
{
    if (!s_lock || now_us <= 0) return ESP_ERR_INVALID_STATE;
    if ((face_valid && (!score_valid(face) || !isfinite(theta_deg)
                        || theta_deg < 0.0f || theta_deg > 90.0f))
        || (tongue_valid && !score_valid(tongue))
        || (eye_valid && !score_valid(eye))) {
        return ESP_ERR_INVALID_ARG;
    }
    if (xSemaphoreTake(s_lock, portMAX_DELAY) != pdTRUE) return ESP_ERR_TIMEOUT;
    if (face_valid) {
        s_face = (sg_score_entry_t){face, theta_deg, now_us};
    } else {
        entry_reset(&s_face);
    }
    if (tongue_valid) {
        s_tongue = (sg_score_entry_t){tongue, NAN, now_us};
    } else {
        entry_reset(&s_tongue);
    }
    if (eye_valid) {
        s_eye = (sg_score_entry_t){eye, NAN, now_us};
    } else {
        entry_reset(&s_eye);
    }
    xSemaphoreGive(s_lock);
    return ESP_OK;
}

void sg_score_bus_snapshot(sg_scores_in_t *out, int64_t now_us,
                           uint32_t stale_ms)
{
    if (!out) return;

    memset(out, 0, sizeof(*out));
    out->face = -1;
    out->face_theta_deg = NAN;
    out->speech = -1;
    out->speech_p_clear = NAN;
    out->tongue = -1;
    out->eye = -1;
    out->csi = -1;

    if (!s_lock || now_us <= 0) return;
    if (xSemaphoreTake(s_lock, portMAX_DELAY) != pdTRUE) return;

    int64_t stale_us = (int64_t)stale_ms * 1000LL;
    if (entry_fresh(&s_face, now_us, stale_us)) {
        out->face = (int8_t)s_face.score;
        out->face_theta_deg = s_face.aux;
    }
    if (entry_fresh(&s_speech, now_us, stale_us)) {
        out->speech = (int8_t)s_speech.score;
        out->speech_p_clear = s_speech.aux;
    }
    if (entry_fresh(&s_tongue, now_us, stale_us)) {
        out->tongue = (int8_t)s_tongue.score;
    }
    if (entry_fresh(&s_eye, now_us, stale_us)) {
        out->eye = (int8_t)s_eye.score;
    }

    xSemaphoreGive(s_lock);
}
