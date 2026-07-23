/**
 * @file app_main.c
 * @brief 卒中卫士 M1a 主入口
 *        流程: NVS -> USB双CDC -> 延迟2s -> WiFi STA -> CSI -> heartbeat 任务
 */
#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"
#include "esp_system.h"
#include "esp_log.h"
#include "esp_event.h"
#include "esp_netif.h"
#include "esp_wifi.h"
#include "esp_netif_ip_addr.h"
#include "esp_timer.h"
#include "nvs_flash.h"
#include "sdkconfig.h"

#include "app_config.h"
#include "log_tag.h"
#include "usb_cdc_proto.h"
#include "csi_monitor.h"
#include "frame_builder.h"
#if CONFIG_STROKEGUARD_LEGACY_USB_STREAM
#include "sensor_frame.h"
#endif
#include "fusion.h"
#include "score_bus.h"
#include "camera_coprocessor.h"
#include "audio_nmo432.h"
#include "sg_time.h"
#include "sg_mqtt.h"
#include "device_config.h"
#include "cloud_contract.h"
#include "local_alert.h"
#include "sg_manager_api.h"

/* WiFi 配置 (来自 Kconfig, sdkconfig.defaults 里给了 YOUR_SSID 占位) */
#ifndef CONFIG_STROKEGUARD_WIFI_SSID
#define CONFIG_STROKEGUARD_WIFI_SSID "YOUR_SSID"
#endif

#ifndef CONFIG_STROKEGUARD_WIFI_PASSWORD
#define CONFIG_STROKEGUARD_WIFI_PASSWORD "YOUR_PASS"
#endif

static volatile bool s_wifi_got_ip = false;
static sg_device_config_t s_device_config;
static bool s_device_config_loaded;
static QueueHandle_t s_downlink_q;

static void on_mqtt_downlink(const sg_mqtt_downlink_t *downlink, void *ctx)
{
    (void)ctx;
    if (!downlink || !s_downlink_q) return;
    xQueueOverwrite(s_downlink_q, downlink);
}

static void task_downlink(void *arg)
{
    (void)arg;
    sg_mqtt_downlink_t downlink;
    while (1) {
        if (xQueueReceive(s_downlink_q, &downlink, portMAX_DELAY) != pdTRUE) {
            continue;
        }
        if (downlink.type == SG_MQTT_DOWNLINK_CONTROL) {
            esp_err_t err = sg_camera_coprocessor_control(
                downlink.payload.control.action);
            if (err != ESP_OK) {
                ESP_LOGW(SG_TAG_MQTT, "screening control failed: %s",
                         esp_err_to_name(err));
            }
            continue;
        }
        const sg_cloud_advice_t advice = downlink.payload.advice;
        int64_t now = sg_time_unix_seconds();
        if (now == 0 || advice.ts > now + 30
            || now - advice.ts > SG_ADVICE_MAX_AGE_SEC) {
            ESP_LOGW(SG_TAG_MQTT, "stale downlink discarded");
            continue;
        }
        sg_local_alert_apply_advice(&advice);
    }
}

static void wifi_event_handler(void *arg, esp_event_base_t base,
                               int32_t id, void *data)
{
    if (base == WIFI_EVENT && id == WIFI_EVENT_STA_START) {
        esp_wifi_connect();
    } else if (base == WIFI_EVENT && id == WIFI_EVENT_STA_DISCONNECTED) {
        ESP_LOGW(SG_TAG_WIFI, "disconnected, retrying");
        s_wifi_got_ip = false;
        esp_wifi_connect();
    } else if (base == IP_EVENT && id == IP_EVENT_STA_GOT_IP) {
        const ip_event_got_ip_t *event = (const ip_event_got_ip_t *)data;
        ESP_LOGI(SG_TAG_WIFI, "GOT_IP address=" IPSTR,
                 IP2STR(&event->ip_info.ip));
        s_wifi_got_ip = true;
    }
}

static esp_err_t wifi_init_sta(void)
{
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    esp_netif_create_default_wifi_sta();

    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));

    ESP_ERROR_CHECK(esp_event_handler_instance_register(
        WIFI_EVENT, ESP_EVENT_ANY_ID, &wifi_event_handler, NULL, NULL));
    ESP_ERROR_CHECK(esp_event_handler_instance_register(
        IP_EVENT, IP_EVENT_STA_GOT_IP, &wifi_event_handler, NULL, NULL));

    wifi_config_t wcfg = { 0 };
    strncpy((char *)wcfg.sta.ssid,     CONFIG_STROKEGUARD_WIFI_SSID,     sizeof(wcfg.sta.ssid) - 1);
    strncpy((char *)wcfg.sta.password, CONFIG_STROKEGUARD_WIFI_PASSWORD, sizeof(wcfg.sta.password) - 1);
    wcfg.sta.threshold.authmode = WIFI_AUTH_WPA2_PSK;

    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_storage(WIFI_STORAGE_RAM));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &wcfg));
    ESP_ERROR_CHECK(esp_wifi_start());
    /* CSI 需要电台常开, 关闭省电才能得到稳定包率 */
    ESP_ERROR_CHECK(esp_wifi_set_ps(WIFI_PS_NONE));
    return ESP_OK;
}

/* ---------- 本地融合流水 ---------- */
static void task_fusion(void *arg)
{
    (void)arg;
    sg_scores_in_t in;
    sg_fusion_out_t out;
    static char buf[SG_FRAME_MAX_PAYLOAD];
    static char uplink[SG_CLOUD_UPLINK_MAX];
    uint32_t n_processed = 0;
    bool has_published = false;
    sg_level_t last_published_level = SG_LEVEL_INSUFFICIENT;
    sg_screening_stage_t last_published_stage = SG_STAGE_IDLE;
    uint32_t last_speech_window_id = 0;
    int64_t last_publish_us = 0;
    TickType_t last = xTaskGetTickCount();

    while (1) {
        vTaskDelayUntil(&last, pdMS_TO_TICKS(SG_TASK_FUSION_PERIOD_MS));

        sg_score_bus_snapshot(&in, esp_timer_get_time(), SG_SCORE_STALE_MS);
        in.seq = (int32_t)n_processed;
        int csi_local = sg_csi_get_score();
        in.csi = (csi_local >= 0 && csi_local <= 100)
                   ? (int8_t)csi_local : (int8_t)-1;
        sg_fusion_compute(&in, -1, &out);
        n_processed++;

        sg_local_alert_apply_fusion(&out);

        int64_t now_us = esp_timer_get_time();
        int64_t unix_ts = sg_time_unix_seconds();
        sg_screening_stage_t screening_stage =
            sg_camera_coprocessor_stage();
        bool speech_score_updated = false;
#if CONFIG_STROKEGUARD_NMO432_ENABLE
        sg_speech_result_t result;
        bool have_speech_result =
            sg_audio_nmo432_speech_snapshot(&result) == ESP_OK;
        if (have_speech_result && result.window_id != 0U
            && result.window_id != last_speech_window_id) {
            last_speech_window_id = result.window_id;
            esp_err_t speech_err = ESP_OK;
            bool speech_result_applied = false;
            if (result.available) {
                speech_err = sg_score_bus_set_speech(
                    result.score, result.p_clear, false, esp_timer_get_time());
                speech_result_applied = true;
            } else if (result.reason == SG_SPEECH_REASON_IO_ERROR) {
                speech_err = sg_score_bus_clear_speech();
                speech_result_applied = true;
            } else {
                ESP_LOGI(SG_TAG_MAIN,
                         "speech window unavailable; retaining previous score");
            }
            if (speech_result_applied && speech_err == ESP_OK) {
                speech_score_updated = true;
                ESP_LOGI(SG_TAG_MAIN,
                         "continuous speech window=%lu available=%u score=%u",
                         (unsigned long)result.window_id,
                         (unsigned)result.available,
                         (unsigned)result.score);
            }
        }
#endif
        if (speech_score_updated) {
            sg_score_bus_snapshot(&in, esp_timer_get_time(), SG_SCORE_STALE_MS);
            in.seq = (int32_t)(n_processed - 1U);
            in.csi = (csi_local >= 0 && csi_local <= 100)
                       ? (int8_t)csi_local : (int8_t)-1;
            sg_fusion_compute(&in, -1, &out);
            sg_local_alert_apply_fusion(&out);
        }
        bool publish_due = !has_published
            || speech_score_updated
            || out.level != last_published_level
            || screening_stage != last_published_stage
            || now_us - last_publish_us
                >= (int64_t)SG_MQTT_PUBLISH_PERIOD_MS * 1000LL;
        if (s_device_config_loaded && publish_due && unix_ts > 0
            && sg_mqtt_connected()) {
            sg_device_config_t config_snapshot;
            esp_err_t snapshot_err = sg_device_config_snapshot(&config_snapshot);
            int up_len = snapshot_err == ESP_OK
                ? sg_cloud_build_uplink(
                    uplink, sizeof(uplink), &config_snapshot, &in, &out,
                    screening_stage,
                    unix_ts, (uint32_t)out.seq)
                : -1;
            if (up_len > 0
                && sg_mqtt_publish_uplink(uplink, (size_t)up_len) == ESP_OK) {
                has_published = true;
                last_published_level = out.level;
                last_published_stage = screening_stage;
                last_publish_us = now_us;
                ESP_LOGI(SG_TAG_MQTT, "uplink queued seq=%ld level=%s",
                         (long)out.seq, sg_fusion_level_name(out.level));
            }
        }

        int n = sg_frame_build_fusion(buf, sizeof(buf), &out);
        if (n <= 0) {
            ESP_LOGW(SG_TAG_MAIN, "fusion build failed n=%d", n);
        } else {
            esp_err_t err = sg_cdc_send_frame(
                SG_FRAME_TYPE_FUSION, (const uint8_t *)buf, (size_t)n);
            if (err != ESP_OK) {
                ESP_LOGW(SG_TAG_MAIN, "fusion send err=%d", err);
            }
        }

        /* 每 20 次采样打一次日志 */
        if ((n_processed % 20) == 1) {
            ESP_LOGI(SG_TAG_MAIN,
                     "fusion seq=%ld final=%ld level=%s veto=[F=%d S=%d]",
                     (long)out.seq, (long)out.final,
                     sg_fusion_level_name(out.level),
                     (int)out.veto_face, (int)out.veto_speech);
        }
    }
}

/* ---------- 心跳任务 1Hz ---------- */
static void task_heartbeat(void *arg){
    uint32_t seq = 0;
    char buf[SG_FRAME_MAX_PAYLOAD];
    TickType_t last = xTaskGetTickCount();

    while (1) {
        vTaskDelayUntil(&last, pdMS_TO_TICKS(1000));

        uint32_t ts = (uint32_t)(esp_timer_get_time() / 1000000ULL);
        int csi = sg_csi_get_score();
        int n = sg_frame_build_heartbeat(buf, sizeof(buf), ts, seq++, csi);
        if (n <= 0) continue;

        esp_err_t err = sg_cdc_send_frame(SG_FRAME_TYPE_HEARTBEAT,
                                          (const uint8_t *)buf, (size_t)n);
        if (err != ESP_OK) {
            ESP_LOGW(SG_TAG_MAIN, "hb send err=%d", err);
        }
    }
}

/* ---------- M1b 合成 frame 任务 ----------
 * 传感器未到货前先发送最终 JSON 契约, 让 PC/GUI/云端链路可联调.
 * 到货后这里替换为 GC2145 JPEG + INMP441 MFCC + CSI 分数.
 */
#if CONFIG_STROKEGUARD_LEGACY_USB_STREAM
static void task_sensor_frame(void *arg)
{
    uint32_t seq = 0;
    char buf[SG_FRAME_MAX_PAYLOAD];
    TickType_t last = xTaskGetTickCount();

    while (1) {
        vTaskDelayUntil(&last, pdMS_TO_TICKS(SG_FRAME_PERIOD_MS));

        uint32_t ts = (uint32_t)(esp_timer_get_time() / 1000000ULL);
        int csi = sg_csi_get_score();
        int n = sg_sensor_frame_build_json(buf, sizeof(buf), ts, seq++, csi);
        if (n <= 0) {
            ESP_LOGW(SG_TAG_MAIN, "frame build failed n=%d", n);
            continue;
        }
        esp_err_t err = sg_cdc_send_frame(SG_FRAME_TYPE_DATA,
                                          (const uint8_t *)buf, (size_t)n);
        if (err != ESP_OK) {
            ESP_LOGW(SG_TAG_MAIN, "frame send err=%d", err);
        }
    }
}
#endif

void app_main(void)
{
    /* NVS */
    esp_err_t ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        ret = nvs_flash_init();
    }
    ESP_ERROR_CHECK(ret);

    esp_err_t config_err = sg_device_config_load(&s_device_config);
    s_device_config_loaded = config_err == ESP_OK;
    if (!s_device_config_loaded) {
        ESP_LOGW(SG_TAG_MAIN, "device config unavailable err=%s; cloud disabled",
                 esp_err_to_name(config_err));
    }

    ESP_ERROR_CHECK(sg_score_bus_init());
    ESP_ERROR_CHECK(sg_local_alert_init());

#if CONFIG_STROKEGUARD_CAMERA_COPROCESSOR_ENABLE
    esp_err_t camera_err = sg_camera_coprocessor_init();
    if (camera_err != ESP_OK) {
        ESP_LOGW(SG_TAG_MAIN, "camera coprocessor init failed: %s",
                 esp_err_to_name(camera_err));
    }
#endif

#if CONFIG_STROKEGUARD_NMO432_ENABLE
    esp_err_t audio_err = sg_audio_nmo432_init();
    if (audio_err != ESP_OK) {
        ESP_LOGW(SG_TAG_MAIN, "NMO432 init failed: %s",
                 esp_err_to_name(audio_err));
    }
#endif

    s_downlink_q = xQueueCreate(1, sizeof(sg_mqtt_downlink_t));
    ESP_ERROR_CHECK(s_downlink_q ? ESP_OK : ESP_ERR_NO_MEM);
    xTaskCreatePinnedToCore(task_downlink, "downlink",
                            SG_TASK_ADVICE_STACK, NULL,
                            SG_TASK_ADVICE_PRIO, NULL,
                            SG_TASK_ADVICE_CORE);

    /* USB 先起, 日志立刻可见 */
    ESP_ERROR_CHECK(sg_cdc_init());
    sg_cdc_start_tx_task();
    sg_cdc_start_rx_task();

    xTaskCreatePinnedToCore(task_fusion, "fusion",
                            SG_TASK_FUSION_STACK, NULL,
                            SG_TASK_FUSION_PRIO, NULL,
                            SG_TASK_FUSION_CORE);

    ESP_LOGI(SG_TAG_MAIN, "boot fw=%s", SG_FW_VERSION);
    ESP_LOGI(SG_TAG_MAIN, "waiting %d ms for USB host enum...",
             SG_USB_TO_WIFI_DELAY_MS);
    vTaskDelay(pdMS_TO_TICKS(SG_USB_TO_WIFI_DELAY_MS));

    /* WiFi STA */
    ESP_ERROR_CHECK(wifi_init_sta());
    esp_err_t time_err = sg_time_sync_start();
    if (time_err != ESP_OK) {
        ESP_LOGW(SG_TAG_TIME, "SNTP start failed err=%s",
                 esp_err_to_name(time_err));
    }
    if (s_device_config_loaded
        && sg_device_config_mqtt_ready(&s_device_config)) {
        esp_err_t mqtt_err = sg_mqtt_start(
            &s_device_config, on_mqtt_downlink, NULL);
        if (mqtt_err != ESP_OK) {
            ESP_LOGW(SG_TAG_MQTT, "mqtt start failed err=%s",
                     esp_err_to_name(mqtt_err));
        }
    } else {
        ESP_LOGW(SG_TAG_MQTT, "mqtt disabled: configuration incomplete");
    }

    /* 等一次 GOT_IP 再开 CSI, 最多 15 s, 超时也开(CSI 依然可采) */
    int wait = 0;
    while (!s_wifi_got_ip && wait < 30) {
        vTaskDelay(pdMS_TO_TICKS(500));
        wait++;
    }

    if (s_wifi_got_ip && s_device_config_loaded
        && sg_device_config_manager_ready(&s_device_config)) {
        esp_err_t manager_err = sg_manager_api_start();
        if (manager_err != ESP_OK) {
            ESP_LOGW(SG_TAG_MANAGER, "manager API unavailable err=%s",
                     esp_err_to_name(manager_err));
        }
    } else {
        ESP_LOGW(SG_TAG_MANAGER, "manager API disabled: no IP or token");
    }

    ESP_ERROR_CHECK(sg_csi_start());

    /* CSI keep-alive: 1Hz ping 网关, 保证 CSI 包流量 (需在 GOT_IP 后) */
    if (s_wifi_got_ip) {
        sg_csi_ping_start();
    } else {
        ESP_LOGW(SG_TAG_MAIN, "no IP yet, skipping csi ping keepalive");
    }

    xTaskCreatePinnedToCore(task_heartbeat, "hb",
                            SG_TASK_HEARTBEAT_STACK, NULL,
                            SG_TASK_HEARTBEAT_PRIO, NULL,
                            SG_TASK_HEARTBEAT_CORE);

#if CONFIG_STROKEGUARD_LEGACY_USB_STREAM
    xTaskCreatePinnedToCore(task_sensor_frame, "sensor_frame",
                            SG_TASK_FRAME_STACK, NULL,
                            SG_TASK_FRAME_PRIO, NULL,
                            SG_TASK_FRAME_CORE);
#endif

    ESP_LOGI(SG_TAG_MAIN, "all tasks started");
}
