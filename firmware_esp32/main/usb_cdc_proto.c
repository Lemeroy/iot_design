#include "usb_cdc_proto.h"
#include "app_config.h"
#include "log_tag.h"
#include "crc16.h"

#include <string.h>
#include <stdio.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"
#include "esp_log.h"
#include "driver/usb_serial_jtag.h"

/**
 * M1a v0.2: 用 ESP32-S3 内置 USB-Serial-JTAG 单口
 *  - 数据帧 (A5 5A ...) 和日志 (ESP_LOGx) 混流写入同一 CDC
 *  - PC 端 cdc_reader 靠 magic 滑动同步自动跳过日志垃圾字节
 *  - 优点: 零外部依赖, 不需要 tinyusb managed component
 *  - 只需要一根 Type-C 线, 一个 COM 口, 数据 + 日志全走它
 */

/* ---- 单帧结构, 用于 TX 队列传递 ---- */
typedef struct {
    uint8_t  type;
    uint16_t plen;
    uint8_t  payload[SG_FRAME_MAX_PAYLOAD];
} sg_frame_t;

static QueueHandle_t s_tx_queue = NULL;

/* ---------- 发送任务 ---------- */
static void task_cdc_tx(void *arg)
{
    sg_frame_t f;
    uint8_t hdr[SG_FRAME_HEADER_LEN];
    uint8_t crcbuf[SG_FRAME_CRC_LEN];

    while (1) {
        if (xQueueReceive(s_tx_queue, &f, portMAX_DELAY) != pdTRUE) continue;

        /* 组头 */
        hdr[0] = SG_FRAME_MAGIC0;
        hdr[1] = SG_FRAME_MAGIC1;
        hdr[2] = SG_FRAME_VER;
        hdr[3] = f.type;
        hdr[4] = (uint8_t)(f.plen & 0xFF);
        hdr[5] = (uint8_t)((f.plen >> 8) & 0xFF);

        /* CRC 覆盖 [ver,type,lenL,lenH,payload...] */
        uint8_t tmp[4 + SG_FRAME_MAX_PAYLOAD];
        tmp[0] = hdr[2]; tmp[1] = hdr[3];
        tmp[2] = hdr[4]; tmp[3] = hdr[5];
        if (f.plen > 0) memcpy(&tmp[4], f.payload, f.plen);
        uint16_t crc = sg_crc16_ccitt(tmp, 4 + f.plen);

        crcbuf[0] = (uint8_t)(crc & 0xFF);
        crcbuf[1] = (uint8_t)((crc >> 8) & 0xFF);

        /* 写 USB-Serial-JTAG. 使用 100ms 超时, 避免主机断开时长期阻塞 */
        usb_serial_jtag_write_bytes(hdr, SG_FRAME_HEADER_LEN, pdMS_TO_TICKS(100));
        if (f.plen > 0) {
            usb_serial_jtag_write_bytes(f.payload, f.plen, pdMS_TO_TICKS(100));
        }
        usb_serial_jtag_write_bytes(crcbuf, SG_FRAME_CRC_LEN, pdMS_TO_TICKS(100));
    }
}

esp_err_t sg_cdc_send_frame(uint8_t type, const uint8_t *payload, size_t plen)
{
    if (plen > SG_FRAME_MAX_PAYLOAD) return ESP_ERR_INVALID_SIZE;
    if (!s_tx_queue) return ESP_ERR_INVALID_STATE;

    sg_frame_t f;
    f.type = type;
    f.plen = (uint16_t)plen;
    if (plen > 0 && payload) memcpy(f.payload, payload, plen);

    if (xQueueSend(s_tx_queue, &f, pdMS_TO_TICKS(50)) != pdTRUE) {
        return ESP_ERR_TIMEOUT;
    }
    return ESP_OK;
}

esp_err_t sg_cdc_init(void)
{
    ESP_LOGI(SG_TAG_CDC, "init usb_serial_jtag (single CDC, log+data)");

    usb_serial_jtag_driver_config_t cfg = USB_SERIAL_JTAG_DRIVER_CONFIG_DEFAULT();
    cfg.tx_buffer_size = 2048;
    cfg.rx_buffer_size = 2048;
    esp_err_t err = usb_serial_jtag_driver_install(&cfg);
    if (err != ESP_OK && err != ESP_ERR_INVALID_STATE) {
        return err;
    }

    s_tx_queue = xQueueCreate(SG_CDC_TX_QUEUE_LEN, sizeof(sg_frame_t));
    if (!s_tx_queue) return ESP_ERR_NO_MEM;

    return ESP_OK;
}

void sg_cdc_start_tx_task(void)
{
    xTaskCreatePinnedToCore(task_cdc_tx, "cdc_tx",
                            SG_TASK_CDC_TX_STACK, NULL,
                            SG_TASK_CDC_TX_PRIO, NULL,
                            SG_TASK_CDC_TX_CORE);
}

/* ---------- RX 通路 ---------- */
static sg_cdc_rx_cb_t s_rx_cb = NULL;
static void          *s_rx_ctx = NULL;

void sg_cdc_set_rx_cb(sg_cdc_rx_cb_t cb, void *ctx)
{
    s_rx_cb  = cb;
    s_rx_ctx = ctx;
}

/**
 * 状态机解析: 匹配 magic A5 5A, 读 ver/type/len, 读 payload, 校验 CRC.
 * 遇到坏 magic / CRC 错时重新回到"找 magic0"状态, 保证跟 PC 端一致.
 */
typedef enum {
    ST_M0, ST_M1, ST_VER, ST_TYPE, ST_LENL, ST_LENH, ST_PAYLOAD, ST_CRCL, ST_CRCH
} rx_state_t;

static void task_cdc_rx(void *arg)
{
    static uint8_t payload[SG_FRAME_MAX_PAYLOAD];
    rx_state_t st = ST_M0;
    uint8_t  ver = 0, type = 0;
    uint16_t plen = 0, ppos = 0;
    uint16_t crc_expect = 0;
    uint8_t  crc_lo = 0;
    uint32_t n_ok = 0, n_bad = 0;

    for (;;) {
        uint8_t b;
        int r = usb_serial_jtag_read_bytes(&b, 1, pdMS_TO_TICKS(200));
        if (r != 1) continue;

        switch (st) {
        case ST_M0:
            if (b == SG_FRAME_MAGIC0) st = ST_M1;
            break;
        case ST_M1:
            if (b == SG_FRAME_MAGIC1) st = ST_VER;
            else if (b == SG_FRAME_MAGIC0) st = ST_M1;   /* 保持 */
            else st = ST_M0;
            break;
        case ST_VER:
            ver = b;
            if (ver != SG_FRAME_VER) { st = ST_M0; n_bad++; break; }
            st = ST_TYPE;
            break;
        case ST_TYPE:
            type = b;
            st = ST_LENL;
            break;
        case ST_LENL:
            plen = b;
            st = ST_LENH;
            break;
        case ST_LENH:
            plen |= ((uint16_t)b) << 8;
            if (plen > SG_FRAME_MAX_PAYLOAD) { st = ST_M0; n_bad++; break; }
            ppos = 0;
            st = (plen == 0) ? ST_CRCL : ST_PAYLOAD;
            break;
        case ST_PAYLOAD:
            payload[ppos++] = b;
            if (ppos >= plen) st = ST_CRCL;
            break;
        case ST_CRCL:
            crc_lo = b;
            st = ST_CRCH;
            break;
        case ST_CRCH:
            crc_expect = ((uint16_t)b << 8) | crc_lo;
            {
                /* CRC 覆盖 [ver,type,lenL,lenH,payload...] */
                uint8_t hdrbuf[4];
                hdrbuf[0] = ver; hdrbuf[1] = type;
                hdrbuf[2] = (uint8_t)(plen & 0xFF);
                hdrbuf[3] = (uint8_t)(plen >> 8);
                uint16_t crc = sg_crc16_ccitt(hdrbuf, 4);
                if (plen > 0) crc = sg_crc16_ccitt_update(crc, payload, plen);
                if (crc == crc_expect) {
                    n_ok++;
                    if (s_rx_cb) s_rx_cb(type, payload, plen, s_rx_ctx);
                } else {
                    n_bad++;
                    if ((n_bad % 10) == 1) {
                        ESP_LOGW(SG_TAG_CDC, "rx crc err ok=%lu bad=%lu",
                                 (unsigned long)n_ok, (unsigned long)n_bad);
                    }
                }
            }
            st = ST_M0;
            break;
        }
    }
}

void sg_cdc_start_rx_task(void)
{
    xTaskCreatePinnedToCore(task_cdc_rx, "cdc_rx",
                            SG_TASK_CDC_RX_STACK, NULL,
                            SG_TASK_CDC_RX_PRIO, NULL,
                            SG_TASK_CDC_RX_CORE);
}
