#include <stddef.h>
#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "unity.h"
#include "unity_test_runner.h"
#include "esp_crc.h"
#include "nvs.h"
#include "nvs_flash.h"
#include "alert_io.h"
#include "display_st7789.h"
#include "fusion.h"
#include "local_alert.h"
#include "device_config.h"

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

static void reset_test_nvs(void)
{
    nvs_handle_t handle;
    TEST_ASSERT_EQUAL(ESP_OK, nvs_open("sg_cfg", NVS_READWRITE, &handle));
    TEST_ASSERT_EQUAL(ESP_OK, nvs_erase_all(handle));
    TEST_ASSERT_EQUAL(ESP_OK, nvs_commit(handle));
    nvs_close(handle);
}

static sg_profile_patch_t valid_patch(void)
{
    sg_profile_patch_t patch = { 0 };
    patch.age = 69;
    strlcpy(patch.gender, "F", sizeof(patch.gender));
    patch.stroke_history = true;
    patch.condition_count = 1;
    strlcpy(patch.conditions[0], "hypertension",
            sizeof(patch.conditions[0]));
    patch.med_count = 1;
    strlcpy(patch.meds[0], "aspirin", sizeof(patch.meds[0]));
    return patch;
}

TEST_CASE("profile update is revisioned and rejects stale writes", "[e1][config]")
{
    reset_test_nvs();
    sg_device_config_t initial;
    TEST_ASSERT_EQUAL(ESP_OK, sg_device_config_load(&initial));
    TEST_ASSERT_EQUAL_UINT32(1, initial.revision);

    sg_profile_patch_t patch = valid_patch();
    sg_device_config_t updated;
    TEST_ASSERT_EQUAL(ESP_OK, sg_device_config_apply_profile(
        initial.revision, &patch, &updated));
    TEST_ASSERT_EQUAL_UINT32(2, updated.revision);
    TEST_ASSERT_EQUAL_UINT8(69, updated.age);
    TEST_ASSERT_EQUAL_STRING("F", updated.gender);

    TEST_ASSERT_EQUAL(ESP_ERR_INVALID_STATE, sg_device_config_apply_profile(
        initial.revision, &patch, NULL));
    sg_device_config_t snapshot;
    TEST_ASSERT_EQUAL(ESP_OK, sg_device_config_snapshot(&snapshot));
    TEST_ASSERT_EQUAL_UINT32(2, snapshot.revision);
}

TEST_CASE("invalid profile patch preserves current config", "[e1][config]")
{
    reset_test_nvs();
    sg_device_config_t initial;
    TEST_ASSERT_EQUAL(ESP_OK, sg_device_config_load(&initial));

    sg_profile_patch_t patch = valid_patch();
    strlcpy(patch.gender, "X", sizeof(patch.gender));
    TEST_ASSERT_EQUAL(ESP_ERR_INVALID_ARG, sg_device_config_apply_profile(
        initial.revision, &patch, NULL));

    sg_device_config_t snapshot;
    TEST_ASSERT_EQUAL(ESP_OK, sg_device_config_snapshot(&snapshot));
    TEST_ASSERT_EQUAL_UINT32(initial.revision, snapshot.revision);
    TEST_ASSERT_EQUAL_STRING(initial.gender, snapshot.gender);
}

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
} test_config_v1_t;

TEST_CASE("version one NVS config migrates without losing profile", "[e1][config]")
{
    reset_test_nvs();
    test_config_v1_t old = { 0 };
    old.schema_version = 1;
    strlcpy(old.device_id, "sg-legacy", sizeof(old.device_id));
    old.age = 70;
    strlcpy(old.gender, "M", sizeof(old.gender));
    old.condition_count = 1;
    strlcpy(old.conditions[0], "diabetes", sizeof(old.conditions[0]));
    old.crc32 = esp_crc32_le(0, (const uint8_t *)&old,
                            offsetof(test_config_v1_t, crc32));

    nvs_handle_t handle;
    TEST_ASSERT_EQUAL(ESP_OK, nvs_open("sg_cfg", NVS_READWRITE, &handle));
    TEST_ASSERT_EQUAL(ESP_OK, nvs_set_blob(handle, "device", &old, sizeof(old)));
    TEST_ASSERT_EQUAL(ESP_OK, nvs_commit(handle));
    nvs_close(handle);

    sg_device_config_t migrated;
    TEST_ASSERT_EQUAL(ESP_OK, sg_device_config_load(&migrated));
    TEST_ASSERT_EQUAL_UINT32(SG_DEVICE_CONFIG_VERSION,
                             migrated.schema_version);
    TEST_ASSERT_EQUAL_UINT32(1, migrated.revision);
    TEST_ASSERT_EQUAL_UINT8(70, migrated.age);
    TEST_ASSERT_EQUAL_STRING("M", migrated.gender);
    TEST_ASSERT_EQUAL_STRING("diabetes", migrated.conditions[0]);
    TEST_ASSERT_TRUE(sg_device_config_manager_ready(&migrated));
}

void app_main(void)
{
    esp_err_t err = nvs_flash_init();
    if (err == ESP_ERR_NVS_NO_FREE_PAGES
        || err == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        TEST_ASSERT_EQUAL(ESP_OK, nvs_flash_erase());
        err = nvs_flash_init();
    }
    TEST_ASSERT_EQUAL(ESP_OK, err);
    unity_run_all_tests();
    while (1) vTaskDelay(pdMS_TO_TICKS(1000));
}
