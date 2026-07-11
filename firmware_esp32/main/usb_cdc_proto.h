#pragma once
#include <stdint.h>
#include <stddef.h>
#include "esp_err.h"

/**
 * @brief 帧接收回调 (从 CDC RX 任务里调用, 尽快返回, 别阻塞)
 * @param type    SG_FRAME_TYPE_*
 * @param payload UTF-8 JSON (无 \0 结尾)
 * @param plen    payload 长度
 * @param ctx     注册时传入的用户上下文
 */
typedef void (*sg_cdc_rx_cb_t)(uint8_t type, const uint8_t *payload,
                               size_t plen, void *ctx);

/**
 * @brief 初始化 USB-Serial-JTAG (单 CDC, 数据+日志共用)
 */
esp_err_t sg_cdc_init(void);

/**
 * @brief 构造并入队一帧到发送队列
 */
esp_err_t sg_cdc_send_frame(uint8_t type, const uint8_t *payload, size_t plen);

/**
 * @brief 启动 CDC 发送任务
 */
void sg_cdc_start_tx_task(void);

/**
 * @brief 注册 RX 回调 (只支持一个订阅者, 后注册覆盖)
 */
void sg_cdc_set_rx_cb(sg_cdc_rx_cb_t cb, void *ctx);

/**
 * @brief 启动 CDC 接收任务 (状态机解析 magic + CRC)
 */
void sg_cdc_start_rx_task(void);
