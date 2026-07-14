#include "camera_usb_preview.h"

#include <stdlib.h>
#include <string.h>

#include "camera_preview_protocol.h"
#include "driver/uart.h"
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "img_converters.h"

#define SG_PREVIEW_UART UART_NUM_0
#define SG_PREVIEW_BAUD 921600
#define SG_PREVIEW_RX_BUFFER 1024
#define SG_PREVIEW_JPEG_QUALITY 70

static const char *TAG = "sg_camera_usb";
static portMUX_TYPE s_request_lock = portMUX_INITIALIZER_UNLOCKED;
static bool s_request_pending;
static uint32_t s_sequence;

static void preview_request_task(void *arg)
{
    (void)arg;
    uint8_t byte;
    while (true) {
        int received = uart_read_bytes(
            SG_PREVIEW_UART, &byte, 1, pdMS_TO_TICKS(100));
        if (received == 1 && byte == SG_CAMERA_PREVIEW_REQUEST) {
            portENTER_CRITICAL(&s_request_lock);
            s_request_pending = true;
            portEXIT_CRITICAL(&s_request_lock);
            esp_log_level_set("*", ESP_LOG_NONE);
        }
    }
}

esp_err_t sg_camera_usb_preview_init(void)
{
    ESP_LOGI(TAG, "USB preview UART switching to %d baud", SG_PREVIEW_BAUD);
    if (!uart_is_driver_installed(SG_PREVIEW_UART)) {
        esp_err_t err = uart_driver_install(
            SG_PREVIEW_UART, SG_PREVIEW_RX_BUFFER, 0, 0, NULL, 0);
        if (err != ESP_OK) return err;
    }
    esp_err_t err = uart_set_baudrate(SG_PREVIEW_UART, SG_PREVIEW_BAUD);
    if (err != ESP_OK) return err;

    BaseType_t created = xTaskCreate(
        preview_request_task, "camera_usb_rx", 3072, NULL, 8, NULL);
    return created == pdPASS ? ESP_OK : ESP_ERR_NO_MEM;
}

bool sg_camera_usb_preview_requested(void)
{
    portENTER_CRITICAL(&s_request_lock);
    bool requested = s_request_pending;
    s_request_pending = false;
    portEXIT_CRITICAL(&s_request_lock);
    return requested;
}

static esp_err_t write_packet(
    const uint8_t *jpeg,
    size_t jpeg_length,
    uint8_t flags,
    const sg_camera_face_bbox_t *bbox)
{
    const size_t packet_size =
        sizeof(sg_camera_preview_header_t) + jpeg_length + sizeof(uint32_t);
    uint8_t *packet = heap_caps_malloc(
        packet_size, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    if (packet == NULL) packet = malloc(packet_size);
    if (packet == NULL) return ESP_ERR_NO_MEM;

    uint8_t bbox_bytes[4] = {0};
    if (bbox != NULL && bbox->valid) {
        bbox_bytes[0] = bbox->center_x;
        bbox_bytes[1] = bbox->center_y;
        bbox_bytes[2] = bbox->width;
        bbox_bytes[3] = bbox->height;
    }

    sg_camera_preview_header_t *header =
        (sg_camera_preview_header_t *)packet;
    sg_camera_preview_header_init(
        header, ++s_sequence, (uint32_t)jpeg_length, flags, bbox_bytes);
    if (jpeg_length > 0) {
        memcpy(packet + sizeof(*header), jpeg, jpeg_length);
    }

    uint32_t crc = sg_camera_preview_crc32(
        0, &header->version, sizeof(*header) - sizeof(header->magic));
    crc = sg_camera_preview_crc32(crc, jpeg, jpeg_length);
    memcpy(packet + sizeof(*header) + jpeg_length, &crc, sizeof(crc));

    int written = uart_write_bytes(SG_PREVIEW_UART, packet, packet_size);
    free(packet);
    if (written != (int)packet_size) return ESP_FAIL;
    return uart_wait_tx_done(SG_PREVIEW_UART, pdMS_TO_TICKS(2000));
}

esp_err_t sg_camera_usb_preview_send(
    camera_fb_t *frame, const sg_camera_face_bbox_t *bbox)
{
    if (frame == NULL) return ESP_ERR_INVALID_ARG;

    uint8_t *jpeg = NULL;
    size_t jpeg_length = 0;
    bool converted = frame2jpg(
        frame, SG_PREVIEW_JPEG_QUALITY, &jpeg, &jpeg_length);
    if (!converted || jpeg == NULL || jpeg_length > SG_CAMERA_PREVIEW_MAX_JPEG) {
        free(jpeg);
        return write_packet(NULL, 0, SG_CAMERA_PREVIEW_FLAG_ERROR, bbox);
    }

    esp_err_t err = write_packet(jpeg, jpeg_length, 0, bbox);
    free(jpeg);
    return err;
}
