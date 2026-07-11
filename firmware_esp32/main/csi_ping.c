/**
 * @file csi_ping.c
 * @brief 1 Hz ICMP ping keep-alive
 *
 * 目的: STA 空闲时 CSI 包非常少 (只有 beacon/probe), 主动 ping 网关
 *       可以稳定制造 CSI 采样, 提升打分刷新率. 借鉴 RuView 的做法.
 *
 * 用法: 必须在 GOT_IP 之后调用 sg_csi_ping_start().
 */
#include "csi_monitor.h"
#include "app_config.h"
#include "log_tag.h"

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_netif.h"
#include "esp_log.h"
#include "ping/ping_sock.h"
#include "lwip/inet.h"

static bool s_ping_running = false;

static void on_ping_success(esp_ping_handle_t hdl, void *args)
{
    /* 静默: 只是为了产生流量, 详细日志会刷屏 */
    (void)hdl; (void)args;
}

static void on_ping_end(esp_ping_handle_t hdl, void *args)
{
    (void)hdl; (void)args;
}

esp_err_t sg_csi_ping_start(void)
{
    if (s_ping_running) return ESP_OK;

    /* 拿到默认 netif 的网关 IP */
    esp_netif_t *netif = esp_netif_get_default_netif();
    if (!netif) {
        ESP_LOGE(SG_TAG_CSI, "ping: no default netif");
        return ESP_FAIL;
    }
    esp_netif_ip_info_t ip;
    esp_err_t err = esp_netif_get_ip_info(netif, &ip);
    if (err != ESP_OK || ip.gw.addr == 0) {
        ESP_LOGE(SG_TAG_CSI, "ping: no gateway (err=%d)", err);
        return ESP_FAIL;
    }

    ip_addr_t target = {
        .type = IPADDR_TYPE_V4,
        .u_addr.ip4.addr = ip.gw.addr,
    };

    esp_ping_config_t cfg = ESP_PING_DEFAULT_CONFIG();
    cfg.target_addr = target;
    cfg.count       = ESP_PING_COUNT_INFINITE;
    cfg.interval_ms = SG_CSI_PING_INTERVAL_MS;
    cfg.timeout_ms  = 800;
    cfg.data_size   = 32;
    cfg.tos         = 0;
    cfg.task_stack_size = SG_CSI_PING_STACK;
    cfg.task_prio       = SG_CSI_PING_PRIO;

    esp_ping_callbacks_t cbs = {
        .on_ping_success = on_ping_success,
        .on_ping_end     = on_ping_end,
    };

    esp_ping_handle_t hdl = NULL;
    err = esp_ping_new_session(&cfg, &cbs, &hdl);
    if (err != ESP_OK) {
        ESP_LOGE(SG_TAG_CSI, "ping new session err=%d", err);
        return err;
    }
    err = esp_ping_start(hdl);
    if (err != ESP_OK) {
        ESP_LOGE(SG_TAG_CSI, "ping start err=%d", err);
        return err;
    }

    s_ping_running = true;
    ESP_LOGI(SG_TAG_CSI, "ping keep-alive @ gw=" IPSTR " every %d ms",
             IP2STR(&ip.gw), SG_CSI_PING_INTERVAL_MS);
    return ESP_OK;
}
