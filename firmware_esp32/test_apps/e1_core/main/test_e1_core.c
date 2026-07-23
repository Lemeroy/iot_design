#include <stddef.h>
#include <math.h>
#include <stdint.h>
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
#include "sg_manager_api.h"
#include "score_bus.h"
#include "speech_screening.h"

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

static char captured_level[16];
static char captured_text[SG_ADVICE_TEXT_MAX + 128];

typedef struct {
    bool existed;
    size_t length;
    uint8_t bytes[sizeof(sg_device_config_t)];
} device_config_backup_t;

static esp_err_t backup_device_config(device_config_backup_t *backup)
{
    if (backup == NULL) return ESP_ERR_INVALID_ARG;
    memset(backup, 0, sizeof(*backup));
    nvs_handle_t handle;
    esp_err_t err = nvs_open("sg_cfg", NVS_READWRITE, &handle);
    if (err != ESP_OK) return err;
    size_t length = sizeof(backup->bytes);
    err = nvs_get_blob(handle, "device", backup->bytes, &length);
    nvs_close(handle);
    if (err == ESP_ERR_NVS_NOT_FOUND) return ESP_OK;
    if (err != ESP_OK) return err;
    backup->existed = true;
    backup->length = length;
    return ESP_OK;
}

static esp_err_t restore_device_config(const device_config_backup_t *backup)
{
    if (backup == NULL) return ESP_ERR_INVALID_ARG;
    nvs_handle_t handle;
    esp_err_t err = nvs_open("sg_cfg", NVS_READWRITE, &handle);
    if (err != ESP_OK) return err;
    if (backup->existed) {
        err = nvs_set_blob(handle, "device", backup->bytes, backup->length);
    } else {
        err = nvs_erase_key(handle, "device");
        if (err == ESP_ERR_NVS_NOT_FOUND) err = ESP_OK;
    }
    if (err == ESP_OK) err = nvs_commit(handle);
    nvs_close(handle);
    return err;
}

static void fill_silence(int16_t *samples)
{
    memset(samples, 0, SG_SPEECH_FRAME_SAMPLES * sizeof(*samples));
}

static void fill_clipped(int16_t *samples)
{
    for (size_t i = 0; i < SG_SPEECH_FRAME_SAMPLES; ++i) {
        samples[i] = (i & 1U) ? INT16_MAX : INT16_MIN;
    }
}

static void fill_speech_like(int16_t *samples, unsigned frame)
{
    for (size_t i = 0; i < SG_SPEECH_FRAME_SAMPLES; ++i) {
        float t = (float)(frame * SG_SPEECH_FRAME_SAMPLES + i) / 16000.0f;
        float envelope = 0.55f + 0.35f
            * sinf(2.0f * (float)M_PI * 4.0f * t);
        samples[i] = (int16_t)(envelope * (
            900.0f * sinf(2.0f * (float)M_PI * 220.0f * t)
            + 420.0f * sinf(2.0f * (float)M_PI * 1050.0f * t)));
    }
}

static void fill_broadband_noise(int16_t *samples, unsigned frame)
{
    uint32_t state = 0x9e3779b9U ^ (frame + 1U);
    for (size_t i = 0; i < SG_SPEECH_FRAME_SAMPLES; ++i) {
        state = state * 1664525U + 1013904223U;
        samples[i] = (int16_t)((int32_t)(state >> 20) - 2048);
    }
}

static sg_speech_result_t run_speech_frames(unsigned frames, bool clipped)
{
    sg_speech_context_t context;
    sg_speech_result_t result;
    int16_t samples[SG_SPEECH_FRAME_SAMPLES];
    sg_speech_screening_init(&context);
    sg_speech_screening_start(&context);
    for (unsigned frame = 0; frame < frames; ++frame) {
        if (frame < SG_SPEECH_NOISE_FRAMES) fill_silence(samples);
        else if (clipped) fill_clipped(samples);
        else fill_speech_like(samples, frame - SG_SPEECH_NOISE_FRAMES);
        sg_speech_screening_process(&context, samples,
                                    SG_SPEECH_FRAME_SAMPLES);
    }
    sg_speech_screening_snapshot(&context, &result);
    return result;
}

TEST_CASE("silence produces no preliminary speech score", "[speech]")
{
    sg_speech_context_t context;
    sg_speech_result_t result;
    int16_t samples[SG_SPEECH_FRAME_SAMPLES];
    fill_silence(samples);
    sg_speech_screening_init(&context);
    sg_speech_screening_start(&context);
    for (unsigned frame = 0; frame < SG_SPEECH_MAX_FRAMES; ++frame) {
        sg_speech_screening_process(&context, samples,
                                    SG_SPEECH_FRAME_SAMPLES);
    }
    sg_speech_screening_snapshot(&context, &result);
    TEST_ASSERT_EQUAL(SG_SPEECH_RETRY, result.state);
    TEST_ASSERT_FALSE(result.available);
    TEST_ASSERT_EQUAL(SG_SPEECH_REASON_NO_VOICE, result.reason);
}

TEST_CASE("short utterance produces too_short", "[speech]")
{
    sg_speech_result_t result = run_speech_frames(25, false);
    TEST_ASSERT_EQUAL(SG_SPEECH_LISTENING, result.state);
    TEST_ASSERT_FALSE(result.available);
    TEST_ASSERT_EQUAL(SG_SPEECH_REASON_NONE, result.reason);
}

TEST_CASE("clipped utterance produces clipped", "[speech]")
{
    sg_speech_result_t result = run_speech_frames(SG_SPEECH_MAX_FRAMES, true);
    TEST_ASSERT_EQUAL(SG_SPEECH_RETRY, result.state);
    TEST_ASSERT_FALSE(result.available);
    TEST_ASSERT_EQUAL(SG_SPEECH_REASON_CLIPPED, result.reason);
}

TEST_CASE("speech-like utterance produces bounded score", "[speech]")
{
    sg_speech_result_t result = run_speech_frames(SG_SPEECH_MAX_FRAMES, false);
    TEST_ASSERT_EQUAL(SG_SPEECH_COMPLETE, result.state);
    TEST_ASSERT_TRUE(result.available);
    TEST_ASSERT_UINT8_WITHIN(50, 50, result.score);
    TEST_ASSERT_FLOAT_WITHIN(0.01f, result.score / 100.0f, result.p_clear);
}

TEST_CASE("continuous broadband noise cannot receive a high speech score",
          "[speech]")
{
    sg_speech_context_t context;
    sg_speech_result_t result;
    int16_t samples[SG_SPEECH_FRAME_SAMPLES];
    sg_speech_screening_init(&context);
    sg_speech_screening_start(&context);
    for (unsigned frame = 0; frame < SG_SPEECH_MAX_FRAMES; ++frame) {
        if (frame < SG_SPEECH_NOISE_FRAMES) fill_silence(samples);
        else fill_broadband_noise(samples, frame);
        sg_speech_screening_process(&context, samples,
                                    SG_SPEECH_FRAME_SAMPLES);
    }
    sg_speech_screening_snapshot(&context, &result);
    TEST_ASSERT_TRUE(!result.available || result.score <= 35U);
}

TEST_CASE("cancel clears partial speech result", "[speech]")
{
    sg_speech_context_t context;
    sg_speech_result_t result;
    int16_t samples[SG_SPEECH_FRAME_SAMPLES];
    sg_speech_screening_init(&context);
    sg_speech_screening_start(&context);
    fill_speech_like(samples, 0);
    sg_speech_screening_process(&context, samples, SG_SPEECH_FRAME_SAMPLES);
    sg_speech_screening_cancel(&context);
    sg_speech_screening_snapshot(&context, &result);
    TEST_ASSERT_EQUAL(SG_SPEECH_IDLE, result.state);
    TEST_ASSERT_FALSE(result.available);
    TEST_ASSERT_EQUAL_UINT16(0, result.valid_frames);
}

TEST_CASE("completed result is stable until next start", "[speech]")
{
    sg_speech_context_t context;
    sg_speech_result_t before;
    sg_speech_result_t after;
    int16_t samples[SG_SPEECH_FRAME_SAMPLES];
    sg_speech_screening_init(&context);
    sg_speech_screening_start(&context);
    for (unsigned frame = 0; frame < SG_SPEECH_MAX_FRAMES; ++frame) {
        fill_speech_like(samples, frame);
        sg_speech_screening_process(&context, samples,
                                    SG_SPEECH_FRAME_SAMPLES);
    }
    sg_speech_screening_snapshot(&context, &before);
    fill_silence(samples);
    sg_speech_screening_process(&context, samples, SG_SPEECH_FRAME_SAMPLES);
    sg_speech_screening_snapshot(&context, &after);
    TEST_ASSERT_EQUAL_MEMORY(&before, &after, sizeof(before));
}

TEST_CASE("speech IO failure produces unavailable terminal result", "[speech]")
{
    sg_speech_context_t context;
    sg_speech_result_t result;
    sg_speech_screening_init(&context);
    sg_speech_screening_start(&context);
    sg_speech_screening_fail(&context, SG_SPEECH_REASON_IO_ERROR);
    sg_speech_screening_snapshot(&context, &result);
    TEST_ASSERT_EQUAL(SG_SPEECH_RETRY, result.state);
    TEST_ASSERT_FALSE(result.available);
    TEST_ASSERT_EQUAL(SG_SPEECH_REASON_IO_ERROR, result.reason);
}

TEST_CASE("heuristic low speech contributes without danger veto",
          "[speech][fusion]")
{
    sg_scores_in_t in = {
        .face = 80,
        .face_theta_deg = 2.0f,
        .speech = 20,
        .speech_p_clear = 0.2f,
        .speech_veto_eligible = false,
        .tongue = 80,
        .eye = 80,
        .csi = 80,
    };
    sg_fusion_out_t out;
    sg_fusion_compute(&in, -1, &out);
    TEST_ASSERT_EQUAL(0, out.veto_speech);
    TEST_ASSERT_GREATER_THAN(0.0f, out.contrib_speech);
}

TEST_CASE("evaluated low speech remains veto eligible",
          "[speech][fusion]")
{
    sg_scores_in_t in = {
        .face = 80,
        .face_theta_deg = 2.0f,
        .speech = 20,
        .speech_p_clear = 0.2f,
        .speech_veto_eligible = true,
        .tongue = 80,
        .eye = 80,
        .csi = 80,
    };
    sg_fusion_out_t out;
    sg_fusion_compute(&in, -1, &out);
    TEST_ASSERT_EQUAL(1, out.veto_speech);
    TEST_ASSERT_EQUAL(SG_LEVEL_DANGER, out.level);
}

TEST_CASE("continuous low eye does not independently upgrade warning",
          "[eye][fusion]")
{
    sg_scores_in_t in = {
        .face = 100,
        .face_theta_deg = 0.0f,
        .speech = 100,
        .speech_p_clear = 1.0f,
        .speech_veto_eligible = false,
        .tongue = 100,
        .eye = 10,
        .csi = 100,
    };
    sg_fusion_out_t out;
    sg_fusion_compute(&in, -1, &out);
    TEST_ASSERT_GREATER_OR_EQUAL(70, out.final);
    TEST_ASSERT_EQUAL(SG_LEVEL_NORMAL, out.level);
}

TEST_CASE("retained speech contributes without stale veto", "[speech][score_bus]")
{
    sg_scores_in_t snapshot;
    TEST_ASSERT_EQUAL(ESP_OK, sg_score_bus_init());
    TEST_ASSERT_EQUAL(ESP_OK,
        sg_score_bus_set_speech(20, 0.2f, true, 1000000));
    sg_score_bus_snapshot(&snapshot, 1000000, 1000);
    TEST_ASSERT_EQUAL(20, snapshot.speech);
    TEST_ASSERT_TRUE(snapshot.speech_veto_eligible);

    sg_score_bus_snapshot(&snapshot, 3000000, 1000);
    TEST_ASSERT_EQUAL(20, snapshot.speech);
    TEST_ASSERT_FALSE(snapshot.speech_veto_eligible);

    sg_score_bus_snapshot(&snapshot, 301000000, 1000);
    TEST_ASSERT_EQUAL(20, snapshot.speech);
    TEST_ASSERT_FALSE(snapshot.speech_veto_eligible);

    sg_score_bus_snapshot(&snapshot, 301000001, 1000);
    TEST_ASSERT_EQUAL(-1, snapshot.speech);
    TEST_ASSERT_FALSE(snapshot.speech_veto_eligible);
}

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

static void assert_patch_result(const char *json,
                                sg_manager_parse_err_t expected)
{
    uint32_t revision = 0;
    sg_profile_patch_t patch = { 0 };
    TEST_ASSERT_EQUAL(expected, sg_manager_parse_profile_patch(
        json, strlen(json), &revision, &patch));
}

TEST_CASE("manager parser accepts a bounded profile update", "[e1][manager]")
{
    const char *json =
        "{\"schema_version\":1,\"expected_revision\":7,\"profile\":{"
        "\"age\":69,\"gender\":\"F\","
        "\"conditions\":[\"hypertension\"],\"meds\":[\"aspirin\"],"
        "\"stroke_history\":true}}";
    uint32_t revision = 0;
    sg_profile_patch_t patch = { 0 };
    TEST_ASSERT_EQUAL(SG_MANAGER_OK, sg_manager_parse_profile_patch(
        json, strlen(json), &revision, &patch));
    TEST_ASSERT_EQUAL_UINT32(7, revision);
    TEST_ASSERT_EQUAL_UINT8(69, patch.age);
    TEST_ASSERT_EQUAL_STRING("F", patch.gender);
    TEST_ASSERT_EQUAL_UINT8(1, patch.condition_count);
    TEST_ASSERT_EQUAL_STRING("hypertension", patch.conditions[0]);
    TEST_ASSERT_EQUAL_UINT8(1, patch.med_count);
    TEST_ASSERT_EQUAL_STRING("aspirin", patch.meds[0]);
    TEST_ASSERT_TRUE(patch.stroke_history);

    const char *utf8_json =
        "{\"schema_version\":1,\"expected_revision\":8,\"profile\":{"
        "\"age\":70,\"gender\":\"other\","
        "\"conditions\":[\"\xE9\xAB\x98\xE8\xA1\x80\xE5\x8E\x8B\"],"
        "\"meds\":[],\"stroke_history\":false}}";
    TEST_ASSERT_EQUAL(SG_MANAGER_OK, sg_manager_parse_profile_patch(
        utf8_json, strlen(utf8_json), &revision, &patch));
}

TEST_CASE("manager parser rejects non-whitelisted structures", "[e1][manager]")
{
    assert_patch_result(
        "{\"schema_version\":1,\"expected_revision\":1,\"profile\":{"
        "\"age\":60,\"gender\":\"M\",\"conditions\":[],\"meds\":[],"
        "\"stroke_history\":false},\"mqtt_uri\":\"mqtt://x\"}",
        SG_MANAGER_INVALID_FIELD);
    assert_patch_result(
        "{\"schema_version\":1,\"expected_revision\":1,"
        "\"expected_revision\":2,\"profile\":{\"age\":60,"
        "\"gender\":\"M\",\"conditions\":[],\"meds\":[],"
        "\"stroke_history\":false}}",
        SG_MANAGER_INVALID_FIELD);
    assert_patch_result(
        "{\"schema_version\":1,\"expected_revision\":1,\"profile\":{"
        "\"age\":60,\"gender\":\"M\",\"conditions\":[],\"meds\":[],"
        "\"stroke_history\":false,\"face_danger\":20}}",
        SG_MANAGER_INVALID_FIELD);
}

TEST_CASE("manager parser rejects invalid values and bounds", "[e1][manager]")
{
    assert_patch_result(
        "{\"schema_version\":2,\"expected_revision\":1,\"profile\":{}}",
        SG_MANAGER_INVALID_FIELD);
    assert_patch_result(
        "{\"schema_version\":1,\"expected_revision\":1.5,\"profile\":{}}",
        SG_MANAGER_INVALID_FIELD);
    assert_patch_result(
        "{\"schema_version\":1,\"expected_revision\":1,\"profile\":{"
        "\"age\":131,\"gender\":\"M\",\"conditions\":[],\"meds\":[],"
        "\"stroke_history\":false}}",
        SG_MANAGER_INVALID_FIELD);
    assert_patch_result(
        "{\"schema_version\":1,\"expected_revision\":1,\"profile\":{"
        "\"age\":60,\"gender\":\"M\",\"conditions\":[\"a\",\"b\","
        "\"c\",\"d\",\"e\"],\"meds\":[],\"stroke_history\":false}}",
        SG_MANAGER_INVALID_FIELD);
    assert_patch_result(
        "{\"schema_version\":1,\"expected_revision\":1,\"profile\":{"
        "\"age\":60,\"gender\":\"M\","
        "\"conditions\":[\"12345678901234567890123456789012\"],"
        "\"meds\":[],\"stroke_history\":false}}",
        SG_MANAGER_INVALID_FIELD);
    assert_patch_result("{bad", SG_MANAGER_BAD_JSON);

    char invalid_utf8[] =
        "{\"schema_version\":1,\"expected_revision\":1,\"profile\":{"
        "\"age\":60,\"gender\":\"M\",\"conditions\":[\"\xC0\xAF\"],"
        "\"meds\":[],\"stroke_history\":false}}";
    assert_patch_result(invalid_utf8, SG_MANAGER_INVALID_FIELD);

    char oversized[SG_MANAGER_BODY_MAX + 2];
    memset(oversized, ' ', sizeof(oversized));
    oversized[sizeof(oversized) - 1] = '\0';
    assert_patch_result(oversized, SG_MANAGER_TOO_LARGE);
}

TEST_CASE("manager token comparison is exact", "[e1][manager]")
{
    TEST_ASSERT_TRUE(sg_manager_token_equal("unit-token", "unit-token"));
    TEST_ASSERT_FALSE(sg_manager_token_equal("unit-token", "unit-tokeN"));
    TEST_ASSERT_FALSE(sg_manager_token_equal("unit-token", "unit"));
    TEST_ASSERT_FALSE(sg_manager_token_equal("", ""));
    char too_long[SG_MANAGER_TOKEN_MAX + 2];
    memset(too_long, 'x', sizeof(too_long));
    too_long[sizeof(too_long) - 1] = '\0';
    TEST_ASSERT_FALSE(sg_manager_token_equal(too_long, too_long));
}

TEST_CASE("manager response excludes credentials", "[e1][manager]")
{
    sg_device_config_t cfg;
    TEST_ASSERT_EQUAL(ESP_OK, sg_device_config_snapshot(&cfg));
    strlcpy(cfg.mqtt_pass, "forbidden-mqtt-secret", sizeof(cfg.mqtt_pass));
    strlcpy(cfg.manager_token, "forbidden-manager-secret",
            sizeof(cfg.manager_token));
    char response[SG_MANAGER_RESPONSE_MAX];
    int length = sg_manager_build_config_json(response, sizeof(response), &cfg);
    TEST_ASSERT_GREATER_THAN(0, length);
    TEST_ASSERT_NOT_NULL(strstr(response, "\"schema_version\":1"));
    TEST_ASSERT_NOT_NULL(strstr(response, "\"revision\":"));
    TEST_ASSERT_NOT_NULL(strstr(response, "\"readonly\":"));
    TEST_ASSERT_NOT_NULL(strstr(response, "\"profile_write\""));
    TEST_ASSERT_NULL(strstr(response, "forbidden-mqtt-secret"));
    TEST_ASSERT_NULL(strstr(response, "forbidden-manager-secret"));
    TEST_ASSERT_NULL(strstr(response, "mqtt_pass"));
    TEST_ASSERT_NULL(strstr(response, "manager_token"));
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
    device_config_backup_t backup;
    ESP_ERROR_CHECK(backup_device_config(&backup));
    unity_run_all_tests();
    ESP_ERROR_CHECK(restore_device_config(&backup));
    while (1) vTaskDelay(pdMS_TO_TICKS(1000));
}
