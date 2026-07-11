#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "unity.h"
#include "unity_test_runner.h"
#include "alert_io.h"
#include "display_st7789.h"
#include "fusion.h"
#include "local_alert.h"

static char captured_level[16];
static char captured_text[SG_ADVICE_TEXT_MAX + 128];

esp_err_t sg_alert_io_init(void)
{
    return ESP_OK;
}

esp_err_t sg_alert_io_set_level(const char *level)
{
    strlcpy(captured_level, level, sizeof(captured_level));
    return ESP_OK;
}

esp_err_t sg_display_st7789_init(void)
{
    return ESP_OK;
}

esp_err_t sg_display_st7789_show_status(const char *level,
                                        const char *advice_text)
{
    (void)level;
    strlcpy(captured_text, advice_text, sizeof(captured_text));
    return ESP_OK;
}

TEST_CASE("cloud advice cannot lower local danger", "[e1][alert]")
{
    captured_level[0] = '\0';
    captured_text[0] = '\0';
    sg_fusion_out_t fusion = { .level = SG_LEVEL_DANGER };
    sg_cloud_advice_t advice = {
        .level = SG_LEVEL_NORMAL,
        .ts = 1,
        .advice_text = "continue observing",
        .source = "test",
    };

    TEST_ASSERT_EQUAL(ESP_OK, sg_local_alert_init());
    sg_local_alert_apply_fusion(&fusion);
    TEST_ASSERT_EQUAL_STRING("danger", captured_level);
    TEST_ASSERT_EQUAL(SG_LEVEL_DANGER, sg_local_alert_get_level());

    sg_local_alert_apply_advice(&advice);
    TEST_ASSERT_EQUAL_STRING("danger", captured_level);
    TEST_ASSERT_EQUAL(SG_LEVEL_DANGER, sg_local_alert_get_level());
    TEST_ASSERT_NOT_NULL(strstr(captured_text, "120"));
}

TEST_CASE("face veto produces local danger", "[e1][fusion]")
{
    sg_scores_in_t in = {
        .seq = 1,
        .face = 20,
        .face_theta_deg = 0.0f,
        .speech = 80,
        .speech_p_clear = 0.8f,
        .tongue = 80,
        .eye = 80,
        .csi = 80,
    };
    sg_fusion_out_t out;
    sg_fusion_compute(&in, -1, &out);
    TEST_ASSERT_EQUAL(SG_LEVEL_DANGER, out.level);
    TEST_ASSERT_EQUAL(1, out.veto_face);
}

void app_main(void)
{
    unity_run_all_tests();
    while (1) vTaskDelay(pdMS_TO_TICKS(1000));
}
