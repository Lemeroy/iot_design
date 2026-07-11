/**
 * @file app_main.c
 * @brief 卒中卫士 M1a 主入口
 *        流程: NVS -> USB双CDC -> 延迟2s -> WiFi STA -> CSI -> heartbeat 任务
 */
#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_system.h"
#include "esp_log.h"
#include "esp_event.h"
#include "esp_netif.h"
#include "esp_wifi.h"
#include "esp_timer.h"
#include "nvs_flash.h"
#include "sdkconfig.h"

#include "app_config.h"
#include "log_tag.h"
#include "usb_cdc_proto.h"
#include "csi_monitor.h"
#include "frame_builder.h"
#include "sensor_frame.h"
#include "fusion.h"
#include "scores_parser.h"

#include "freertos/queue.h"

/* WiFi 配置 (来自 Kconfig, sdkconfig.defaults 里给了 YOUR_SSID 占位) */
#ifndef CONFIG_STROKEGUARD_WIFI_SSID
#define CONFIG_STROKEGUARD_WIFI_SSID "YOUR_SSID"
#endif
#ifndef CONFIG_STROKEGUARD_WIFI_PASSWORD
#define CONFIG_STROKEGUARD_WIFI_PASSWORD "YOUR_PASS"
#endif

static volatile bool s_wifi_got_ip = false;

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
        ESP_LOGI(SG_TAG_WIFI, "GOT_IP");
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

/* ---------- 融合流水 ---------- */
static QueueHandle_t s_scores_q = NULL;

/* CDC RX 回调: 只做 JSON 解析 + 入队, 不阻塞 */
static void on_cdc_rx(uint8_t type, const uint8_t *payload,
                      size_t plen, void *ctx)
{
    (void)ctx;
    if (type != SG_FRAME_TYPE_SCORES) return;
    sg_scores_in_t in;
    int r = sg_scores_parse(payload, plen, &in);
    if (r != 0) {
        ESP_LOGW(SG_TAG_MAIN, "scores parse failed r=%d plen=%u",
                 r, (unsigned)plen);
        return;
    }
    /* 队列满就丢老的 */
    if (xQueueSend(s_scores_q, &in, 0) != pdTRUE) {
        sg_scores_in_t drop;
        xQueueReceive(s_scores_q, &drop, 0);
        xQueueSend(s_scores_q, &in, 0);
    }
}

/* 融合任务: 收到 scores 帧就出一次 fusion 帧 */
static void task_fusion(void *arg)
{
    sg_scores_in_t in;
    sg_fusion_out_t out;
    static char buf[SG_FRAME_MAX_PAYLOAD];
    uint32_t n_processed = 0;

    while (1) {
        if (xQueueReceive(s_scores_q, &in, portMAX_DELAY) != pdTRUE) continue;

        int csi_local = sg_csi_get_score();  /* -1 if not ready */
        sg_fusion_compute(&in, csi_local, &out);
        n_processed++;

        int n = sg_frame_build_fusion(buf, sizeof(buf), &out);
        if (n <= 0) {
            ESP_LOGW(SG_TAG_MAIN, "fusion build failed n=%d", n);
            continue;
        }
        esp_err_t err = sg_cdc_send_frame(SG_FRAME_TYPE_FUSION,
                                          (const uint8_t *)buf, (size_t)n);
        if (err != ESP_OK) {
            ESP_LOGW(SG_TAG_MAIN, "fusion send err=%d", err);
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

void app_main(void)
{
    /* NVS */
    esp_err_t ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        ret = nvs_flash_init();
    }
    ESP_ERROR_CHECK(ret);

    /* USB 先起, 日志立刻可见 */
    ESP_ERROR_CHECK(sg_cdc_init());
    sg_cdc_start_tx_task();
    sg_cdc_start_rx_task();

    /* 融合队列 & 任务 (RX cb 用) */
    s_scores_q = xQueueCreate(SG_SCORES_RX_QUEUE_LEN, sizeof(sg_scores_in_t));
    ESP_ERROR_CHECK(s_scores_q ? ESP_OK : ESP_ERR_NO_MEM);
    sg_cdc_set_rx_cb(on_cdc_rx, NULL);
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

    /* 等一次 GOT_IP 再开 CSI, 最多 15 s, 超时也开(CSI 依然可采) */
    int wait = 0;
    while (!s_wifi_got_ip && wait < 30) {
        vTaskDelay(pdMS_TO_TICKS(500));
        wait++;
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

    xTaskCreatePinnedToCore(task_sensor_frame, "sensor_frame",
                            SG_TASK_FRAME_STACK, NULL,
                            SG_TASK_FRAME_PRIO, NULL,
                            SG_TASK_FRAME_CORE);

    ESP_LOGI(SG_TAG_MAIN, "all tasks started");
}
