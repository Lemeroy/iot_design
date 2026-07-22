#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "camera_scores_protocol.h"

#ifdef __cplusplus
extern "C" {
#endif

#define SG_CAMERA_UART_PACKET_SIZE 20U
#define SG_CAMERA_UART_MAGIC0 0x53U
#define SG_CAMERA_UART_MAGIC1 0x47U
#define SG_CAMERA_UART_VERSION 1U

typedef enum {
    SG_CAMERA_UART_OK = 0,
    SG_CAMERA_UART_BAD_ARGUMENT,
    SG_CAMERA_UART_BAD_LENGTH,
    SG_CAMERA_UART_BAD_MAGIC,
    SG_CAMERA_UART_BAD_VERSION,
    SG_CAMERA_UART_BAD_CRC,
    SG_CAMERA_UART_BAD_VALUE,
} sg_camera_uart_result_t;

typedef struct {
    sg_camera_face_metrics_t face;
    sg_camera_modal_metrics_t eye;
    sg_camera_modal_metrics_t tongue;
    sg_camera_stage_status_t screening;
} sg_camera_uart_payload_t;

typedef struct {
    uint8_t buffer[SG_CAMERA_UART_PACKET_SIZE];
    size_t used;
} sg_camera_uart_stream_t;

sg_camera_uart_result_t sg_camera_uart_encode(
    const sg_camera_uart_payload_t *payload,
    uint16_t sequence,
    uint8_t out[SG_CAMERA_UART_PACKET_SIZE]);

sg_camera_uart_result_t sg_camera_uart_parse(
    const uint8_t *data,
    size_t length,
    sg_camera_uart_payload_t *payload,
    uint16_t *sequence);

bool sg_camera_uart_stream_feed(
    sg_camera_uart_stream_t *stream,
    uint8_t byte,
    sg_camera_uart_payload_t *payload,
    uint16_t *sequence);

#ifdef __cplusplus
}
#endif
