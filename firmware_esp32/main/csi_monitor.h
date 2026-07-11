#pragma once
#include "esp_err.h"

/**
 * @brief WiFi STA 起来后调用: 注册 CSI 回调 + 启动 CSI 消费任务
 * @return ESP_OK / ESP_FAIL
 */
esp_err_t sg_csi_start(void);

/**
 * @brief 读取当前 CSI 稳定性评分
 * @return 0-100; -1 表示尚未收到足够样本
 */
int sg_csi_get_score(void);

/**
 * @brief 启动 1 Hz keep-alive 任务, 主动 ping 网关制造 CSI 流量.
 *        必须在 GOT_IP 之后调用. 幂等.
 * @return ESP_OK / ESP_FAIL
 */
esp_err_t sg_csi_ping_start(void);
