#include "local_alert.h"

#include <stdio.h>
#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "alert_io.h"
#include "display_st7789.h"
#include "esp_log.h"
#include "log_tag.h"

#define SG_PRESENT_TEXT_MAX (SG_ADVICE_TEXT_MAX + 128)

static SemaphoreHandle_t s_lock;
static sg_level_t s_level = SG_LEVEL_INSUFFICIENT;
static bool s_has_advice;
static char s_advice[SG_ADVICE_TEXT_MAX + 1];

static const char *fixed_text(sg_level_t level)
{
    switch (level) {
        case SG_LEVEL_NORMAL:
            return "当前未发现明显异常，请继续观察";
        case SG_LEVEL_WARNING:
            return "检测到风险变化，请家属陪同并尽快评估";
        case SG_LEVEL_DANGER:
            return "疑似高风险，请立即拨打120";
        default:
            return "数据不足，请按提示重新测量";
    }
}

static void render_state(void)
{
    sg_level_t level;
    bool has_advice;
    char advice[SG_ADVICE_TEXT_MAX + 1];

    if (xSemaphoreTake(s_lock, portMAX_DELAY) != pdTRUE) return;
    level = s_level;
    has_advice = s_has_advice;
    strlcpy(advice, s_advice, sizeof(advice));
    xSemaphoreGive(s_lock);

    const char *level_name = sg_fusion_level_name(level);
    char text[SG_PRESENT_TEXT_MAX];
    if (has_advice) {
        snprintf(text, sizeof(text), "%s\n%s", fixed_text(level), advice);
    } else {
        strlcpy(text, fixed_text(level), sizeof(text));
    }
    sg_display_st7789_show_status(level_name, text);
}

esp_err_t sg_local_alert_init(void)
{
    if (!s_lock) {
        s_lock = xSemaphoreCreateMutex();
        if (!s_lock) return ESP_ERR_NO_MEM;
    }

    esp_err_t alert_err = sg_alert_io_init();
    esp_err_t display_err = sg_display_st7789_init();
    ESP_LOGI(SG_TAG_MAIN, "local alert ready alert=%s display=%s",
             esp_err_to_name(alert_err), esp_err_to_name(display_err));
    render_state();
    return ESP_OK;
}

void sg_local_alert_apply_fusion(const sg_fusion_out_t *fusion)
{
    if (!fusion || !s_lock) return;
    if (xSemaphoreTake(s_lock, portMAX_DELAY) != pdTRUE) return;
    s_level = fusion->level;
    xSemaphoreGive(s_lock);

    const char *level_name = sg_fusion_level_name(fusion->level);
    sg_alert_io_set_level(level_name);
    render_state();
}

void sg_local_alert_apply_advice(const sg_cloud_advice_t *advice)
{
    if (!advice || !s_lock || !advice->advice_text[0]) return;
    if (xSemaphoreTake(s_lock, portMAX_DELAY) != pdTRUE) return;
    strlcpy(s_advice, advice->advice_text, sizeof(s_advice));
    s_has_advice = true;
    xSemaphoreGive(s_lock);
    render_state();
}

sg_level_t sg_local_alert_get_level(void)
{
    if (!s_lock) return SG_LEVEL_INSUFFICIENT;
    if (xSemaphoreTake(s_lock, portMAX_DELAY) != pdTRUE) {
        return SG_LEVEL_INSUFFICIENT;
    }
    sg_level_t level = s_level;
    xSemaphoreGive(s_lock);
    return level;
}
